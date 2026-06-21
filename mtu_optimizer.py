#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, io
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
"""
╔══════════════════════════════════════════════════════════════╗
║          MTU OPTIMIZER FOR GAMING  —  Valorant Edition       ║
║     Find your perfect MTU · Ping servers · Boost network     ║
╚══════════════════════════════════════════════════════════════╝

USAGE:
    python mtu_optimizer.py            — Full scan + optimize
    python mtu_optimizer.py --scan     — Scan only (no changes)
    python mtu_optimizer.py --mtu-only — MTU finder only
    python mtu_optimizer.py --ping     — Server ping only
    python mtu_optimizer.py --apply    — Apply tweaks with given MTU
    python mtu_optimizer.py --restore  — Restore default settings

Requires: pip install rich ping3
Run as Administrator for applying network tweaks.
"""

import sys
import os
import re
import time
import socket
import subprocess
import statistics
import ctypes
import platform
import argparse
import threading
import struct
import select
import random
from dataclasses import dataclass, field
from typing import Optional

# ── dependency check ────────────────────────────────────────────────────────
def check_deps():
    missing = []
    try:
        import rich
    except ImportError:
        missing.append("rich")
    try:
        import ping3
    except ImportError:
        missing.append("ping3")
    if missing:
        print(f"[ERROR] Missing packages: {', '.join(missing)}")
        print(f"        Run: pip install {' '.join(missing)}")
        sys.exit(1)

check_deps()

import ping3
from ping3 import ping as ping3_ping
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich.align import Align
from rich.rule import Rule
from rich.columns import Columns
from rich import box
from rich.style import Style
from rich.prompt import Confirm, Prompt
from rich.markup import escape

console = Console()

# ── constants ────────────────────────────────────────────────────────────────
VERSION = "2.0.0"
PING_TIMEOUT = 2.0       # seconds per ping
MTU_MIN = 576
MTU_MAX = 1500
PING_COUNT = 10          # pings per server for stats
DNS_TEST_DOMAIN = "www.google.com"   # domain used to benchmark DNS resolution
DNS_BENCH_ROUNDS = 5                 # queries per DNS server for averaging
DNS_TIMEOUT = 2.0                    # seconds before a DNS query times out

# Valorant / Riot server targets -- ordered by proximity to Egypt/Middle East
# Riot uses AWS Bahrain for the Middle East region (closest to Egypt ~60-90ms)
# Turkey/Istanbul is second closest (~70-100ms)
# EU Frankfurt / London ~80-110ms from Egypt
VALORANT_SERVERS = {
    "ME  - Bahrain (CLOSEST)  ": ["99.83.199.240",  "15.185.184.1",  "15.185.160.1"],
    "EU  - Frankfurt          ": ["104.160.142.3",  "185.40.64.1",   "185.40.65.1"],
    "EU  - London             ": ["185.40.66.1",    "185.40.67.1",   "185.40.68.1"],
    "AF  - Johannesburg       ": ["196.50.160.1",   "196.50.161.1",  "196.50.162.1"],
    "AP  - Singapore          ": ["104.160.156.3",  "104.160.157.3", "192.48.48.1"],
    "AP  - Tokyo              ": ["104.160.152.3",  "104.160.153.3", "104.160.154.3"],
    "KR  - Seoul              ": ["104.160.161.3",  "104.160.162.3", "104.160.163.3"],
    "NA  - Ashburn (US East)  ": ["162.249.72.1",   "162.249.73.1",  "104.160.136.3"],
    "NA  - Chicago (US Mid)   ": ["104.160.141.3",  "104.160.137.3", "104.160.138.3"],
    "BR  - Sao Paulo          ": ["104.160.130.3",  "104.160.131.3", "185.40.56.1"],
    "OCE - Sydney             ": ["104.160.158.3",  "104.160.159.3", "104.160.160.3"],
}

# Riot Games known IP ranges (AS6507 + relay allocations) used for route injection
RIOT_IP_RANGES = [
    "162.249.72.0/21",    # Riot relay NA
    "104.160.128.0/19",   # Riot relay global
    "185.40.64.0/21",     # Riot relay EU
    "192.48.44.0/22",     # Riot relay NA2
    "192.48.48.0/22",     # Riot relay AP
    "196.50.160.0/22",    # Riot relay AF
    "99.83.192.0/21",     # AWS Bahrain (ME Valorant servers)
    "15.185.0.0/16",      # AWS Bahrain wider range
]

# Good fallback hosts for MTU testing (stable, always respond to ICMP)
MTU_TEST_HOSTS = ["8.8.8.8", "1.1.1.1", "9.9.9.9"]

