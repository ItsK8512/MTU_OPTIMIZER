"""
mtu_optimizer.speedtest — Built-in internet speed test
Measures download/upload speed and bufferbloat detection.
Uses HTTP-based testing without external dependencies.
"""

import time
import socket
import threading
import statistics
from typing import Optional

from mtu_optimizer.core import ping_with_size
from mtu_optimizer.ui import (
    console, ping_color, score_color, make_progress, gauge_bar,
    Panel, Rule, Table, Text, box, TextColumn,
)


# ── Speed test targets (well-known CDN endpoints) ────────────────────────────
SPEED_TEST_URLS = [
    # Cloudflare speed test endpoints
    ("https://speed.cloudflare.com/__down?bytes=10000000", "Cloudflare", 10_000_000),
    ("https://speed.cloudflare.com/__down?bytes=25000000", "Cloudflare", 25_000_000),
]

UPLOAD_TEST_URL = "https://speed.cloudflare.com/__up"


def _download_speed_test(url: str, size_hint: int, timeout: float = 15.0) -> Optional[float]:
    """
    Download from URL and measure speed.
    Returns speed in Mbps, or None on failure.
    """
    try:
        import requests
        start = time.perf_counter()
        resp = requests.get(url, timeout=timeout, stream=True)
        total = 0
        for chunk in resp.iter_content(chunk_size=65536):
            total += len(chunk)
        elapsed = time.perf_counter() - start
        if elapsed > 0 and total > 0:
            mbps = (total * 8) / (elapsed * 1_000_000)
            return round(mbps, 2)
    except ImportError:
        return _download_speed_socket(timeout)
    except Exception:
        pass
    return None


def _download_speed_socket(timeout: float = 10.0) -> Optional[float]:
    """Fallback speed test using raw socket to Cloudflare."""
    try:
        import ssl
        context = ssl.create_default_context()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        ssock = context.wrap_socket(sock, server_hostname="speed.cloudflare.com")
        ssock.connect(("speed.cloudflare.com", 443))

        request = (
            "GET /__down?bytes=5000000 HTTP/1.1\r\n"
            "Host: speed.cloudflare.com\r\n"
            "Connection: close\r\n\r\n"
        )
        ssock.sendall(request.encode())

        total = 0
        start = time.perf_counter()
        while True:
            data = ssock.recv(65536)
            if not data:
                break
            total += len(data)

        elapsed = time.perf_counter() - start
        ssock.close()

        if elapsed > 0 and total > 0:
            mbps = (total * 8) / (elapsed * 1_000_000)
            return round(mbps, 2)
    except Exception:
        pass
    return None


def _upload_speed_test(timeout: float = 10.0) -> Optional[float]:
    """Upload test using requests POST."""
    try:
        import requests
        payload = b"0" * 2_000_000  # 2MB upload
        start = time.perf_counter()
        requests.post(UPLOAD_TEST_URL, data=payload, timeout=timeout)
        elapsed = time.perf_counter() - start

        if elapsed > 0:
            mbps = (len(payload) * 8) / (elapsed * 1_000_000)
            return round(mbps, 2)
    except Exception:
        pass
    return None


def _ping_during_load(host: str = "8.8.8.8", duration: float = 5.0) -> list[float]:
    """Ping during a speed test to detect bufferbloat."""
    rtts = []
    start = time.time()
    while time.time() - start < duration:
        rtt = ping_with_size(host, 64, timeout=1.0)
        if rtt is not None:
            rtts.append(rtt)
        time.sleep(0.3)
    return rtts


def _speed_rating(mbps: float) -> tuple[str, str, str]:
    """Return (rating, color, emoji) for a speed value."""
    if mbps < 5:
        return "POOR", "bold bright_red", "🔴"
    if mbps < 25:
        return "PLAYABLE", "bold yellow", "🟡"
    if mbps < 100:
        return "GOOD", "bold green", "🟢"
    return "EXCELLENT", "bold bright_green", "🚀"


def _bufferbloat_rating(idle_ms: float, load_ms: float) -> tuple[str, str]:
    """Rate bufferbloat based on ping increase under load."""
    if idle_ms <= 0 or load_ms <= 0:
        return "Unknown", "dim"
    increase = load_ms - idle_ms
    if increase < 5:
        return "None (excellent)", "bold bright_green"
    if increase < 15:
        return "Low (good)", "bold green"
    if increase < 30:
        return "Moderate (acceptable)", "bold yellow"
    if increase < 80:
        return "High (bad for gaming)", "bold red"
    return "Severe (fix this!)", "bold bright_red"


