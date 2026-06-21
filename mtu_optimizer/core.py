"""
mtu_optimizer.core — MTU finder and server ping engine
Provides binary-search MTU discovery and multi-host ICMP ping with statistics.
"""

import re
import time
import statistics
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Optional

import ping3
from ping3 import ping as ping3_ping

from mtu_optimizer.servers import MTU_TEST_HOSTS, VALORANT_SERVERS, GAMES
from mtu_optimizer.ui import (
    console, ping_color, rating_color, rating_emoji,
    make_progress, sparkline, Panel, Table, Rule, Align, Text, box,
    TextColumn,
)

# ── Constants ─────────────────────────────────────────────────────────────────
PING_TIMEOUT = 2.0
MTU_MIN = 576
MTU_MAX = 1500
PING_COUNT = 10
STABILITY_DURATION = 30   # seconds for stability test


# ── Data classes ──────────────────────────────────────────────────────────────
@dataclass
class PingResult:
    region: str
    avg_ms: float
    min_ms: float
    max_ms: float
    jitter_ms: float
    loss_pct: float
    rating: str = ""

    def __post_init__(self):
        if self.avg_ms < 0:
            self.rating = "UNREACHABLE"
        elif self.avg_ms < 40:
            self.rating = "EXCELLENT"
        elif self.avg_ms < 70:
            self.rating = "GOOD"
        elif self.avg_ms < 100:
            self.rating = "OK"
        elif self.avg_ms < 150:
            self.rating = "POOR"
        else:
            self.rating = "BAD"


# ── ICMP ping with DF bit ────────────────────────────────────────────────────
def ping_with_size(host: str, payload_size: int, timeout: float = 2.0) -> Optional[float]:
    """
    Send a single ICMP echo with a specific payload size and DF bit set.
    Returns round-trip time in ms, or None on failure/fragmentation.
    """
    try:
        result = ping3_ping(host, timeout=timeout, size=payload_size, unit="ms")
        if result is False or result is None:
            return None
        return float(result)
    except Exception:
        return None


# ── MTU finder (binary search) ───────────────────────────────────────────────
def find_optimal_mtu(host: str, progress_callback=None) -> int:
    """
    Binary search to find the largest payload that doesn't fragment.
    MTU = largest_payload + 28  (IP header 20 + ICMP header 8)
    """
    lo, hi = MTU_MIN - 28, MTU_MAX - 28
    best = lo
    iterations = 0
    max_iterations = 12

    while lo <= hi and iterations < max_iterations:
        mid = (lo + hi) // 2
        iterations += 1

        if progress_callback:
            progress_callback(mid + 28, lo + 28, hi + 28)

        successes = 0
        for _ in range(3):
            rtt = ping_with_size(host, mid, timeout=PING_TIMEOUT)
            if rtt is not None:
                successes += 1
            time.sleep(0.05)

        if successes >= 2:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1

        time.sleep(0.1)

    return best + 28


def find_optimal_mtu_parallel(progress_callback=None) -> int:
    """
    Test multiple hosts in parallel and return the consensus MTU.
    More reliable than single-host testing.
    """
    results = []
    lock = threading.Lock()

    def worker(host):
        mtu = find_optimal_mtu(host)
        with lock:
            results.append(mtu)

    threads = []
    for host in MTU_TEST_HOSTS:
        t = threading.Thread(target=worker, args=(host,), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=30)

    if results:
        # Return the minimum (most conservative / safest) MTU
        return min(results)
    return 1500


# ── OS-level ping (no admin needed) ──────────────────────────────────────────
def os_ping(host: str, count: int = 3, timeout_ms: int = 1500) -> tuple[list[float], float]:
    """
    Use Windows ping.exe.  Returns (rtt_list_ms, loss_percent).
    """
    try:
        result = subprocess.run(
            ["ping", "-n", str(count), "-w", str(timeout_ms), host],
            capture_output=True, text=True,
            timeout=count * (timeout_ms / 1000 + 0.5) + 2,
            encoding="utf-8", errors="replace",
        )
        output = result.stdout
        rtts = []
        for m in re.finditer(r"time[=<](\d+)\s*ms", output, re.IGNORECASE):
            rtts.append(float(m.group(1)))
        for m in re.finditer(r"time<1ms", output, re.IGNORECASE):
            rtts.append(0.5)

        loss_match = re.search(r"(\d+)%\s+loss", output, re.IGNORECASE)
        loss = float(loss_match.group(1)) if loss_match else (100.0 if not rtts else 0.0)
        return rtts, loss
    except Exception:
        return [], 100.0


