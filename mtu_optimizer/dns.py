"""
mtu_optimizer.dns — DNS provider database and benchmark engine
Benchmarks 25+ DNS providers via raw UDP queries and displays a leaderboard.
"""

import time
import random
import socket
import struct
import statistics
import threading
from dataclasses import dataclass
from typing import Optional

from mtu_optimizer.ui import (
    console, ping_color, dns_rating_color, dns_rating_emoji,
    make_progress, Panel, Table, Rule, Align, Text, box,
    TextColumn, Confirm,
)

# ── Constants ─────────────────────────────────────────────────────────────────
DNS_TEST_DOMAIN = "www.google.com"
DNS_BENCH_ROUNDS = 5
DNS_TIMEOUT = 2.0

# ── DNS provider database ────────────────────────────────────────────────────
DNS_PROVIDERS = {
    # ── Tier-1: Privacy + Speed
    "Cloudflare (1.1.1.1)": {
        "primary": "1.1.1.1", "secondary": "1.0.0.1",
        "tag": "privacy · fast",
    },
    "Cloudflare Gaming (1.1.1.3)": {
        "primary": "1.1.1.3", "secondary": "1.0.0.3",
        "tag": "blocks malware/adult",
    },
    "Google (8.8.8.8)": {
        "primary": "8.8.8.8", "secondary": "8.8.4.4",
        "tag": "reliable · global",
    },
    "Quad9 (9.9.9.9)": {
        "primary": "9.9.9.9", "secondary": "149.112.112.112",
        "tag": "security filtered",
    },
    # ── Tier-2: Gaming-optimised
    "Comodo Secure DNS": {
        "primary": "8.26.56.26", "secondary": "8.20.247.20",
        "tag": "gaming · secure",
    },
    "OpenDNS (Cisco)": {
        "primary": "208.67.222.222", "secondary": "208.67.220.220",
        "tag": "smart cache",
    },
    "OpenDNS FamilyShield": {
        "primary": "208.67.222.123", "secondary": "208.67.220.123",
        "tag": "family safe",
    },
    "Level3 (Lumen)": {
        "primary": "4.2.2.1", "secondary": "4.2.2.2",
        "tag": "backbone cdn",
    },
    "Level3 Alt": {
        "primary": "4.2.2.3", "secondary": "4.2.2.4",
        "tag": "backbone cdn",
    },
    # ── Tier-3: Regional fast resolvers
    "DNS.WATCH": {
        "primary": "84.200.69.80", "secondary": "84.200.70.40",
        "tag": "no logging · EU",
    },
    "Freenom World": {
        "primary": "80.80.80.80", "secondary": "80.80.81.81",
        "tag": "neutral",
    },
    "Verisign Public": {
        "primary": "64.6.64.6", "secondary": "64.6.65.6",
        "tag": "stability",
    },
    "Norton ConnectSafe": {
        "primary": "199.85.126.10", "secondary": "199.85.127.10",
        "tag": "security",
    },
    "AdGuard DNS": {
        "primary": "94.140.14.14", "secondary": "94.140.15.15",
        "tag": "ad blocking",
    },
    "AdGuard Family": {
        "primary": "94.140.14.15", "secondary": "94.140.15.16",
        "tag": "family · ads",
    },
    "CleanBrowsing Security": {
        "primary": "185.228.168.9", "secondary": "185.228.169.9",
        "tag": "security filter",
    },
    "CleanBrowsing Family": {
        "primary": "185.228.168.168", "secondary": "185.228.169.168",
        "tag": "family safe",
    },
    "Alternate DNS": {
        "primary": "76.76.19.19", "secondary": "76.223.122.150",
        "tag": "ad blocking",
    },
    "NextDNS": {
        "primary": "45.90.28.0", "secondary": "45.90.30.0",
        "tag": "customizable",
    },
    "ControlD": {
        "primary": "76.76.2.0", "secondary": "76.76.10.0",
        "tag": "no-log · fast",
    },
    "Yandex Basic": {
        "primary": "77.88.8.8", "secondary": "77.88.8.1",
        "tag": "RU/ME region",
    },
    "Yandex Safe": {
        "primary": "77.88.8.88", "secondary": "77.88.8.2",
        "tag": "security · RU/ME",
    },
    "Neustar UltraDNS": {
        "primary": "156.154.70.1", "secondary": "156.154.71.1",
        "tag": "anycast",
    },
    "Hurricane Electric": {
        "primary": "74.82.42.42", "secondary": "74.82.42.42",
        "tag": "backbone",
    },
}