# ── Main speed test UI ────────────────────────────────────────────────────────
def run_speed_test() -> dict:
    """Full speed test with download, upload, and bufferbloat detection."""
    console.print(Rule("[bold bright_magenta]⚡ Internet Speed Test[/]", style="bright_magenta"))
    console.print()
    console.print("  [dim]Testing download/upload speed and bufferbloat...[/]")
    console.print()

    results = {
        "download_mbps": 0,
        "upload_mbps": 0,
        "idle_ping_ms": 0,
        "loaded_ping_ms": 0,
        "bufferbloat": "Unknown",
    }

    with make_progress(bar_color="bright_magenta", extra_columns=[
        TextColumn("[dim]{task.fields[info]}"),
    ]) as progress:
        task = progress.add_task("Speed test...", total=5, info="Starting...")

        # Step 1: Idle ping
        progress.update(task, description="Measuring idle ping...", info="baseline latency")
        idle_pings = []
        for _ in range(5):
            rtt = ping_with_size("8.8.8.8", 64, timeout=2.0)
            if rtt is not None:
                idle_pings.append(rtt)
            time.sleep(0.2)
        idle_ping = statistics.mean(idle_pings) if idle_pings else 0
        results["idle_ping_ms"] = round(idle_ping, 1)
        progress.advance(task)

        # Step 2-3: Download tests
        progress.update(task, description="Testing download speed...", info="downloading...")
        download_speeds = []

        for url, provider, size in SPEED_TEST_URLS:
            speed = _download_speed_test(url, size)
            if speed is not None:
                download_speeds.append(speed)
                progress.update(task, info=f"{speed} Mbps from {provider}")
            progress.advance(task)

        if download_speeds:
            results["download_mbps"] = round(max(download_speeds), 2)

        # Step 4: Upload test
        progress.update(task, description="Testing upload speed...", info="uploading...")
        upload = _upload_speed_test()
        if upload:
            results["upload_mbps"] = upload
        progress.advance(task)

        # Step 5: Bufferbloat (ping under load)
        progress.update(task, description="Checking bufferbloat...", info="ping under load")

        # Start a download in background and ping simultaneously
        load_pings = []
        download_thread_speeds = []

        def bg_download():
            for url, _, size in SPEED_TEST_URLS[:1]:
                s = _download_speed_test(url, size, timeout=10)
                if s:
                    download_thread_speeds.append(s)

        dl_thread = threading.Thread(target=bg_download, daemon=True)
        dl_thread.start()
        load_pings = _ping_during_load("8.8.8.8", duration=5.0)
        dl_thread.join(timeout=15)

        loaded_ping = statistics.mean(load_pings) if load_pings else 0
        results["loaded_ping_ms"] = round(loaded_ping, 1)

        bb_rating, bb_color = _bufferbloat_rating(idle_ping, loaded_ping)
        results["bufferbloat"] = bb_rating

        progress.update(task, completed=5,
                        description="[bold green]Speed test complete!",
                        info=f"↓{results['download_mbps']} Mbps ↑{results['upload_mbps']} Mbps")

    # Display results
    console.print()

    dl_rating, dl_color, dl_emoji = _speed_rating(results["download_mbps"])
    ul_rating, ul_color, ul_emoji = _speed_rating(results["upload_mbps"])
    bb_rating, bb_color = _bufferbloat_rating(results["idle_ping_ms"], results["loaded_ping_ms"])

    console.print(Panel(
        f"  [bold bright_white]Download Speed[/]\n"
        f"    [{dl_color}]{dl_emoji} {results['download_mbps']} Mbps — {dl_rating}[/]\n\n"
        f"  [bold bright_white]Upload Speed[/]\n"
        f"    [{ul_color}]{ul_emoji} {results['upload_mbps']} Mbps — {ul_rating}[/]\n\n"
        f"  [bold bright_white]Latency[/]\n"
        f"    Idle Ping  : [{ping_color(results['idle_ping_ms'])}]{results['idle_ping_ms']} ms[/]\n"
        f"    Under Load : [{ping_color(results['loaded_ping_ms'])}]{results['loaded_ping_ms']} ms[/]\n\n"
        f"  [bold bright_white]Bufferbloat[/]\n"
        f"    [{bb_color}]{results['bufferbloat']}[/]\n"
        f"    [dim](Ping increase under load: "
        f"{results['loaded_ping_ms'] - results['idle_ping_ms']:.0f}ms)[/]\n\n"
        f"  [bold bright_white]Gaming Requirements[/]\n"
        f"    [dim]< 5 Mbps[/] ❌ Gaming will suffer\n"
        f"    [dim]5-25 Mbps[/] ⚠️  Playable but may lag with others on network\n"
        f"    [dim]25-100 Mbps[/] ✅ Good for gaming\n"
        f"    [dim]100+ Mbps[/] 🚀 Excellent",
        title="[bold bright_magenta]⚡ Speed Test Results[/]",
        border_style="bright_magenta",
        box=box.DOUBLE_EDGE,
        padding=(1, 2),
    ))
    console.print()

    return results
