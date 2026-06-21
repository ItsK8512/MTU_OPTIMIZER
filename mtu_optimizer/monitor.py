"""
mtu_optimizer.monitor — Real-time network monitoring dashboard
Live-updating display with ping sparkline, jitter, loss, and throughput.
"""

import time
import statistics
from typing import Optional

from mtu_optimizer.core import ping_with_size
from mtu_optimizer.ui import (
    console, ping_color, sparkline, score_color, gauge_bar,
    Panel, Rule, Text, box, Layout,
)
from rich.live import Live


def run_network_monitor(host: str = "8.8.8.8", duration: int = 120) -> dict:
    """
    Real-time network monitor with live-updating dashboard.
    Runs for `duration` seconds or until Ctrl+C.
    """
    console.print(Rule("[bold bright_green]📊 Real-time Network Monitor[/]", style="bright_green"))
    console.print()
    console.print(f"  Monitoring [cyan]{host}[/] — Press [bold]Ctrl+C[/] to stop.")
    console.print(f"  [dim]Duration: {duration}s  |  Interval: 0.5s[/]")
    console.print()

    ping_history: list[float] = []
    all_pings: list[float] = []
    sent = 0
    lost = 0
    spikes = 0
    start_time = time.time()

    # Throughput tracking (optional, via psutil)
    has_psutil = False
    net_io_start = None
    try:
        import psutil
        has_psutil = True
        net_io_start = psutil.net_io_counters()
    except ImportError:
        pass

    try:
        with Live(console=console, refresh_per_second=2, transient=False) as live:
            while time.time() - start_time < duration:
                sent += 1
                rtt = ping_with_size(host, 64, timeout=2.0)

                if rtt is not None:
                    all_pings.append(rtt)
                    ping_history.append(rtt)
                    if len(ping_history) > 60:
                        ping_history = ping_history[-60:]
                    avg = statistics.mean(all_pings)
                    if rtt > avg * 2 and len(all_pings) > 5:
                        spikes += 1
                else:
                    lost += 1
                    ping_history.append(0)

                elapsed = time.time() - start_time
                loss_pct = (lost / sent * 100) if sent > 0 else 0

                # Build stats
                if all_pings:
                    avg = statistics.mean(all_pings)
                    mn = min(all_pings)
                    mx = max(all_pings)
                    jitter = statistics.stdev(all_pings) if len(all_pings) > 1 else 0
                    current = rtt if rtt else -1
                else:
                    avg = mn = mx = jitter = 0
                    current = -1

                # Sparkline
                spark_values = [p if p > 0 else avg for p in ping_history]
                spark = sparkline(spark_values, width=40) if spark_values else ""

                # Connection quality (simple)
                if loss_pct > 10 or avg > 200:
                    conn_status = "🔴 UNSTABLE"
                    conn_color = "bold bright_red"
                elif jitter > 20 or avg > 100:
                    conn_status = "🟡 FAIR"
                    conn_color = "bold yellow"
                elif jitter > 10 or avg > 60:
                    conn_status = "🟢 GOOD"
                    conn_color = "bold green"
                else:
                    conn_status = "🟢 STABLE"
                    conn_color = "bold bright_green"

                # Score (0-100)
                score = max(0, min(100, int(
                    100 - avg * 0.3 - jitter * 2 - loss_pct * 5 - spikes * 3
                )))

                # Throughput
                throughput_line = ""
                if has_psutil:
                    try:
                        import psutil
                        net_io_now = psutil.net_io_counters()
                        dl_bytes = net_io_now.bytes_recv - net_io_start.bytes_recv
                        ul_bytes = net_io_now.bytes_sent - net_io_start.bytes_sent
                        dl_rate = dl_bytes / elapsed / 1024 if elapsed > 0 else 0
                        ul_rate = ul_bytes / elapsed / 1024 if elapsed > 0 else 0
                        throughput_line = (
                            f"\n  Throughput   : ▼ [cyan]{dl_rate:.1f} KB/s[/]  "
                            f"▲ [cyan]{ul_rate:.1f} KB/s[/]"
                        )
                    except Exception:
                        pass

                # Current ping display
                if current > 0:
                    current_str = f"[{ping_color(current)}]{current:.0f}ms[/]"
                else:
                    current_str = "[bold red]LOST[/]"

                # Time formatting
                mins, secs = divmod(int(elapsed), 60)
                time_str = f"{mins:02d}:{secs:02d}"

                panel = Panel(
                    f"  Ping ({host}): {current_str}  {spark}\n"
                    f"  Avg: [{ping_color(avg)}]{avg:.1f}ms[/]  "
                    f"Min: [dim]{mn:.1f}ms[/]  "
                    f"Max: [{ping_color(mx)}]{mx:.1f}ms[/]  "
                    f"Spike: [{ping_color(mx)}]{mx:.0f}ms[/]\n"
                    f"  Jitter      : [{'bold yellow' if jitter > 10 else 'dim'}]{jitter:.1f}ms[/]\n"
                    f"  Packet Loss : [{'bold red' if loss_pct > 1 else 'dim'}]{loss_pct:.1f}%[/]  "
                    f"({lost}/{sent} lost)\n"
                    f"  Spikes (>2x): [{'bold red' if spikes > 3 else 'dim'}]{spikes}[/]"
                    f"{throughput_line}\n"
                    f"  Connection  : [{conn_color}]{conn_status}[/]  "
                    f"(score: [{score_color(score)}]{score}/100[/])\n"
                    f"  Duration    : [dim]{time_str} / {duration}s[/]",
                    title="[bold bright_green]📊 Network Monitor — Ctrl+C to stop[/]",
                    border_style="bright_green",
                    box=box.DOUBLE_EDGE,
                    padding=(1, 2),
                )

                live.update(panel)
                time.sleep(0.5)

    except KeyboardInterrupt:
        pass

    # Final summary
    elapsed = time.time() - start_time
    loss_pct = (lost / sent * 100) if sent > 0 else 0

    console.print()
    if all_pings:
        console.print(Panel(
            f"  [bold white]Monitoring Summary ({elapsed:.0f}s)[/]\n\n"
            f"  Total Pings  : {sent}\n"
            f"  Received     : {len(all_pings)}  |  Lost: {lost}\n"
            f"  Avg Latency  : [{ping_color(statistics.mean(all_pings))}]"
            f"{statistics.mean(all_pings):.1f}ms[/]\n"
            f"  Min / Max    : {min(all_pings):.1f}ms / {max(all_pings):.1f}ms\n"
            f"  Jitter       : {statistics.stdev(all_pings):.1f}ms\n"
            f"  Packet Loss  : {loss_pct:.1f}%\n"
            f"  Spikes       : {spikes}",
            title="[bold bright_green]📊 Session Summary[/]",
            border_style="green",
            box=box.ROUNDED,
            padding=(1, 2),
        ))
    else:
        console.print("[bold red]  No pings received during monitoring.[/]")

    console.print()

    return {
        "host": host,
        "duration": elapsed,
        "total_sent": sent,
        "total_received": len(all_pings),
        "avg_ms": round(statistics.mean(all_pings), 1) if all_pings else -1,
        "min_ms": round(min(all_pings), 1) if all_pings else -1,
        "max_ms": round(max(all_pings), 1) if all_pings else -1,
        "jitter_ms": round(statistics.stdev(all_pings), 1) if len(all_pings) > 1 else 0,
        "loss_pct": round(loss_pct, 1),
        "spikes": spikes,
        "ping_history": all_pings,
    }
