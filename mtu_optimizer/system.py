"""
mtu_optimizer.system — System and ISP detection
Auto-detects ISP, public IP, adapter details, VPN status, and OS info.
"""

import platform
import ctypes
import subprocess
import socket
import json
from typing import Optional

from mtu_optimizer.ui import console, Panel, box


def is_admin() -> bool:
    """Check if running with Administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def get_os_info() -> str:
    """Return a human-readable OS string."""
    return f"{platform.system()} {platform.release()} (Build {platform.version()})"


def get_public_ip_info() -> dict:
    """
    Fetch public IP + ISP info from ip-api.com.
    Returns dict with keys: ip, isp, org, city, country, regionName
    Falls back gracefully if requests is not installed or network is down.
    """
    try:
        import requests
        resp = requests.get("http://ip-api.com/json/", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            # Mask the IP for privacy: 41.xxx.xxx.23
            ip = data.get("query", "")
            if ip:
                parts = ip.split(".")
                if len(parts) == 4:
                    data["masked_ip"] = f"{parts[0]}.xxx.xxx.{parts[3]}"
                else:
                    data["masked_ip"] = ip
            return data
    except ImportError:
        pass
    except Exception:
        pass

    # Fallback: try socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return {"query": local_ip, "masked_ip": local_ip, "isp": "Unknown", "country": "Unknown"}
    except Exception:
        return {"query": "Unknown", "masked_ip": "Unknown", "isp": "Unknown", "country": "Unknown"}


def get_adapter_speed(adapter: str) -> str:
    """Get the link speed of the active adapter."""
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             f"(Get-NetAdapter -Name '{adapter}' -ErrorAction SilentlyContinue).LinkSpeed"],
            capture_output=True, text=True, timeout=5,
        )
        speed = result.stdout.strip()
        return speed if speed else "Unknown"
    except Exception:
        return "Unknown"


def get_connection_type(adapter: str) -> str:
    """Determine if the connection is Ethernet or Wi-Fi."""
    lower = adapter.lower()
    if "ethernet" in lower or "local" in lower:
        return "🔌 Ethernet"
    if "wi-fi" in lower or "wifi" in lower or "wireless" in lower:
        return "📶 Wi-Fi"
    return "🔗 Unknown"


def detect_vpn() -> tuple[bool, str]:
    """Check for active VPN connections."""
    vpn_adapters = []
    try:
        result = subprocess.run(
            ["netsh", "interface", "show", "interface"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines():
            lower = line.lower()
            if "connected" in lower and any(
                v in lower for v in ["vpn", "tap", "tun", "warp", "wireguard",
                                      "openvpn", "nordlynx", "proton"]
            ):
                parts = line.split()
                if len(parts) >= 4:
                    vpn_adapters.append(" ".join(parts[3:]))
    except Exception:
        pass

    # Also check for WARP
    try:
        r = subprocess.run(
            ["sc", "query", "CloudflareWARP"],
            capture_output=True, text=True, timeout=5,
        )
        if "RUNNING" in r.stdout:
            vpn_adapters.append("Cloudflare WARP")
    except Exception:
        pass

    if vpn_adapters:
        return True, ", ".join(vpn_adapters)
    return False, ""


def get_system_snapshot() -> dict:
    """Collect a full system snapshot for reports and profiles."""
    from mtu_optimizer.tweaks import get_active_adapter, get_current_mtu

    adapter = get_active_adapter()
    mtu = get_current_mtu(adapter)
    os_info = get_os_info()
    ip_info = get_public_ip_info()
    adapter_speed = get_adapter_speed(adapter)
    conn_type = get_connection_type(adapter)
    vpn_active, vpn_name = detect_vpn()

    return {
        "adapter": adapter,
        "mtu": mtu,
        "os": os_info,
        "isp": ip_info.get("isp", "Unknown"),
        "country": ip_info.get("country", "Unknown"),
        "city": ip_info.get("city", "Unknown"),
        "public_ip": ip_info.get("masked_ip", "Unknown"),
        "adapter_speed": adapter_speed,
        "connection_type": conn_type,
        "vpn_active": vpn_active,
        "vpn_name": vpn_name,
    }


def show_full_system_info() -> dict:
    """Display detailed system information panel and return the snapshot."""
    console.print("[dim]  Detecting system information...[/]")
    snapshot = get_system_snapshot()

    vpn_line = ""
    if snapshot["vpn_active"]:
        vpn_line = f"\n  🔒 VPN        : [bold green]{snapshot['vpn_name']}[/]"
    else:
        vpn_line = "\n  🔓 VPN        : [dim]None detected[/]"

    console.print(Panel(
        f"  🖥️  Adapter    : [cyan]{snapshot['adapter']}[/]\n"
        f"  📦 Current MTU : [yellow]{snapshot['mtu']}[/] bytes\n"
        f"  🖥️  OS         : [dim]{snapshot['os']}[/]\n"
        f"  🌐 ISP        : [cyan]{snapshot['isp']}[/]\n"
        f"  🏙️  Location   : [dim]{snapshot['city']}, {snapshot['country']}[/]\n"
        f"  🌍 Public IP  : [dim]{snapshot['public_ip']}[/]\n"
        f"  ⚡ Link Speed : [bold]{snapshot['adapter_speed']}[/]\n"
        f"  {snapshot['connection_type']}"
        f"{vpn_line}",
        title="[bold bright_white]🖥️  System Information[/]",
        border_style="bright_cyan",
        box=box.DOUBLE_EDGE,
        padding=(1, 2),
    ))
    console.print()
    return snapshot