def ping_server_group(region: str, hosts: list) -> PingResult:
    """Ping all hosts for a region and aggregate statistics."""
    all_rtts: list[float] = []
    total_sent = 0
    total_lost = 0
    samples = 4

    for ip in hosts:
        rtts, loss = os_ping(ip, count=samples, timeout_ms=1500)
        all_rtts.extend(rtts)
        total_sent += samples
        total_lost += int(round(samples * loss / 100))

    if not all_rtts:
        return PingResult(region=region, avg_ms=-1, min_ms=-1, max_ms=-1,
                          jitter_ms=0, loss_pct=100.0)

    loss_pct = max(0.0, total_lost / total_sent * 100) if total_sent else 100.0
    avg = statistics.mean(all_rtts)
    mn = min(all_rtts)
    mx = max(all_rtts)
    jitter = statistics.stdev(all_rtts) if len(all_rtts) > 1 else 0.0

    return PingResult(
        region=region,
        avg_ms=round(avg, 1),
        min_ms=round(mn, 1),
        max_ms=round(mx, 1),
        jitter_ms=round(jitter, 1),
        loss_pct=round(loss_pct, 1),
    )


# ── Stability test ────────────────────────────────────────────────────────────
@dataclass
class StabilityResult:
    host: str
    duration_s: float
    total_pings: int
    avg_ms: float
    min_ms: float
    max_ms: float
    jitter_ms: float
    loss_pct: float
    spikes: int          # count of pings > 2x average
    ping_history: list[float] = field(default_factory=list)

    @property
    def rating(self) -> str:
        if self.loss_pct > 5:
            return "UNSTABLE"
        if self.spikes > self.total_pings * 0.1:
            return "SPIKY"
        if self.jitter_ms > 20:
            return "INCONSISTENT"
        if self.avg_ms < 50 and self.jitter_ms < 5:
            return "ROCK SOLID"
        if self.jitter_ms < 10:
            return "STABLE"
        return "FAIR"


def run_stability_test(host: str = "8.8.8.8",
                       duration: int = STABILITY_DURATION,
                       progress_callback=None) -> StabilityResult:
    """
    Sustained ping test over `duration` seconds.  Detects spikes and packet loss.
    """
    rtts: list[float] = []
    sent = 0
    start = time.time()

    while time.time() - start < duration:
        sent += 1
        elapsed_pct = min(100, int((time.time() - start) / duration * 100))

        rtt = ping_with_size(host, 64, timeout=2.0)
        if rtt is not None:
            rtts.append(rtt)

        if progress_callback:
            current_ms = rtt if rtt else -1
            progress_callback(elapsed_pct, current_ms, len(rtts), sent)

        time.sleep(0.5)

    if not rtts:
        return StabilityResult(
            host=host, duration_s=duration, total_pings=sent,
            avg_ms=-1, min_ms=-1, max_ms=-1, jitter_ms=0,
            loss_pct=100.0, spikes=0, ping_history=[],
        )

    avg = statistics.mean(rtts)
    spikes = sum(1 for r in rtts if r > avg * 2)
    loss_pct = max(0.0, (sent - len(rtts)) / sent * 100)

    return StabilityResult(
        host=host,
        duration_s=time.time() - start,
        total_pings=sent,
        avg_ms=round(avg, 1),
        min_ms=round(min(rtts), 1),
        max_ms=round(max(rtts), 1),
        jitter_ms=round(statistics.stdev(rtts), 1) if len(rtts) > 1 else 0.0,
        loss_pct=round(loss_pct, 1),
        spikes=spikes,
        ping_history=rtts,
    )