# ── Data class ────────────────────────────────────────────────────────────────
@dataclass
class DnsResult:
    name: str
    primary: str
    secondary: str
    tag: str
    avg_ms: float      # -1 = unreachable
    min_ms: float
    jitter_ms: float
    loss_pct: float
    rank: int = 0

    @property
    def rating(self) -> str:
        if self.avg_ms < 0:
            return "UNREACHABLE"
        if self.avg_ms < 10:
            return "BLAZING"
        if self.avg_ms < 25:
            return "EXCELLENT"
        if self.avg_ms < 50:
            return "GOOD"
        if self.avg_ms < 100:
            return "OK"
        if self.avg_ms < 200:
            return "SLOW"
        return "BAD"


# ── Raw DNS query engine ─────────────────────────────────────────────────────
def dns_query_latency(server_ip: str, domain: str = DNS_TEST_DOMAIN,
                      timeout: float = DNS_TIMEOUT) -> Optional[float]:
    """
    Send a raw DNS A-record query to server_ip:53 (UDP) and measure RTT in ms.
    Bypasses the OS resolver so results are server-specific.
    """
    txid = random.randint(0, 0xFFFF)
    flags = 0x0100
    qdcount = 1
    header = struct.pack(">HHHHHH", txid, flags, qdcount, 0, 0, 0)

    labels = b""
    for part in domain.split("."):
        encoded = part.encode()
        labels += bytes([len(encoded)]) + encoded
    labels += b"\x00"
    qtype = struct.pack(">H", 1)
    qclass = struct.pack(">H", 1)
    packet = header + labels + qtype + qclass

    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        t0 = time.perf_counter()
        sock.sendto(packet, (server_ip, 53))
        data, _ = sock.recvfrom(512)
        elapsed = (time.perf_counter() - t0) * 1000

        resp_id = struct.unpack(">H", data[:2])[0]
        resp_flags = struct.unpack(">H", data[2:4])[0]
        if resp_id == txid and (resp_flags & 0x8000):
            return round(elapsed, 2)
        return None
    except Exception:
        return None
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


def _bench_one_dns(name: str, info: dict) -> DnsResult:
    """Benchmark a single DNS provider."""
    primary = info["primary"]
    secondary = info["secondary"]
    tag = info["tag"]
    rtts: list[float] = []
    sent = DNS_BENCH_ROUNDS

    for _ in range(DNS_BENCH_ROUNDS):
        rtt = dns_query_latency(primary)
        if rtt is not None:
            rtts.append(rtt)
        time.sleep(0.05)

    if not rtts:
        return DnsResult(name=name, primary=primary, secondary=secondary, tag=tag,
                         avg_ms=-1, min_ms=-1, jitter_ms=0, loss_pct=100.0)

    loss = max(0.0, (sent - len(rtts)) / sent * 100)
    avg = statistics.mean(rtts)
    mn = min(rtts)
    jitter = statistics.stdev(rtts) if len(rtts) > 1 else 0.0
    return DnsResult(
        name=name, primary=primary, secondary=secondary, tag=tag,
        avg_ms=round(avg, 2), min_ms=round(mn, 2),
        jitter_ms=round(jitter, 2), loss_pct=round(loss, 1),
    )


def scan_dns_servers(providers: dict | None = None,
                     progress_callback=None) -> list[DnsResult]:
    """Benchmark all DNS providers in parallel.  Returns sorted fastest→slowest."""
    if providers is None:
        providers = DNS_PROVIDERS

    results: list[DnsResult] = []
    lock = threading.Lock()
    completed = [0]

    def worker(name, info):
        r = _bench_one_dns(name, info)
        with lock:
            results.append(r)
            completed[0] += 1
            if progress_callback:
                progress_callback(completed[0], len(providers), name)

    threads = []
    for name, info in providers.items():
        t = threading.Thread(target=worker, args=(name, info), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=DNS_TIMEOUT * DNS_BENCH_ROUNDS + 5)

    reachable = sorted([r for r in results if r.avg_ms >= 0], key=lambda r: r.avg_ms)
    unreachable = [r for r in results if r.avg_ms < 0]
    sorted_results = reachable + unreachable
    for i, r in enumerate(sorted_results):
        r.rank = i + 1
    return sorted_results


