<div align="center">

# ⚡ MTU Optimizer v3.0

**The Ultimate Gaming Network Optimization Suite**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows-0078D6.svg?style=for-the-badge&logo=windows&logoColor=white)](https://microsoft.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-success.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Status: Active](https://img.shields.io/badge/Status-Active-brightgreen.svg?style=for-the-badge)](#)

*A powerful Python CLI tool and **interactive TUI** for finding your network's optimal MTU, benchmarking DNS providers, pinging game servers across 5 games, testing internet speed, monitoring connection stability, and applying Windows network optimizations for the lowest possible gaming latency.*

<br>
<b>Supported Games</b><br>
🎮 Valorant · 💣 CS2 · ⚔️ League of Legends · 🔫 Apex Legends · 🏗️ Fortnite

</div>

---

## 📖 Table of Contents
- [🚀 Quick Start](#-quick-start)
- [✨ Core Features](#-core-features)
- [🕹️ Usage](#️-usage)
- [📦 Requirements](#-requirements)
- [🏗️ Project Structure](#️-project-structure)
- [⚠️ Important Notes](#️-important-notes)

---

## 🚀 Quick Start

Get up and running in seconds.

```powershell
# 1. Install required dependencies
pip install rich ping3

# 2. Install optional dependencies (for enhanced features like network monitor & speed test)
pip install requests psutil

# 3. Launch interactive menu
python mtu_optimizer.py
```

> **🔥 Pro Tip:** For full optimization capabilities, run your terminal (e.g., PowerShell) as **Administrator**.
> *Right-click PowerShell → "Run as administrator"*

---

## ✨ Core Features

### 🔍 Precision MTU Discovery
- **Binary search** between 576–1500 bytes with DF (Don't Fragment) bit enabled.
- **Parallel multi-host testing** ensures highly reliable and fast results.
- Dynamically finds the largest packet that won't fragment on your specific network route.

### 📡 Multi-Game Server Ping Database
Test latency against official servers globally for top competitive titles.

| Game | Regions |
| :--- | :--- |
| **🎯 Valorant** | 11 regions *(ME, EU, NA, AP, KR, BR, OCE, AF)* |
| **⚔️ League of Legends** | 11 regions |
| **💣 CS2** | 12 regions *(Valve SDR relays)* |
| **🔫 Apex Legends** | 11 regions |
| **🏗️ Fortnite** | 10 regions |

*Reports **avg / min / max ping, jitter, and packet loss** per region with color-coded health ratings.*

### 🌐 Advanced DNS Speed Scanner
- Benchmarks **25+ DNS providers** via raw UDP queries.
- Tests major providers: *Cloudflare, Google, Quad9, AdGuard, NextDNS, and more.*
- **Auto-applies** the fastest DNS with a single click.
- Complete with a performance leaderboard (🏆🥈🥉).

### 📊 Real-time Dashboard & Monitoring
| Feature | Description |
| :--- | :--- |
| **⚡ Internet Speed Test** | Built-in test for download/upload speed and **Bufferbloat detection**. |
| **📈 Network Monitor** | Live dashboard with ping sparkline graph, jitter detection, and connection quality score (0-100). |
| **🛡️ Stability Test** | 30-second sustained ping analysis to detect latent network spikes (>2x average). |

### ⚙️ Automated Network Optimizations
Achieve peak network performance with automated, OS-level tweaks:

| Tweak | Impact |
| :--- | :--- |
| **Optimal MTU** | Eliminates fragmentation-induced latency. |
| **Disable Nagle's Algorithm** | Reduces TCP buffering delay. |
| **Disable TCP Auto-Tuning** | Prevents random latency spikes under load. |
| **Enable RSS** | Optimizes multi-core CPU network packet processing. |
| **QoS DSCP 46** | Marks gaming packets as highest priority. |
| **TCP CTCP** | Better congestion control for continuous gaming streams. |
| **Windows Game Mode** | OS-level resource prioritization for active games. |
| **NIC Power Saving Off** | Prevents network adapter sleep state latency. |

### 💾 Safe & Reversible (Profiles & Backups)
- **Auto-backup** before any registry or network changes (your safety net).
- Named profiles: save, load, compare, and import/export your best configurations.
- **One-click restore** from any historical backup point.

### 📋 Export & Advanced Tools
- Export detailed reports in **JSON, HTML, or Text**.
- **Traceroute analysis** with hop-by-hop latency coloring.
- Cloudflare **WARP detection**.
- Riot **static route injection** for optimal local routing.

---

## 🕹️ Usage

### Interactive Menu (Highly Recommended)
Experience the beautiful Terminal User Interface (TUI):
```powershell
python mtu_optimizer.py
```

### CLI Automation Modes
Integrate into scripts or run single tasks directly:
```text
python mtu_optimizer.py --scan       # Full diagnostic scan (no changes made)
python mtu_optimizer.py --mtu-only   # Execute only MTU finder
python mtu_optimizer.py --ping       # Quick server ping test
python mtu_optimizer.py --dns-scan   # Execute DNS benchmark
python mtu_optimizer.py --speed      # Run Internet speed test
python mtu_optimizer.py --monitor    # Open Real-time network monitor
python mtu_optimizer.py --stable     # Execute connection stability test
python mtu_optimizer.py --trace      # Traceroute analysis
python mtu_optimizer.py --apply      # Auto-apply all optimal network tweaks
python mtu_optimizer.py --restore    # Restore all Windows network defaults
python mtu_optimizer.py --export     # Generate optimization report
python mtu_optimizer.py --game CS2   # Ping specific game servers
```
*(Run `python mtu_optimizer.py --help` for the full list of commands.)*

---

## 📦 Requirements

### Core Dependencies
```text
rich>=13.0.0
ping3>=4.0.3
```

### Optional Dependencies *(For Enhanced Features)*
```text
requests>=2.31.0    # Required for ISP detection & speed test
psutil>=5.9.0       # Required for network monitor throughput graphing
```

---

## 🏗️ Project Structure
```text
mtu/
├── mtu_optimizer.py          # 🚀 Application Entry Point
├── mtu_optimizer/            # 📦 Core Package
│   ├── __init__.py           
│   ├── core.py               # MTU finder, ping engine, stability
│   ├── dns.py                # DNS database & benchmark engine
│   ├── servers.py            # Multi-game server databases
│   ├── tweaks.py             # Network optimizations & traceroute
│   ├── system.py             # ISP detection, system info
│   ├── scoring.py            # Connection quality scoring
│   ├── profiles.py           # Profile save/load/compare
│   ├── backup.py             # Full network state backup/restore
│   ├── speedtest.py          # Internet speed test engine
│   ├── monitor.py            # Real-time network monitor TUI
│   ├── export.py             # Report generation (JSON/HTML/TXT)
│   ├── ui.py                 # Rich console UI helpers
│   └── menu.py               # Interactive TUI menu & CLI handler
```

---

## ⚠️ Important Notes

- 🛑 **Windows Only**: This suite relies heavily on Windows-specific utilities (`netsh`, `winreg`, `tracert`).
- 🛡️ **Administrator Privileges**: Applying or restoring network tweaks requires running as Admin.
- 🔄 **Reboot Recommended**: For TCP/IP and Registry changes to fully take effect, reboot your PC after applying tweaks.
- 📂 **Storage Paths**:
  - Backups: `%APPDATA%\MTUOptimizer\backups\`
  - Profiles: `%APPDATA%\MTUOptimizer\profiles\`
  - Reports: `%APPDATA%\MTUOptimizer\reports\`

---

<div align="center">
  <b>Built with ❤️ for gamers to achieve the lowest possible latency.</b><br>
  <a href="LICENSE">MIT License</a>
</div>