# ── UI wrappers ───────────────────────────────────────────────────────────────
def build_ping_table(results: list[PingResult], game_name: str = "Valorant") -> Table:
    """Build a Rich table from ping results."""
    table = Table(
        title=f"[bold bright_red]⚡ {game_name} Server Ping Results[/]",
        box=box.DOUBLE_EDGE,
        border_style="red",
        header_style="bold bright_white on grey15",
        show_footer=False,
        pad_edge=True,
        expand=False,
    )
    table.add_column("Region", style="bold white", min_width=26)
    table.add_column("Avg", justify="right", min_width=8)
    table.add_column("Min", justify="right", min_width=8)
    table.add_column("Max", justify="right", min_width=8)
    table.add_column("Jitter", justify="right", min_width=8)
    table.add_column("Loss", justify="right", min_width=8)
    table.add_column("Rating", justify="center", min_width=12)

    sorted_results = sorted(results, key=lambda r: r.avg_ms if r.avg_ms > 0 else 9999)

    for i, r in enumerate(sorted_results):
        prefix = "👑 " if i == 0 and r.avg_ms > 0 else "   "
        region_text = f"{prefix}{r.region}"

        if r.avg_ms < 0:
            table.add_row(
                region_text,
                "[dim]N/A[/]", "[dim]N/A[/]", "[dim]N/A[/]",
                "[dim]N/A[/]", "[dim red]100%[/]",
                "[dim]⚫ UNREACHABLE[/]",
            )
        else:
            pc = ping_color(r.avg_ms)
            rc = rating_color(r.rating)
            em = rating_emoji(r.rating)
            table.add_row(
                region_text,
                f"[{pc}]{r.avg_ms} ms[/]",
                f"[dim]{r.min_ms} ms[/]",
                f"[dim]{r.max_ms} ms[/]",
                f"[{'bold yellow' if r.jitter_ms > 15 else 'dim'}]{r.jitter_ms} ms[/]",
                f"[{'bold red' if r.loss_pct > 5 else 'dim'}]{r.loss_pct}%[/]",
                f"[{rc}]{em} {r.rating}[/]",
            )

    return table


def run_mtu_finder(scan_only: bool = False) -> int:
    """Interactive MTU finder with progress UI."""
    console.print(Rule("[bold red]🔍 MTU Discovery[/]", style="red"))
    console.print()

    test_host = "8.8.8.8"
    for h in MTU_TEST_HOSTS:
        r = ping3_ping(h, timeout=2, unit="ms")
        if r and r > 0:
            test_host = h
            break

    console.print(f"  Testing against [cyan]{test_host}[/] (DF bit set — no fragmentation allowed)")
    console.print()

    result_mtu = [1500]

    with make_progress(bar_color="red", extra_columns=[
        TextColumn("[dim]{task.fields[info]}"),
    ]) as progress:
        task = progress.add_task(
            "Finding optimal MTU...",
            total=100,
            info="Starting binary search...",
        )

        iteration = [0]
        max_iters = 12

        def cb(current_mtu, lo, hi):
            iteration[0] += 1
            pct = min(100, int(iteration[0] / max_iters * 100))
            progress.update(
                task,
                completed=pct,
                description=f"Testing MTU [bold cyan]{current_mtu}[/]...",
                info=f"range [{lo}–{hi}]",
            )

        recommended = find_optimal_mtu(test_host, progress_callback=cb)
        progress.update(task, completed=100,
                        description="[bold green]MTU scan complete!",
                        info=f"Optimal: {recommended}")
        result_mtu[0] = recommended

    console.print()
    console.print(Panel(
        Align.center(
            Text.from_markup(
                f"\n  🎯 Optimal MTU: [bold bright_green]{result_mtu[0]}[/bold bright_green] bytes\n"
                f"  [dim](payload: {result_mtu[0] - 28} bytes  ·  headers: 28 bytes)[/dim]\n"
            )
        ),
        border_style="bright_green",
        box=box.DOUBLE_EDGE,
    ))
    console.print()
    return result_mtu[0]