# ── UI ────────────────────────────────────────────────────────────────────────
def build_dns_table(results: list[DnsResult]) -> Table:
    table = Table(
        title="[bold bright_cyan]🌐 DNS Benchmark Results — Fastest First[/]",
        box=box.DOUBLE_EDGE,
        border_style="cyan",
        header_style="bold bright_white on grey15",
        show_footer=False,
        pad_edge=True,
        expand=False,
    )
    table.add_column("#",          justify="right",  min_width=3,  style="dim")
    table.add_column("Provider",   justify="left",   min_width=28, style="bold white")
    table.add_column("Primary IP", justify="left",   min_width=16)
    table.add_column("Secondary",  justify="left",   min_width=16)
    table.add_column("Avg",        justify="right",  min_width=9)
    table.add_column("Min",        justify="right",  min_width=9)
    table.add_column("Jitter",     justify="right",  min_width=9)
    table.add_column("Loss",       justify="right",  min_width=6)
    table.add_column("Rating",     justify="center", min_width=14)
    table.add_column("Tag",        justify="left",   min_width=16, style="dim italic")

    for r in results:
        prefix = "🏆 " if r.rank == 1 and r.avg_ms >= 0 else (
                 "🥈 " if r.rank == 2 and r.avg_ms >= 0 else (
                 "🥉 " if r.rank == 3 and r.avg_ms >= 0 else "   "))
        if r.avg_ms < 0:
            table.add_row(
                str(r.rank), f"{prefix}{r.name}", f"[dim]{r.primary}[/]",
                f"[dim]{r.secondary}[/]",
                "[dim]N/A[/]", "[dim]N/A[/]", "[dim]N/A[/]",
                "[dim red]100%[/]", "[dim]⚫ UNREACHABLE[/]", r.tag,
            )
        else:
            pc = ping_color(r.avg_ms)
            rc = dns_rating_color(r.rating)
            em = dns_rating_emoji(r.rating)
            table.add_row(
                str(r.rank),
                f"{prefix}{r.name}",
                f"[bold cyan]{r.primary}[/]",
                f"[dim]{r.secondary}[/]",
                f"[{pc}]{r.avg_ms} ms[/]",
                f"[dim]{r.min_ms} ms[/]",
                f"[{'bold yellow' if r.jitter_ms > 5 else 'dim'}]{r.jitter_ms} ms[/]",
                f"[{'bold red' if r.loss_pct > 5 else 'dim'}]{r.loss_pct}%[/]",
                f"[{rc}]{em} {r.rating}[/]",
                r.tag,
            )
    return table


def run_dns_scanner(adapter: str | None = None,
                    auto_apply: bool = False) -> Optional[DnsResult]:
    """Full DNS scanner UI with leaderboard."""
    console.print(Rule("[bold cyan]🌐 DNS Speed Scanner[/]", style="cyan"))
    console.print()
    console.print(
        f"  Benchmarking [bold]{len(DNS_PROVIDERS)}[/] DNS providers via raw UDP queries\n"
        f"  Domain: [cyan]{DNS_TEST_DOMAIN}[/]  ·  Rounds per server: [cyan]{DNS_BENCH_ROUNDS}[/]\n"
        f"  [dim]All queries sent in parallel — results in ~{DNS_BENCH_ROUNDS * 0.1:.0f}s[/]\n"
    )

    with make_progress(bar_color="cyan", extra_columns=[
        TextColumn("[dim]{task.completed}/{task.total} tested[/dim]"),
    ]) as progress:
        task = progress.add_task("Scanning DNS servers...", total=len(DNS_PROVIDERS))

        def cb(done, total, last_name):
            progress.update(
                task,
                completed=done,
                description=f"Tested: [dim]{last_name[:30]}[/]",
            )

        results = scan_dns_servers(progress_callback=cb)
        progress.update(task, completed=len(DNS_PROVIDERS),
                        description="[bold green]DNS scan complete!")

    console.print()
    console.print(build_dns_table(results))
    console.print()

    reachable = [r for r in results if r.avg_ms >= 0]
    if not reachable:
        console.print("[bold red]  ❌ No DNS server responded. Check your internet connection.[/]")
        return None

    winner = reachable[0]

    console.print(Panel(
        f"  🏆 Fastest DNS: [bold bright_cyan]{winner.name}[/]\n"
        f"     Primary  : [bold white]{winner.primary}[/]\n"
        f"     Secondary: [bold white]{winner.secondary}[/]\n"
        f"     Avg Ping : [bold bright_green]{winner.avg_ms} ms[/]   "
        f"Jitter: [dim]{winner.jitter_ms} ms[/]\n"
        f"     Rating   : [{dns_rating_color(winner.rating)}]{dns_rating_emoji(winner.rating)} {winner.rating}[/]",
        title="[bold bright_cyan]🏆 DNS Benchmark Winner[/]",
        border_style="bright_cyan",
        box=box.DOUBLE_EDGE,
        padding=(1, 2),
    ))
    console.print()

    if adapter:
        from mtu_optimizer.tweaks import set_dns_custom, flush_dns

        do_apply = auto_apply
        if not auto_apply:
            do_apply = Confirm.ask(
                f"  [bold yellow]Apply {winner.name} ({winner.primary}) as your DNS now?[/]",
                default=True,
                console=console,
            )
        if do_apply:
            ok, msg = set_dns_custom(
                adapter, winner.primary, winner.secondary, winner.name,
            )
            flush_ok, flush_msg = flush_dns()
            icon = "✅" if ok else "❌"
            color = "green" if ok else "red"
            console.print(f"  {icon} [{color}]{msg}[/{color}]")
            console.print(f"  ✅ [green]{flush_msg}[/green]")
            console.print()

    return winner