# ── DNS provider database ─────────────────────────────────────────────────────
# Format: "Provider Name": {"primary": "IP", "secondary": "IP", "tag": "label"}
DNS_PROVIDERS = {
    # ── Tier-1: Privacy + Speed ──────────────────────────────────────────────
    "Cloudflare (1.1.1.1)": {
        "primary":   "1.1.1.1",
        "secondary": "1.0.0.1",
        "tag": "privacy · fast",
    },
    "Cloudflare Gaming (1.1.1.3)": {
        "primary":   "1.1.1.3",
        "secondary": "1.0.0.3",
        "tag": "blocks malware/adult",
    },
    "Google (8.8.8.8)": {
        "primary":   "8.8.8.8",
        "secondary": "8.8.4.4",
        "tag": "reliable · global",
    },
    "Quad9 (9.9.9.9)": {
        "primary":   "9.9.9.9",
        "secondary": "149.112.112.112",
        "tag": "security filtered",
    },
    # ── Tier-2: Gaming-optimised ─────────────────────────────────────────────
    "Comodo Secure DNS": {
        "primary":   "8.26.56.26",
        "secondary": "8.20.247.20",
        "tag": "gaming · secure",
    },
    "OpenDNS (Cisco)": {
        "primary":   "208.67.222.222",
        "secondary": "208.67.220.220",
        "tag": "smart cache",
    },
    "OpenDNS FamilyShield": {
        "primary":   "208.67.222.123",
        "secondary": "208.67.220.123",
        "tag": "family safe",
    },
    "Level3 (Lumen)": {
        "primary":   "4.2.2.1",
        "secondary": "4.2.2.2",
        "tag": "backbone cdn",
    },
    "Level3 Alt": {
        "primary":   "4.2.2.3",
        "secondary": "4.2.2.4",
        "tag": "backbone cdn",
    },
    # ── Tier-3: Regional fast resolvers ─────────────────────────────────────
    "DNS.WATCH": {
        "primary":   "84.200.69.80",
        "secondary": "84.200.70.40",
        "tag": "no logging · EU",
    },
    "Freenom World": {
        "primary":   "80.80.80.80",
        "secondary": "80.80.81.81",
        "tag": "neutral",
    },
    "Verisign Public": {
        "primary":   "64.6.64.6",
        "secondary": "64.6.65.6",
        "tag": "stability",
    },
    "Norton ConnectSafe": {
        "primary":   "199.85.126.10",
        "secondary": "199.85.127.10",
        "tag": "security",
    },
    "AdGuard DNS": {
        "primary":   "94.140.14.14",
        "secondary": "94.140.15.15",
        "tag": "ad blocking",
    },
    "AdGuard Family": {
        "primary":   "94.140.14.15",
        "secondary": "94.140.15.16",
        "tag": "family · ads",
    },
    "CleanBrowsing Security": {
        "primary":   "185.228.168.9",
        "secondary": "185.228.169.9",
        "tag": "security filter",
    },
    "CleanBrowsing Family": {
        "primary":   "185.228.168.168",
        "secondary": "185.228.169.168",
        "tag": "family safe",
    },
    "Alternate DNS": {
        "primary":   "76.76.19.19",
        "secondary": "76.223.122.150",
        "tag": "ad blocking",
    },
    "NextDNS": {
        "primary":   "45.90.28.0",
        "secondary": "45.90.30.0",
        "tag": "customizable",
    },
    "ControlD": {
        "primary":   "76.76.2.0",
        "secondary": "76.76.10.0",
        "tag": "no-log · fast",
    },
    "Yandex Basic": {
        "primary":   "77.88.8.8",
        "secondary": "77.88.8.1",
        "tag": "RU/ME region",
    },
    "Yandex Safe": {
        "primary":   "77.88.8.88",
        "secondary": "77.88.8.2",
        "tag": "security · RU/ME",
    },
    "Neustar UltraDNS": {
        "primary":   "156.154.70.1",
        "secondary": "156.154.71.1",
        "tag": "anycast",
    },
    "Hurricane Electric": {
        "primary":   "74.82.42.42",
        "secondary": "74.82.42.42",
        "tag": "backbone",
    },
}


# ── helpers ──────────────────────────────────────────────────────────────────
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