def run_ping_test(game_name: str = "Valorant",
                  servers: dict | None = None) -> list[PingResult]:
    """Ping all server regions for a game."""
    if servers is None:
        servers = VALORANT_SERVERS

    game_info = GAMES.get(game_name, {})
    emoji = game_info.get("emoji", "📡")
    color = game_info.get("color", "red")

    console.print(Rule(f"[bold {color}]{emoji} {game_name} Server Ping Test[/]", style=color))
    console.print()

    results = []
    regions = list(servers.items())

    with make_progress(bar_color=color, extra_columns=[
        TextColumn("[dim]{task.completed}/{task.total} regions[/dim]"),
    ]) as progress:
        task = progress.add_task("Pinging regions...", total=len(regions))

        for region, ips in regions:
            progress.update(task, description=f"Pinging {region.strip()}...")
            result = ping_server_group(region, ips)
            results.append(result)
            progress.advance(task)

    console.print()
    console.print(build_ping_table(results, game_name=game_name))
    console.print()
    return results


def run_stability_test_ui(host: str = "8.8.8.8",
                          duration: int = STABILITY_DURATION) -> StabilityResult:
    """Connection stability test with live sparkline display."""
    console.print(Rule("[bold red]📈 Connection Stability Test[/]", style="red"))
    console.print()
    console.print(f"  Pinging [cyan]{host}[/] for [bold]{duration}[/] seconds...")
    console.print(f"  [dim]Detects latency spikes, packet loss, and jitter patterns.[/]")
    console.print()

    ping_history: list[float] = []

    with make_progress(bar_color="cyan", extra_columns=[
        TextColumn("[dim]{task.fields[info]}"),
    ]) as progress:
        task = progress.add_task(
            "Testing stability...",
            total=100,
            info="Starting...",
        )

        def cb(pct, current_ms, received, sent):
            ms_str = f"{current_ms:.0f}ms" if current_ms > 0 else "lost"
            spark = sparkline(ping_history, width=20) if ping_history else ""
            if current_ms > 0:
                ping_history.append(current_ms)
            progress.update(
                task,
                completed=pct,
                description=f"Ping: [{ping_color(current_ms)}]{ms_str}[/]",
                info=f"{spark}  {received}/{sent} ok",
            )

        result = run_stability_test(host, duration, progress_callback=cb)
        progress.update(task, completed=100,
                        description="[bold green]Stability test complete!",
                        info=f"avg: {result.avg_ms}ms")

    result.ping_history = ping_history

    # Display results
    console.print()
    spark = sparkline(result.ping_history, width=40)

    rating_styles = {
        "ROCK SOLID": "bold bright_green",
        "STABLE": "bold green",
        "FAIR": "bold yellow",
        "INCONSISTENT": "bold red",
        "SPIKY": "bold bright_red",
        "UNSTABLE": "bold bright_red",
    }
    rs = rating_styles.get(result.rating, "white")

    console.print(Panel(
        f"  📊 Ping Graph : {spark}\n\n"
        f"  Avg Latency   : [{ping_color(result.avg_ms)}]{result.avg_ms} ms[/]\n"
        f"  Min / Max     : [dim]{result.min_ms} ms[/] / [{ping_color(result.max_ms)}]{result.max_ms} ms[/]\n"
        f"  Jitter        : [{'bold yellow' if result.jitter_ms > 10 else 'dim'}]{result.jitter_ms} ms[/]\n"
        f"  Packet Loss   : [{'bold red' if result.loss_pct > 1 else 'dim'}]{result.loss_pct}%[/]\n"
        f"  Spikes (>2x)  : [{'bold red' if result.spikes > 2 else 'dim'}]{result.spikes}[/]\n"
        f"  Duration      : [dim]{result.duration_s:.0f}s ({result.total_pings} pings)[/]\n\n"
        f"  Verdict       : [{rs}]{result.rating}[/]",
        title="[bold cyan]📈 Stability Report[/]",
        border_style="cyan",
        box=box.DOUBLE_EDGE,
        padding=(1, 2),
    ))
    console.print()
    return result
