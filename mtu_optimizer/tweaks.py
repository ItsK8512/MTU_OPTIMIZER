"""
mtu_optimizer.tweaks — Windows network optimizations
Applies / restores MTU, Nagle, TCP tuning, RSS, QoS, DNS, routes, power management, and more.
"""

import re
import subprocess
from typing import Optional

from mtu_optimizer.servers import RIOT_IP_RANGES
from mtu_optimizer.ui import (
    console, ping_color, make_progress, Panel, Rule, Text, box,
    TextColumn, Confirm,
)
from mtu_optimizer.dns import DnsResult


# ── System helpers ────────────────────────────────────────────────────────────
def get_active_adapter() -> str:
    """Return the name of the first active network adapter."""
    try:
        result = subprocess.run(
            ["netsh", "interface", "show", "interface"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines():
            if "Connected" in line and ("Ethernet" in line or "Wi-Fi" in line or "Local" in line):
                parts = line.split()
                return " ".join(parts[3:])
    except Exception:
        pass
    return "Wi-Fi"


def get_current_mtu(adapter: str) -> int:
    """Read current MTU for the adapter."""
    try:
        result = subprocess.run(
            ["netsh", "interface", "ipv4", "show", "subinterface", adapter],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if parts and parts[0].isdigit():
                return int(parts[0])
    except Exception:
        pass
    return 1500


# ── Individual tweaks ─────────────────────────────────────────────────────────
def apply_mtu(adapter: str, mtu: int) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["netsh", "interface", "ipv4", "set", "subinterface",
             adapter, f"mtu={mtu}", "store=persistent"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return True, f"MTU set to {mtu} on '{adapter}'"
        return False, result.stderr.strip() or result.stdout.strip()
    except Exception as e:
        return False, str(e)


def disable_nagle() -> tuple[bool, str]:
    """Disable Nagle's algorithm via registry (reduces TCP latency)."""
    try:
        import winreg
        key_path = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
        base = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        count = winreg.QueryInfoKey(base)[0]
        modified = 0
        for i in range(count):
            sub_name = winreg.EnumKey(base, i)
            try:
                sub_key = winreg.OpenKey(base, sub_name, 0, winreg.KEY_ALL_ACCESS)
                winreg.SetValueEx(sub_key, "TcpAckFrequency", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(sub_key, "TCPNoDelay", 0, winreg.REG_DWORD, 1)
                winreg.CloseKey(sub_key)
                modified += 1
            except Exception:
                pass
        winreg.CloseKey(base)
        return True, f"Nagle disabled on {modified} interface(s)"
    except Exception as e:
        return False, str(e)


def disable_auto_tuning() -> tuple[bool, str]:
    """Disable TCP receive window auto-tuning."""
    try:
        result = subprocess.run(
            ["netsh", "int", "tcp", "set", "global", "autotuninglevel=disabled"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return True, "TCP auto-tuning disabled"
        return False, result.stderr.strip()
    except Exception as e:
        return False, str(e)


def enable_rss() -> tuple[bool, str]:
    """Enable Receive Side Scaling for better multi-core network processing."""
    try:
        result = subprocess.run(
            ["netsh", "int", "tcp", "set", "global", "rss=enabled"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return True, "RSS (Receive Side Scaling) enabled"
        return False, result.stderr.strip()
    except Exception as e:
        return False, str(e)


def set_dns_cloudflare(adapter: str) -> tuple[bool, str]:
    """Set DNS to Cloudflare 1.1.1.1."""
    try:
        r1 = subprocess.run(
            ["netsh", "interface", "ipv4", "set", "dnsservers",
             adapter, "static", "1.1.1.1", "primary"],
            capture_output=True, text=True, timeout=10,
        )
        subprocess.run(
            ["netsh", "interface", "ipv4", "add", "dnsservers",
             adapter, "1.0.0.1", "index=2"],
            capture_output=True, text=True, timeout=10,
        )
        if r1.returncode == 0:
            return True, "DNS set to Cloudflare (1.1.1.1 / 1.0.0.1)"
        return False, r1.stderr.strip()
    except Exception as e:
        return False, str(e)


def set_dns_custom(adapter: str, primary: str, secondary: str, label: str) -> tuple[bool, str]:
    """Apply any DNS server pair."""
    try:
        r1 = subprocess.run(
            ["netsh", "interface", "ipv4", "set", "dnsservers",
             adapter, "static", primary, "primary"],
            capture_output=True, text=True, timeout=10,
        )
        if r1.returncode != 0:
            return False, r1.stderr.strip() or r1.stdout.strip()
        if secondary and secondary != primary:
            subprocess.run(
                ["netsh", "interface", "ipv4", "add", "dnsservers",
                 adapter, secondary, "index=2"],
                capture_output=True, text=True, timeout=10,
            )
        return True, f"DNS set to {label} ({primary} / {secondary})"
    except Exception as e:
        return False, str(e)


def flush_dns() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["ipconfig", "/flushdns"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return True, "DNS cache flushed"
        return False, result.stderr.strip()
    except Exception as e:
        return False, str(e)


def set_qos_dscp() -> tuple[bool, str]:
    """Enable QoS DSCP marking (Expedited Forwarding)."""
    try:
        import winreg
        key_path = r"SOFTWARE\Policies\Microsoft\Windows\QoS"
        key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        winreg.SetValueEx(key, "Application Name", 0, winreg.REG_SZ, "*")
        winreg.SetValueEx(key, "Version", 0, winreg.REG_SZ, "1.0")
        winreg.SetValueEx(key, "Protocol", 0, winreg.REG_SZ, "*")
        winreg.SetValueEx(key, "Local Port", 0, winreg.REG_SZ, "*")
        winreg.SetValueEx(key, "Local IP", 0, winreg.REG_SZ, "*")
        winreg.SetValueEx(key, "Remote Port", 0, winreg.REG_SZ, "*")
        winreg.SetValueEx(key, "Remote IP", 0, winreg.REG_SZ, "*")
        winreg.SetValueEx(key, "DSCP Value", 0, winreg.REG_SZ, "46")
        winreg.SetValueEx(key, "Throttle Rate", 0, winreg.REG_SZ, "-1")
        winreg.CloseKey(key)
        return True, "QoS DSCP marking set to 46 (Expedited Forwarding)"
    except Exception as e:
        return False, str(e)


def disable_nic_power_saving(adapter: str) -> tuple[bool, str]:
    """Disable power management on the network adapter."""
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             f"Get-NetAdapter -Name '{adapter}' | "
             f"Set-NetAdapterPowerManagement -WakeOnMagicPacket Disabled "
             f"-WakeOnPattern Disabled -ErrorAction SilentlyContinue; "
             f"Write-Output 'OK'"],
            capture_output=True, text=True, timeout=10,
        )
        if "OK" in result.stdout:
            return True, f"NIC power saving disabled on '{adapter}'"
        return False, result.stderr.strip() or "Power management change failed"
    except Exception as e:
        return False, str(e)


def set_tcp_congestion_provider() -> tuple[bool, str]:
    """Set TCP congestion provider to CTCP for better gaming throughput."""
    try:
        result = subprocess.run(
            ["netsh", "int", "tcp", "set", "supplemental", "template=Internet",
             "congestionprovider=ctcp"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return True, "TCP congestion provider set to CTCP"
        # Fallback for older Windows
        result2 = subprocess.run(
            ["netsh", "int", "tcp", "set", "global", "congestionprovider=ctcp"],
            capture_output=True, text=True, timeout=10,
        )
        if result2.returncode == 0:
            return True, "TCP congestion provider set to CTCP"
        return False, result.stderr.strip() or result2.stderr.strip()
    except Exception as e:
        return False, str(e)


def enable_game_mode() -> tuple[bool, str]:
    """Ensure Windows Game Mode is enabled."""
    try:
        import winreg
        key_path = r"SOFTWARE\Microsoft\GameBar"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
        except FileNotFoundError:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
        winreg.SetValueEx(key, "AllowAutoGameMode", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "AutoGameModeEnabled", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key)
        return True, "Windows Game Mode enabled"
    except Exception as e:
        return False, str(e)


def disable_focus_assist() -> tuple[bool, str]:
    """Disable Focus Assist (notification silencing during gaming)."""
    try:
        import winreg
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Notifications\Settings"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
        except FileNotFoundError:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
        winreg.SetValueEx(key, "NOC_GLOBAL_SETTING_TOASTS_ENABLED", 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key)
        return True, "Focus Assist set to disable notifications during gaming"
    except Exception as e:
        return False, str(e)


# ── Restore defaults ─────────────────────────────────────────────────────────
def restore_defaults(adapter: str) -> list[tuple[bool, str]]:
    """Restore network settings to Windows defaults."""
    results = []

    ok, msg = apply_mtu(adapter, 1500)
    results.append((ok, f"MTU → 1500: {msg}"))

    try:
        r = subprocess.run(
            ["netsh", "int", "tcp", "set", "global", "autotuninglevel=normal"],
            capture_output=True, text=True, timeout=10,
        )
        results.append((r.returncode == 0, "TCP auto-tuning → normal"))
    except Exception as e:
        results.append((False, str(e)))

    try:
        import winreg
        key_path = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
        base = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        count = winreg.QueryInfoKey(base)[0]
        for i in range(count):
            sub_name = winreg.EnumKey(base, i)
            try:
                sub_key = winreg.OpenKey(base, sub_name, 0, winreg.KEY_ALL_ACCESS)
                try:
                    winreg.DeleteValue(sub_key, "TcpAckFrequency")
                except FileNotFoundError:
                    pass
                try:
                    winreg.DeleteValue(sub_key, "TCPNoDelay")
                except FileNotFoundError:
                    pass
                winreg.CloseKey(sub_key)
            except Exception:
                pass
        winreg.CloseKey(base)
        results.append((True, "Nagle's algorithm re-enabled"))
    except Exception as e:
        results.append((False, str(e)))

    try:
        r = subprocess.run(
            ["netsh", "interface", "ipv4", "set", "dnsservers", adapter, "dhcp"],
            capture_output=True, text=True, timeout=10,
        )
        results.append((r.returncode == 0, "DNS → DHCP (automatic)"))
    except Exception as e:
        results.append((False, str(e)))

    flush_dns()
    results.append((True, "DNS cache flushed"))
    return results


# ── Route injection ──────────────────────────────────────────────────────────
def inject_riot_routes() -> list[tuple[bool, str]]:
    """Add persistent static routes for Riot IP ranges with metric 1."""
    gateway = None
    try:
        r = subprocess.run(
            ["route", "print", "0.0.0.0"],
            capture_output=True, text=True, timeout=5,
        )
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[0] == "0.0.0.0" and parts[1] == "0.0.0.0":
                gateway = parts[2]
                break
    except Exception:
        pass

    if not gateway:
        return [(False, "Could not determine default gateway")]

    results = [(True, f"Default gateway: {gateway}")]

    for cidr in RIOT_IP_RANGES:
        try:
            ip_net = cidr.split("/")
            network = ip_net[0]
            prefix = int(ip_net[1])
            mask_int = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
            mask = ".".join(str((mask_int >> (8 * i)) & 0xFF) for i in reversed(range(4)))

            r = subprocess.run(
                ["route", "add", network, "mask", mask, gateway, "metric", "1", "-p"],
                capture_output=True, text=True, timeout=5,
            )
            ok = r.returncode == 0
            msg = f"Route {cidr} via {gateway}" + (" added" if ok else f" FAILED: {r.stderr.strip()}")
            results.append((ok, msg))
        except Exception as e:
            results.append((False, f"{cidr}: {e}"))

    return results


# ── Traceroute ────────────────────────────────────────────────────────────────
def run_traceroute(target_ip: str = "99.83.199.240", region: str = "ME - Bahrain") -> None:
    """Run tracert and display hop path with latency analysis."""
    console.print(Rule(f"[bold red]🛣️  Traceroute to {region} ({target_ip})[/]", style="red"))
    console.print()
    console.print(f"  [dim]Running: tracert -d -h 20 -w 1000 {target_ip}[/]")
    console.print(f"  [dim]This shows the exact path your packets take.[/]")
    console.print()

    from rich.table import Table as RichTable

    table = RichTable(
        box=box.SIMPLE_HEAVY, border_style="dim",
        header_style="bold white", show_footer=False, expand=False,
    )
    table.add_column("Hop", justify="right", style="dim", min_width=4)
    table.add_column("IP Address", min_width=18)
    table.add_column("RTT 1", justify="right", min_width=8)
    table.add_column("RTT 2", justify="right", min_width=8)
    table.add_column("RTT 3", justify="right", min_width=8)
    table.add_column("Note", style="dim")

    try:
        proc = subprocess.Popen(
            ["tracert", "-d", "-h", "20", "-w", "1000", target_ip],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
        )

        hop_re = re.compile(
            r"^\s*(\d+)\s+"
            r"([\d<*\s]+ms[\d<*\s]*ms[\d<*\s]*ms|\*\s+\*\s+\*)"
            r"\s+([\d\.]+|Request timed out)"
        )
        rtt_re = re.compile(r"(\d+)\s*ms|\*")

        for line in proc.stdout:
            line = line.rstrip()
            m = hop_re.match(line)
            if not m:
                continue
            hop_idx = m.group(1)
            ip_part = m.group(3).strip()

            rtts = rtt_re.findall(line.replace(ip_part, ""))
            rtt_strs = []
            rtt_vals = []
            for r in rtts[:3]:
                if r and r != "*":
                    rtt_vals.append(int(r))
                    color = ping_color(int(r))
                    rtt_strs.append(f"[{color}]{r} ms[/]")
                else:
                    rtt_strs.append("[dim]*[/]")

            while len(rtt_strs) < 3:
                rtt_strs.append("[dim]*[/]")

            avg_rtt = sum(rtt_vals) / len(rtt_vals) if rtt_vals else -1
            note = ""
            if ip_part == "Request timed out" or not rtt_vals:
                ip_part = "* * *"
                note = "[dim]filtered[/]"
            elif avg_rtt > 200:
                note = "[red]high latency hop[/]"
            elif avg_rtt > 100:
                note = "[yellow]moderate[/]"

            table.add_row(hop_idx, f"[cyan]{ip_part}[/]",
                          rtt_strs[0], rtt_strs[1], rtt_strs[2], note)

        proc.wait(timeout=5)
    except Exception as e:
        console.print(f"  [red]Traceroute failed: {e}[/]")
        return

    console.print(table)
    console.print()
    console.print(Panel(
        "  [bold white]How to read this:[/]\n"
        "  - Each line is a [bold]router hop[/] your packet goes through\n"
        "  - [bold bright_green]< 50ms per hop[/] = good  |  [bold yellow]> 100ms[/] = bad routing\n"
        "  - [bold]* * *[/] = that router blocks ping probes (normal)\n\n"
        "  [bold yellow]Tip:[/] If you see hops going through unexpected countries,\n"
        "  try [bold cyan]Cloudflare WARP[/] (one.one.one.one/warp) — it often fixes this.",
        border_style="dim", box=box.ROUNDED,
    ))
    console.print()


# ── WARP check ────────────────────────────────────────────────────────────────
def check_warp() -> None:
    """Detect if Cloudflare WARP is installed/running and show guidance."""
    console.print(Rule("[bold red]☁️  Cloudflare WARP Check[/]", style="red"))
    console.print()

    warp_running = False
    warp_installed = False

    try:
        r = subprocess.run(
            ["sc", "query", "CloudflareWARP"],
            capture_output=True, text=True, timeout=5,
        )
        if "RUNNING" in r.stdout:
            warp_running = True
            warp_installed = True
        elif "STOPPED" in r.stdout or "FAILED" in r.stdout:
            warp_installed = True
    except Exception:
        pass

    if not warp_installed:
        try:
            r = subprocess.run(
                ["warp-cli", "--version"],
                capture_output=True, text=True, timeout=3,
            )
            if r.returncode == 0:
                warp_installed = True
        except Exception:
            pass

    if warp_running:
        console.print(Panel(
            "  ✅ [bold green]Cloudflare WARP is running![/]\n\n"
            "  Your traffic is being routed through Cloudflare's network.\n"
            "  Compare your game ping with WARP ON vs OFF to see if it helps.",
            title="[bold green]WARP Status[/]",
            border_style="green", box=box.ROUNDED,
        ))
    elif warp_installed:
        console.print(Panel(
            "  ⚠️  [bold yellow]Cloudflare WARP is installed but NOT running.[/]\n"
            "  Open the WARP app in your system tray and enable it to test.",
            border_style="yellow", box=box.ROUNDED,
        ))
    else:
        console.print(Panel(
            "  [bold white]Cloudflare WARP is NOT installed.[/]\n\n"
            "  WARP is a [bold]free[/] VPN by Cloudflare that can reduce\n"
            "  ping by fixing bad ISP routing paths.\n\n"
            "  [bold cyan]How to get it:[/]\n"
            "  1. Go to: [link=https://one.one.one.one/]https://one.one.one.one/[/link]\n"
            "  2. Download WARP for Windows\n"
            "  3. Install & toggle it on\n"
            "  4. Test your game ping — compare with WARP on/off\n\n"
            "  [bold yellow]Note:[/] Vanguard allows WARP — it is NOT a ban risk.",
            title="[bold cyan]WARP Recommendation[/]",
            border_style="cyan", box=box.ROUNDED,
        ))
    console.print()


# ── Route optimizer UI ────────────────────────────────────────────────────────
def run_route_optimizer() -> None:
    """UI wrapper for route injection."""
    console.print(Rule("[bold red]🗺️  Riot Route Optimizer[/]", style="red"))
    console.print()
    console.print(
        "  This injects [bold]persistent static routes[/] for all Riot IP ranges\n"
        "  so your OS always uses the best local gateway for game traffic.\n"
        "  [dim](Uses Windows 'route add -p' — persists across reboots)[/]\n"
    )

    results = inject_riot_routes()
    for ok, msg in results:
        icon = "✅" if ok else "❌"
        color = "green" if ok else "red"
        console.print(f"  {icon} [{color}]{msg}[/{color}]")

    console.print()
    console.print(Panel(
        "  [bold white]Route injection complete.[/]\n"
        "  [bold yellow]Note:[/] This fixes LOCAL routing (which interface your PC uses).\n"
        "  It does NOT change your ISP's routing path (only WARP/VPN can do that).",
        border_style="dim", box=box.ROUNDED,
    ))
    console.print()


# ── Apply all tweaks ─────────────────────────────────────────────────────────
def run_tweaks(adapter: str, mtu: int, dns: bool = True,
               best_dns: Optional[DnsResult] = None) -> list[tuple[bool, str]]:
    """Apply all network optimizations."""
    console.print(Rule("[bold red]⚙️  Applying Network Tweaks[/]", style="red"))
    console.print()

    tweaks_to_run = [
        ("Setting optimal MTU",            lambda: apply_mtu(adapter, mtu)),
        ("Disabling Nagle's algorithm",    disable_nagle),
        ("Disabling TCP auto-tuning",      disable_auto_tuning),
        ("Enabling RSS",                   enable_rss),
        ("Setting QoS DSCP priority",      set_qos_dscp),
        ("Setting TCP congestion (CTCP)",  set_tcp_congestion_provider),
        ("Enabling Windows Game Mode",     enable_game_mode),
        ("Disabling NIC power saving",     lambda: disable_nic_power_saving(adapter)),
    ]
    if dns:
        if best_dns and best_dns.avg_ms >= 0:
            tweaks_to_run.append((
                f"Setting DNS to {best_dns.name} ({best_dns.primary})",
                lambda d=best_dns: set_dns_custom(adapter, d.primary, d.secondary, d.name),
            ))
        else:
            tweaks_to_run.append(("Setting DNS to Cloudflare 1.1.1.1",
                                  lambda: set_dns_cloudflare(adapter)))
    tweaks_to_run.append(("Flushing DNS cache", flush_dns))

    results = []
    with make_progress(bar_color="red", extra_columns=[
        TextColumn("[dim]{task.completed}/{task.total}[/dim]"),
    ]) as progress:
        task = progress.add_task("Applying tweaks...", total=len(tweaks_to_run))

        for name, fn in tweaks_to_run:
            progress.update(task, description=name + "...")
            import time
            time.sleep(0.3)
            try:
                ok, msg = fn()
            except Exception as e:
                ok, msg = False, str(e)

            icon = "✅" if ok else "❌"
            color = "green" if ok else "red"
            console.print(f"  {icon} [{color}]{msg}[/{color}]")
            results.append((ok, msg))
            progress.advance(task)

    console.print()
    return results