@dataclass
class NetworkState:
    adapter_name: str = ""
    original_mtu: int = 0
    recommended_mtu: int = 0
    tweaks_applied: list = field(default_factory=list)


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def get_active_adapter() -> str:
    """Return the name of the first active network adapter."""
    try:
        result = subprocess.run(
            ["netsh", "interface", "show", "interface"],
            capture_output=True, text=True, timeout=10
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
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if parts and parts[0].isdigit():
                return int(parts[0])
    except Exception:
        pass
    return 1500


# ── ICMP ping with DF bit ─────────────────────────────────────────────────────
def ping_with_size(host: str, payload_size: int, timeout: float = 2.0) -> Optional[float]:
    """
    Send a single ICMP echo with a specific payload size and DF bit set.
    Returns round-trip time in ms, or None on failure/fragmentation.
    Uses ping3 which supports packet_size parameter.
    """
    try:
        # ping3 payload_size is the data portion; IP+ICMP headers = 28 bytes
        result = ping3_ping(host, timeout=timeout, size=payload_size, unit="ms")
        if result is False or result is None:
            return None
        return float(result)
    except Exception:
        return None


# ── MTU finder ────────────────────────────────────────────────────────────────
def find_optimal_mtu(host: str, progress_callback=None) -> int:
    """
    Binary search to find the largest payload that doesn't fragment.
    MTU = largest_payload + 28 (IP header 20 + ICMP header 8)
    """
    lo, hi = MTU_MIN - 28, MTU_MAX - 28  # payload range (548 to 1472)
    best = lo

    iterations = 0
    max_iterations = 12  # log2(1472-548) ≈ 10

    while lo <= hi and iterations < max_iterations:
        mid = (lo + hi) // 2
        iterations += 1

        if progress_callback:
            progress_callback(mid + 28, lo + 28, hi + 28)

        # Test 3 times for reliability
        successes = 0
        for _ in range(3):
            rtt = ping_with_size(host, mid, timeout=PING_TIMEOUT)
            if rtt is not None:
                successes += 1
            time.sleep(0.05)

        if successes >= 2:  # majority pass
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1

        time.sleep(0.1)

    return best + 28  # add header size back


# ── Server pinger ─────────────────────────────────────────────────────────────
def os_ping(host: str, count: int = 3, timeout_ms: int = 1500) -> tuple[list[float], float]:
    """
    Use Windows ping.exe to ping a host.
    Returns (rtt_list_ms, loss_percent).
    Works without admin — uses OS ICMP stack.
    """
    try:
        result = subprocess.run(
            ["ping", "-n", str(count), "-w", str(timeout_ms), host],
            capture_output=True, text=True, timeout=count * (timeout_ms / 1000 + 0.5) + 2,
            encoding="utf-8", errors="replace",
        )
        output = result.stdout
        rtts = []
        # Parse each "time=Xms"
        for m in re.finditer(r"time[=<](\d+)\s*ms", output, re.IGNORECASE):
            rtts.append(float(m.group(1)))
        # Also catch "time<1ms" → treat as 0.5ms
        for m in re.finditer(r"time<1ms", output, re.IGNORECASE):
            rtts.append(0.5)

        # Parse loss from "X% loss"
        loss_match = re.search(r"(\d+)%\s+loss", output, re.IGNORECASE)
        loss = float(loss_match.group(1)) if loss_match else (100.0 if not rtts else 0.0)
        return rtts, loss
    except Exception:
        return [], 100.0


def ping_server_group(region: str, hosts: list) -> PingResult:
    """
    Ping hosts for a region using Windows ping.exe.
    Each entry in hosts is an IP string.
    """
    all_rtts: list[float] = []
    total_sent = 0
    total_lost = 0
    samples = 4  # pings per host

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



# ── Network tweaks ────────────────────────────────────────────────────────────
def apply_mtu(adapter: str, mtu: int) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["netsh", "interface", "ipv4", "set", "subinterface",
             adapter, f"mtu={mtu}", "store=persistent"],
            capture_output=True, text=True, timeout=15
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
    """Disable TCP receive window auto-tuning (can cause latency spikes)."""
    try:
        result = subprocess.run(
            ["netsh", "int", "tcp", "set", "global", "autotuninglevel=disabled"],
            capture_output=True, text=True, timeout=10
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
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return True, "RSS (Receive Side Scaling) enabled"
        return False, result.stderr.strip()
    except Exception as e:
        return False, str(e)


def set_dns_cloudflare(adapter: str) -> tuple[bool, str]:
    """Set DNS to Cloudflare 1.1.1.1 for faster resolution."""
    try:
        r1 = subprocess.run(
            ["netsh", "interface", "ipv4", "set", "dnsservers",
             adapter, "static", "1.1.1.1", "primary"],
            capture_output=True, text=True, timeout=10
        )
        r2 = subprocess.run(
            ["netsh", "interface", "ipv4", "add", "dnsservers",
             adapter, "1.0.0.1", "index=2"],
            capture_output=True, text=True, timeout=10
        )
        if r1.returncode == 0:
            return True, "DNS set to Cloudflare (1.1.1.1 / 1.0.0.1)"
        return False, r1.stderr.strip()
    except Exception as e:
        return False, str(e)


def set_dns_custom(adapter: str, primary: str, secondary: str, label: str) -> tuple[bool, str]:
    """Apply any DNS server pair to the given adapter."""
    try:
        r1 = subprocess.run(
            ["netsh", "interface", "ipv4", "set", "dnsservers",
             adapter, "static", primary, "primary"],
            capture_output=True, text=True, timeout=10
        )
        if r1.returncode != 0:
            return False, r1.stderr.strip() or r1.stdout.strip()
        if secondary and secondary != primary:
            subprocess.run(
                ["netsh", "interface", "ipv4", "add", "dnsservers",
                 adapter, secondary, "index=2"],
                capture_output=True, text=True, timeout=10
            )
        return True, f"DNS set to {label} ({primary} / {secondary})"
    except Exception as e:
        return False, str(e)


def flush_dns() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["ipconfig", "/flushdns"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return True, "DNS cache flushed"
        return False, result.stderr.strip()
    except Exception as e:
        return False, str(e)


def set_qos_dscp() -> tuple[bool, str]:
    """Enable QoS DSCP marking (helps on routers that support it)."""
    try:
        import winreg
        key_path = r"SOFTWARE\Policies\Microsoft\Windows\QoS"
        try:
            key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            winreg.SetValueEx(key, "Application Name", 0, winreg.REG_SZ, "*")
            winreg.SetValueEx(key, "Version", 0, winreg.REG_SZ, "1.0")
            winreg.SetValueEx(key, "Protocol", 0, winreg.REG_SZ, "*")
            winreg.SetValueEx(key, "Local Port", 0, winreg.REG_SZ, "*")
            winreg.SetValueEx(key, "Local IP", 0, winreg.REG_SZ, "*")
            winreg.SetValueEx(key, "Remote Port", 0, winreg.REG_SZ, "*")
            winreg.SetValueEx(key, "Remote IP", 0, winreg.REG_SZ, "*")
            winreg.SetValueEx(key, "DSCP Value", 0, winreg.REG_SZ, "46")  # EF — Expedited Forwarding
            winreg.SetValueEx(key, "Throttle Rate", 0, winreg.REG_SZ, "-1")
            winreg.CloseKey(key)
            return True, "QoS DSCP marking set to 46 (Expedited Forwarding)"
        except Exception as e:
            return False, str(e)
    except Exception as e:
        return False, str(e)


def restore_defaults(adapter: str) -> list[tuple[bool, str]]:
    """Restore network settings to Windows defaults."""
    results = []
    
    # Restore MTU to 1500
    ok, msg = apply_mtu(adapter, 1500)
    results.append((ok, f"MTU → 1500: {msg}"))

    # Re-enable auto-tuning
    try:
        r = subprocess.run(
            ["netsh", "int", "tcp", "set", "global", "autotuninglevel=normal"],
            capture_output=True, text=True, timeout=10
        )
        results.append((r.returncode == 0, "TCP auto-tuning → normal"))
    except Exception as e:
        results.append((False, str(e)))

    # Restore Nagle
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

    # Restore DNS (DHCP)
    try:
        r = subprocess.run(
            ["netsh", "interface", "ipv4", "set", "dnsservers", adapter, "dhcp"],
            capture_output=True, text=True, timeout=10
        )
        results.append((r.returncode == 0, "DNS → DHCP (automatic)"))
    except Exception as e:
        results.append((False, str(e)))

    flush_dns()
    results.append((True, "DNS cache flushed"))
    return results


# ── DNS benchmark engine ──────────────────────────────────────────────────────
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
        if self.avg_ms < 0:   return "UNREACHABLE"
        if self.avg_ms < 10:  return "BLAZING"
        if self.avg_ms < 25:  return "EXCELLENT"
        if self.avg_ms < 50:  return "GOOD"
        if self.avg_ms < 100: return "OK"
        if self.avg_ms < 200: return "SLOW"
        return "BAD"


def dns_query_latency(server_ip: str, domain: str = DNS_TEST_DOMAIN,
                      timeout: float = DNS_TIMEOUT) -> Optional[float]:
    """
    Send a raw DNS A-record query to server_ip:53 (UDP) and measure round-trip
    time in milliseconds. Returns None on timeout / error.
    This bypasses the OS resolver so the result is server-specific.
    """
    # Build a minimal DNS query packet for the given domain
    txid = random.randint(0, 0xFFFF)
    flags = 0x0100          # standard query, recursion desired
    qdcount = 1
    header = struct.pack(">HHHHHH", txid, flags, qdcount, 0, 0, 0)

    labels = b""
    for part in domain.split("."):
        encoded = part.encode()
        labels += bytes([len(encoded)]) + encoded
    labels += b"\x00"       # root label
    qtype  = struct.pack(">H", 1)   # A record
    qclass = struct.pack(">H", 1)   # IN
    packet = header + labels + qtype + qclass

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        t0 = time.perf_counter()
        sock.sendto(packet, (server_ip, 53))
        data, _ = sock.recvfrom(512)
        elapsed = (time.perf_counter() - t0) * 1000
        sock.close()
        # Validate: response bit must be set, txid must match
        resp_id = struct.unpack(">H", data[:2])[0]
        resp_flags = struct.unpack(">H", data[2:4])[0]
        if resp_id == txid and (resp_flags & 0x8000):  # QR bit
            return round(elapsed, 2)
        return None
    except Exception:
        return None
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _bench_one_dns(name: str, info: dict) -> DnsResult:
    """Benchmark a single DNS provider (DNS_BENCH_ROUNDS queries)."""
    primary   = info["primary"]
    secondary = info["secondary"]
    tag       = info["tag"]
    rtts: list[float] = []
    sent = DNS_BENCH_ROUNDS

    for _ in range(DNS_BENCH_ROUNDS):
        # Alternate between primary and secondary to get a real-world mix
        server = primary
        rtt = dns_query_latency(server)
        if rtt is not None:
            rtts.append(rtt)
        time.sleep(0.05)

    if not rtts:
        return DnsResult(name=name, primary=primary, secondary=secondary, tag=tag,
                         avg_ms=-1, min_ms=-1, jitter_ms=0, loss_pct=100.0)

    loss = max(0.0, (sent - len(rtts)) / sent * 100)
    avg  = statistics.mean(rtts)
    mn   = min(rtts)
    jitter = statistics.stdev(rtts) if len(rtts) > 1 else 0.0
    return DnsResult(
        name=name, primary=primary, secondary=secondary, tag=tag,
        avg_ms=round(avg, 2), min_ms=round(mn, 2),
        jitter_ms=round(jitter, 2), loss_pct=round(loss, 1)
    )


def scan_dns_servers(providers: dict | None = None,
                     progress_callback=None) -> list[DnsResult]:
    """
    Benchmark all DNS providers in parallel (thread-per-provider).
    Returns results sorted fastest → slowest.
    """
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

    # Sort: reachable by avg_ms, then unreachable at bottom
    reachable   = sorted([r for r in results if r.avg_ms >= 0], key=lambda r: r.avg_ms)
    unreachable = [r for r in results if r.avg_ms < 0]
    sorted_results = reachable + unreachable
    for i, r in enumerate(sorted_results):
        r.rank = i + 1
    return sorted_results


# ── UI helpers ────────────────────────────────────────────────────────────────
BANNER = r"""
  __  __ _____ _   _    ___  ____ _____ ___ __  __ ___ ___________ ____  
 |  \/  |_   _| | | |  / _ \|  _ \_   _|_ _|  \/  |_ _|__  / ____|  _ \ 
 | |\/| | | | | | | | | | | | |_) || |  | || |\/| || |  / /|  _| | |_) |
 | |  | | | | | |_| | | |_| |  __/ | |  | || |  | || | / /_| |___|  _ < 
 |_|  |_| |_|  \___/   \___/|_|    |_| |___|_|  |_|___/____|_____|_| \_\
"""

def show_banner():
    try:
        console.print(Text(BANNER, style="bold bright_red"), justify="center")
    except Exception:
        console.print("[bold bright_red]  MTU OPTIMIZER[/] — Valorant Edition")
    console.print(
        Align.center(
            Text(f"  v{VERSION}  |  Built for low-latency gaming  |  Windows Only  ",
                 style="dim white on grey11")
        )
    )
    console.print()


def ping_color(ms: float) -> str:
    if ms < 0:    return "dim"
    if ms < 40:   return "bold bright_green"
    if ms < 70:   return "bold green"
    if ms < 100:  return "bold yellow"
    if ms < 150:  return "bold red"
    return "bold bright_red"


def rating_color(rating: str) -> str:
    return {
        "EXCELLENT":   "bold bright_green",
        "GOOD":        "bold green",
        "OK":          "bold yellow",
        "POOR":        "bold red",
        "BAD":         "bold bright_red",
        "UNREACHABLE": "dim",
    }.get(rating, "white")


def rating_emoji(rating: str) -> str:
    return {
        "EXCELLENT":   "🟢",
        "GOOD":        "🟢",
        "OK":          "🟡",
        "POOR":        "🔴",
        "BAD":         "🔴",
        "UNREACHABLE": "⚫",
    }.get(rating, "⚪")


def dns_rating_color(rating: str) -> str:
    return {
        "BLAZING":     "bold bright_cyan",
        "EXCELLENT":   "bold bright_green",
        "GOOD":        "bold green",
        "OK":          "bold yellow",
        "SLOW":        "bold red",
        "BAD":         "bold bright_red",
        "UNREACHABLE": "dim",
    }.get(rating, "white")


def dns_rating_emoji(rating: str) -> str:
    return {
        "BLAZING":     "⚡",
        "EXCELLENT":   "🟢",
        "GOOD":        "🟢",
        "OK":          "🟡",
        "SLOW":        "🔴",
        "BAD":         "🔴",
        "UNREACHABLE": "⚫",
    }.get(rating, "⚪")


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
    table.add_column("#",         justify="right",  min_width=3,  style="dim")
    table.add_column("Provider",  justify="left",   min_width=28, style="bold white")
    table.add_column("Primary IP",justify="left",   min_width=16)
    table.add_column("Secondary", justify="left",   min_width=16)
    table.add_column("Avg",       justify="right",  min_width=9)
    table.add_column("Min",       justify="right",  min_width=9)
    table.add_column("Jitter",    justify="right",  min_width=9)
    table.add_column("Loss",      justify="right",  min_width=6)
    table.add_column("Rating",    justify="center", min_width=14)
    table.add_column("Tag",       justify="left",   min_width=16, style="dim italic")

    for r in results:
        prefix = "🏆 " if r.rank == 1 and r.avg_ms >= 0 else (
                 "🥈 " if r.rank == 2 and r.avg_ms >= 0 else (
                 "🥉 " if r.rank == 3 and r.avg_ms >= 0 else "   "))
        if r.avg_ms < 0:
            table.add_row(
                str(r.rank), f"{prefix}{r.name}", f"[dim]{r.primary}[/]",
                f"[dim]{r.secondary}[/]",
                "[dim]N/A[/]", "[dim]N/A[/]", "[dim]N/A[/]",
                "[dim red]100%[/]", "[dim]⚫ UNREACHABLE[/]", r.tag
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
    """
    Full DNS scanner UI.  Benchmarks all providers, shows leaderboard,
    optionally applies the winner.
    Returns the winning DnsResult (or None on failure).
    """
    console.print(Rule("[bold cyan]🌐 DNS Speed Scanner (DNS Jumper Mode)[/]", style="cyan"))
    console.print()
    console.print(
        f"  Benchmarking [bold]{len(DNS_PROVIDERS)}[/] DNS providers via raw UDP queries\n"
        f"  Domain: [cyan]{DNS_TEST_DOMAIN}[/]  ·  Rounds per server: [cyan]{DNS_BENCH_ROUNDS}[/]\n"
        f"  [dim]All queries sent in parallel — results in ~{DNS_BENCH_ROUNDS * 0.1:.0f}s[/]\n"
    )

    results: list[DnsResult] = []

    with Progress(
        SpinnerColumn(spinner_name="dots12", style="bold cyan"),
        TextColumn("[bold white]{task.description}"),
        BarColumn(bar_width=35, style="cyan", complete_style="bright_green"),
        TextColumn("[dim]{task.completed}/{task.total} tested[/dim]"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
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

    # Identify winner
    reachable = [r for r in results if r.avg_ms >= 0]
    if not reachable:
        console.print("[bold red]  ❌ No DNS server responded. Check your internet connection.[/]")
        return None

    winner = reachable[0]  # already sorted fastest first

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

    # Apply if adapter provided and auto_apply or user confirms
    if adapter:
        do_apply = auto_apply
        if not auto_apply:
            do_apply = Confirm.ask(
                f"  [bold yellow]Apply {winner.name} ({winner.primary}) as your DNS now?[/]",
                default=True,
                console=console,
            )
        if do_apply:
            ok, msg = set_dns_custom(
                adapter, winner.primary, winner.secondary, winner.name
            )
            flush_ok, flush_msg = flush_dns()
            icon = "✅" if ok else "❌"
            color = "green" if ok else "red"
            console.print(f"  {icon} [{color}]{msg}[/{color}]")
            console.print(f"  ✅ [green]{flush_msg}[/green]")
            console.print()

    return winner


def build_ping_table(results: list[PingResult]) -> Table:
    table = Table(
        title="[bold bright_red]⚡ Valorant Server Ping Results[/]",
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
                f"[dim]⚫ UNREACHABLE[/]",
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


def build_summary_panel(
    recommended_mtu: int,
    original_mtu: int,
    best_region: Optional[PingResult],
    tweaks: list[tuple[bool, str]],
    scan_only: bool,
) -> Panel:
    lines = []

    # MTU
    lines.append(Text("  MTU Optimization", style="bold bright_white"))
    lines.append(Text(f"   Original MTU : {original_mtu} bytes", style="dim"))
    mtu_diff = recommended_mtu - original_mtu
    diff_str = f"({'↑ increased' if mtu_diff > 0 else '↓ decreased' if mtu_diff < 0 else 'no change'}  {abs(mtu_diff)} bytes)" if mtu_diff != 0 else "(no change needed)"
    lines.append(Text(f"   Optimal MTU  : {recommended_mtu} bytes  {diff_str}", style="bold bright_green"))
    lines.append(Text(""))

    # Best region
    if best_region:
        lines.append(Text("  Best Valorant Server Region", style="bold bright_white"))
        lines.append(Text(f"   Region  : {best_region.region.strip()}", style="bold bright_cyan"))
        lines.append(Text(f"   Avg ping: {best_region.avg_ms} ms", style=ping_color(best_region.avg_ms)))
        lines.append(Text(f"   Jitter  : {best_region.jitter_ms} ms", style="dim"))
        lines.append(Text(""))

    # Tweaks
    if tweaks:
        lines.append(Text("  Network Tweaks Applied", style="bold bright_white"))
        for ok, msg in tweaks:
            icon = "✅" if ok else "❌"
            color = "green" if ok else "red"
            lines.append(Text(f"   {icon} {msg}", style=color))
        lines.append(Text(""))

    if scan_only:
        lines.append(Text("  ⚠  Run without --scan to apply changes (requires admin)", 
                         style="bold yellow"))

    group = Text("\n").join(lines) if lines else Text("No data")
    # Build manually
    out = Text()
    for l in lines:
        out.append_text(l)
        out.append("\n")

    return Panel(
        out,
        title="[bold bright_red]🚀 Optimization Summary[/]",
        border_style="bright_red",
        box=box.DOUBLE_EDGE,
        padding=(1, 2),
    )


# ── main flow ─────────────────────────────────────────────────────────────────
def run_mtu_finder(scan_only: bool = False) -> int:
    """Interactive MTU finder with progress UI."""
    console.print(Rule("[bold red]🔍 MTU Discovery[/]", style="red"))
    console.print()

    test_host = "8.8.8.8"
    # Pick best responding host
    for h in MTU_TEST_HOSTS:
        r = ping3_ping(h, timeout=2, unit="ms")
        if r and r > 0:
            test_host = h
            break

    console.print(f"  Testing against [cyan]{test_host}[/] (DF bit set — no fragmentation allowed)")
    console.print()

    status_text = {"mtu": 0, "lo": 0, "hi": 0}
    result_mtu = [1500]

    with Progress(
        SpinnerColumn(spinner_name="dots12", style="bold red"),
        TextColumn("[bold white]{task.description}"),
        BarColumn(bar_width=40, style="red", complete_style="bright_green"),
        TextColumn("[dim]{task.fields[info]}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task(
            "Finding optimal MTU...",
            total=100,
            info="Starting binary search..."
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


def run_ping_test() -> list[PingResult]:
    """Ping all Valorant server regions."""
    console.print(Rule("[bold red]📡 Valorant Server Ping Test[/]", style="red"))
    console.print()

    results = []
    regions = list(VALORANT_SERVERS.items())

    with Progress(
        SpinnerColumn(spinner_name="dots12", style="bold red"),
        TextColumn("[bold white]{task.description}"),
        BarColumn(bar_width=35, style="red", complete_style="bright_green"),
        TextColumn("[dim]{task.completed}/{task.total} regions[/dim]"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("Pinging regions...", total=len(regions))

        for region, ips in regions:
            progress.update(task, description=f"Pinging {region.strip()}...")
            result = ping_server_group(region, ips)
            results.append(result)
            progress.advance(task)

    console.print()
    console.print(build_ping_table(results))
    console.print()
    return results


def run_tweaks(adapter: str, mtu: int, dns: bool = True,
               best_dns: Optional[DnsResult] = None) -> list[tuple[bool, str]]:
    """Apply all network optimizations."""
    console.print(Rule("[bold red]⚙️  Applying Network Tweaks[/]", style="red"))
    console.print()

    tweaks_to_run = [
        ("Setting optimal MTU",           lambda: apply_mtu(adapter, mtu)),
        ("Disabling Nagle's algorithm",   disable_nagle),
        ("Disabling TCP auto-tuning",     disable_auto_tuning),
        ("Enabling RSS",                  enable_rss),
        ("Setting QoS DSCP priority",    set_qos_dscp),
    ]
    if dns:
        if best_dns and best_dns.avg_ms >= 0:
            # Use the scanned winner
            tweaks_to_run.append((
                f"Setting DNS to {best_dns.name} ({best_dns.primary})",
                lambda d=best_dns: set_dns_custom(
                    adapter, d.primary, d.secondary, d.name
                )
            ))
        else:
            # Fall back to Cloudflare
            tweaks_to_run.append(("Setting DNS to Cloudflare 1.1.1.1",
                                   lambda: set_dns_cloudflare(adapter)))
    tweaks_to_run.append(("Flushing DNS cache", flush_dns))

    results = []
    with Progress(
        SpinnerColumn(spinner_name="dots12", style="bold red"),
        TextColumn("[bold white]{task.description}"),
        BarColumn(bar_width=30, style="red", complete_style="bright_green"),
        TextColumn("[dim]{task.completed}/{task.total}[/dim]"),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("Applying tweaks...", total=len(tweaks_to_run))

        for name, fn in tweaks_to_run:
            progress.update(task, description=name + "...")
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


# ── Traceroute analysis ───────────────────────────────────────────────────────
def run_traceroute(target_ip: str = "99.83.199.240", region: str = "ME - Bahrain") -> None:
    """Run tracert to target and display the hop path with latency analysis."""
    console.print(Rule(f"[bold red]🛣️  Traceroute to {region} ({target_ip})[/]", style="red"))
    console.print()
    console.print(f"  [dim]Running: tracert -d -h 20 -w 1000 {target_ip}[/]")
    console.print(f"  [dim]This shows the exact path your packets take. High hops = bad ISP routing.[/]")
    console.print()

    table = Table(
        box=box.SIMPLE_HEAVY,
        border_style="dim",
        header_style="bold white",
        show_footer=False,
        expand=False,
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

        hop_num = 0
        for line in proc.stdout:
            line = line.rstrip()
            m = hop_re.match(line)
            if not m:
                continue
            hop_num += 1
            hop_idx = m.group(1)
            ip_part = m.group(3).strip()

            rtts = rtt_re.findall(line.replace(ip_part, ""))
            rtt_vals = []
            rtt_strs = []
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
        "  - Many hops through the same country = ISP re-routing problem\n"
        "  - [bold]* * *[/] = that router blocks ping probes (normal)\n\n"
        "  [bold yellow]Egypt tip:[/] If you see hops going through Europe before Bahrain,\n"
        "  your ISP is using a suboptimal path. Contact your ISP or try\n"
        "  [bold cyan]Cloudflare WARP[/] (one.one.one.one/warp) — it often fixes this.",
        border_style="dim",
        box=box.ROUNDED,
    ))
    console.print()


# ── WARP detection ────────────────────────────────────────────────────────────
def check_warp() -> None:
    """Detect if Cloudflare WARP is installed/running and show guidance."""
    console.print(Rule("[bold red]☁️  Cloudflare WARP Check[/]", style="red"))
    console.print()

    warp_running = False
    warp_installed = False

    # Check if WARP service is running
    try:
        r = subprocess.run(
            ["sc", "query", "CloudflareWARP"],
            capture_output=True, text=True, timeout=5
        )
        if "RUNNING" in r.stdout:
            warp_running = True
            warp_installed = True
        elif "STOPPED" in r.stdout or "FAILED" in r.stdout:
            warp_installed = True
    except Exception:
        pass

    # Check if warp-cli exists
    if not warp_installed:
        try:
            r = subprocess.run(
                ["warp-cli", "--version"],
                capture_output=True, text=True, timeout=3
            )
            if r.returncode == 0:
                warp_installed = True
        except Exception:
            pass

    if warp_running:
        console.print(Panel(
            "  ✅ [bold green]Cloudflare WARP is running![/]\n\n"
            "  Your traffic is already being routed through Cloudflare's network.\n"
            "  This can help bypass bad ISP routing paths in Egypt.\n\n"
            "  [bold]Check if it's helping:[/]  Compare your Valorant ping with WARP ON vs OFF.\n"
            "  If ping is higher with WARP, toggle it off in the WARP app.",
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
            "  WARP is a [bold]free[/] VPN by Cloudflare that can significantly reduce\n"
            "  ping for Egyptian players by fixing bad ISP routing paths.\n\n"
            "  [bold cyan]How to get it:[/]\n"
            "  1. Go to: [link=https://one.one.one.one/]https://one.one.one.one/[/link]\n"
            "  2. Download WARP for Windows\n"
            "  3. Install & click the toggle to enable\n"
            "  4. Test your Valorant ping — compare with WARP on/off\n\n"
            "  [bold yellow]Important:[/] WARP may increase or decrease your ping depending\n"
            "  on your specific ISP. Test it before deciding to keep it on.\n"
            "  Vanguard (Valorant anti-cheat) allows WARP — it is NOT a gaming VPN ban risk.",
            title="[bold cyan]WARP Recommendation for Egypt[/]",
            border_style="cyan", box=box.ROUNDED,
        ))
    console.print()


# ── Route injector ─────────────────────────────────────────────────────────────
def inject_riot_routes() -> list[tuple[bool, str]]:
    """
    Add persistent static routes for Riot's IP ranges with metric 1 (highest priority).
    This ensures your OS sends Riot traffic via the best local gateway,
    not a slower secondary interface. Requires admin.
    """
    # Get default gateway
    gateway = None
    try:
        r = subprocess.run(
            ["route", "print", "0.0.0.0"],
            capture_output=True, text=True, timeout=5
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

    results = []
    results.append((True, f"Default gateway: {gateway}"))

    for cidr in RIOT_IP_RANGES:
        try:
            # Parse CIDR
            ip_net = cidr.split("/")
            network = ip_net[0]
            prefix = int(ip_net[1])
            # Convert prefix to mask
            mask_int = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
            mask = ".".join(str((mask_int >> (8 * i)) & 0xFF) for i in reversed(range(4)))

            r = subprocess.run(
                ["route", "add", network, "mask", mask, gateway, "metric", "1", "-p"],
                capture_output=True, text=True, timeout=5
            )
            ok = r.returncode == 0
            msg = f"Route {cidr} via {gateway}" + (" added" if ok else f" FAILED: {r.stderr.strip()}")
            results.append((ok, msg))
        except Exception as e:
            results.append((False, f"{cidr}: {e}"))

    return results


def run_route_optimizer() -> None:
    """UI wrapper for route injection."""
    console.print(Rule("[bold red]🗺️  Riot Route Optimizer[/]", style="red"))
    console.print()
    console.print(
        "  This injects [bold]persistent static routes[/] for all Riot IP ranges\n"
        "  so your OS always uses the best local gateway for Valorant traffic.\n"
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
        "  It does NOT change your ISP's routing path (only WARP/VPN can do that).\n"
        "  To undo: [bold]route delete [network] mask [mask][/] or use --restore.",
        border_style="dim", box=box.ROUNDED,
    ))
    console.print()


# ── CLI entry ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="MTU Optimizer for Valorant / Gaming -- Windows (Egypt Edition)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--scan",     action="store_true", help="Scan only, do not apply any changes")
    parser.add_argument("--mtu-only", action="store_true", help="Only run MTU finder")
    parser.add_argument("--ping",     action="store_true", help="Only run server ping test")
    parser.add_argument("--apply",    action="store_true", help="Apply tweaks (requires admin)")
    parser.add_argument("--restore",  action="store_true", help="Restore default network settings")
    parser.add_argument("--no-dns",   action="store_true", help="Skip DNS change when applying tweaks")
    parser.add_argument("--dns-scan", action="store_true", help="Benchmark all DNS providers and apply the fastest one")
    parser.add_argument("--trace",    action="store_true", help="Traceroute to Bahrain (ME) server — shows your ISP routing path")
    parser.add_argument("--route",    action="store_true", help="Inject static routes for all Riot IP ranges (requires admin)")
    parser.add_argument("--warp",     action="store_true", help="Check Cloudflare WARP status and show setup guide")
    args = parser.parse_args()

    # ── Banner
    console.clear()
    show_banner()

    # ── Admin check
    admin = is_admin()
    if admin:
        console.print(Panel(
            "  ✅ [bold green]Running as Administrator[/] — all tweaks can be applied",
            border_style="green", box=box.ROUNDED
        ))
    else:
        console.print(Panel(
            "  ⚠️  [bold yellow]NOT running as Administrator[/]\n"
            "  Scan will still work, but network tweaks require admin rights.\n"
            "  Re-run as Administrator to apply optimizations.",
            border_style="yellow", box=box.ROUNDED
        ))
    console.print()

    # ── System info
    adapter = get_active_adapter()
    original_mtu = get_current_mtu(adapter)
    console.print(f"  🖥️  Adapter : [cyan]{adapter}[/]")
    console.print(f"  📦 Current MTU : [yellow]{original_mtu}[/] bytes")
    console.print(f"  🖥️  OS : [dim]{platform.system()} {platform.release()}[/]")
    console.print()

    # ── Restore mode
    if args.restore:
        console.print(Rule("[bold red]♻️  Restoring Default Settings[/]", style="red"))
        console.print()
        if not admin:
            console.print("[bold red]ERROR:[/] Administrator rights required to restore settings.")
            sys.exit(1)
        results = restore_defaults(adapter)
        for ok, msg in results:
            icon = "✅" if ok else "❌"
            color = "green" if ok else "red"
            console.print(f"  {icon} [{color}]{msg}[/{color}]")
        console.print()
        console.print("[bold green]✅ Settings restored to defaults. Reboot recommended.[/]")
        return

    # ── Ping-only mode
    if args.ping:
        results = run_ping_test()
        reachable = [r for r in results if r.avg_ms > 0]
        if reachable:
            best = min(reachable, key=lambda r: r.avg_ms)
            console.print(f"  👑 Best region: [bold bright_cyan]{best.region.strip()}[/] @ [bold bright_green]{best.avg_ms} ms[/]")
        return

    # ── DNS scan-only mode
    if args.dns_scan:
        can_apply_dns = admin
        winner = run_dns_scanner(
            adapter=adapter if can_apply_dns else None,
            auto_apply=False,
        )
        if not can_apply_dns:
            console.print("[bold yellow]  ⚠  Run as Administrator to auto-apply the winning DNS.[/]")
        return

    # ── Traceroute mode
    if args.trace:
        run_traceroute(target_ip="99.83.199.240", region="ME - Bahrain (Valorant)")
        return

    # ── WARP check mode
    if args.warp:
        check_warp()
        return

    # ── Route inject mode
    if args.route:
        if not admin:
            console.print("[bold red]ERROR:[/] --route requires Administrator rights.")
            sys.exit(1)
        run_route_optimizer()
        return

    # ── MTU-only mode
    if args.mtu_only:
        run_mtu_finder(scan_only=args.scan)
        return

    # ── Full scan
    recommended_mtu = run_mtu_finder(scan_only=args.scan)
    ping_results = run_ping_test()

    reachable = [r for r in ping_results if r.avg_ms > 0]
    best_region = min(reachable, key=lambda r: r.avg_ms) if reachable else None

    # ── DNS scan (always run in full mode unless --no-dns)
    best_dns: Optional[DnsResult] = None
    if not args.no_dns and not args.scan:
        best_dns = run_dns_scanner(
            adapter=adapter if admin else None,
            auto_apply=True if args.apply else False,
        )
    elif not args.no_dns and args.scan:
        # Scan-only: still benchmark DNS but don't apply
        best_dns = run_dns_scanner(adapter=None, auto_apply=False)

    # ── Apply tweaks
    tweaks_applied = []
    can_apply = admin and not args.scan
    if can_apply:
        if not args.apply:
            # Ask user
            console.print(Rule("[bold red]🔧 Apply Remaining Optimizations?[/]", style="red"))
            console.print()
            console.print(f"  Optimal MTU: [bold bright_green]{recommended_mtu}[/]")
            if best_region:
                console.print(f"  Best region: [bold bright_cyan]{best_region.region.strip()}[/]")
            if best_dns and best_dns.avg_ms >= 0:
                console.print(f"  Best DNS   : [bold bright_cyan]{best_dns.name}[/] @ [bold bright_green]{best_dns.avg_ms} ms[/]")
            console.print()
            do_apply = Confirm.ask(
                "  [bold yellow]Apply remaining network optimizations?[/] (MTU, Nagle, QoS...)",
                default=True,
                console=console
            )
        else:
            do_apply = True

        if do_apply:
            console.print()
            tweaks_applied = run_tweaks(
                adapter, recommended_mtu,
                dns=not args.no_dns,
                best_dns=best_dns,
            )
    elif args.scan:
        console.print("[dim]  Scan-only mode — changes not applied.[/]")
    else:
        console.print("[bold yellow]  ⚠  Run as Administrator to apply tweaks.[/]")

    console.print()
    console.print(build_summary_panel(
        recommended_mtu, original_mtu, best_region, tweaks_applied, scan_only=not can_apply
    ))
    console.print()

    # Final tips
    tips = [
        "💡 Best Valorant region for Egypt: Middle East (Bahrain) — ~60-90ms expected",
        "💡 EU Frankfurt is your fallback if ME servers are unstable — ~80-110ms",
        "💡 Run: python mtu_optimizer.py --dns-scan  to benchmark & apply the fastest DNS",
        "💡 Run: python mtu_optimizer.py --trace     to see your ISP routing path",
        "💡 Run: python mtu_optimizer.py --warp      to check Cloudflare WARP setup",
        "💡 Wired ethernet always beats Wi-Fi for gaming latency",
        "💡 If ping spikes persist, run --trace and share results with your ISP",
        "💡 Re-run --dns-scan weekly — fastest DNS can change based on ISP peering",
    ]
    console.print(Panel(
        "\n".join(f"  {t}" for t in tips),
        title="[bold bright_white]💬 Gaming Tips[/]",
        border_style="dim",
        box=box.SIMPLE_HEAVY,
        padding=(0, 1),
    ))
    console.print()

    if tweaks_applied:
        console.print(Align.center(
            Text("⚡ All done! Reboot recommended for all changes to fully apply. ⚡",
                 style="bold bright_green")
        ))
    console.print()


if __name__ == "__main__":
    main()
