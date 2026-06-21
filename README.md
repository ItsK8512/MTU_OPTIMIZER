# ⚡ MTU Optimizer v3.0 — Gaming Network Suite

A powerful Python CLI tool and **interactive TUI** for finding your network's optimal MTU, benchmarking DNS providers, pinging game servers across 5 games, testing internet speed, monitoring connection stability, and applying Windows network optimizations for the lowest possible gaming latency.

> **Supports:** Valorant · CS2 · League of Legends · Apex Legends · Fortnite

---

## 🚀 Quick Start

```powershell
# 1. Install dependencies
pip install rich ping3

# 2. Optional (enhanced features)
pip install requests psutil

# 3. Launch interactive menu
python mtu_optimizer.py

# 4. Or run as Administrator for full optimization
# Right-click PowerShell → "Run as administrator"
python mtu_optimizer.py
```

---

## ✨ Features

### 🔍 MTU Discovery
- **Binary search** between 576–1500 bytes with DF (Don't Fragment) bit
- Parallel multi-host testing for reliable results
- Finds the largest packet that won't fragment on your network

### 📡 Multi-Game Server Ping (5 Games)
| Game | Regions |
|------|---------|
| 🎯 Valorant | 11 regions (ME, EU, NA, AP, KR, BR, OCE, AF) |
| ⚔️ League of Legends | 11 regions |
| 💣 CS2 | 12 regions (Valve SDR relays) |
| 🔫 Apex Legends | 11 regions |
| 🏗️ Fortnite | 10 regions |

Reports **avg / min / max ping, jitter, and packet loss** per region with color-coded ratings.

### 🌐 DNS Speed Scanner
- Benchmarks **25+ DNS providers** via raw UDP queries
- Tests Cloudflare, Google, Quad9, AdGuard, NextDNS, and more
- Auto-applies the fastest DNS with one click
- Leaderboard with medals (🏆🥈🥉)

### ⚡ Internet Speed Test
- Download & upload speed measurement
- **Bufferbloat detection** (ping under load)
- Gaming-specific speed ratings

### 📊 Real-time Network Monitor
- Live dashboard with **ping sparkline graph**
- Jitter, packet loss, and spike detection
- Connection quality score (0-100)
- Optional throughput tracking via psutil

### 📈 Connection Stability Test
- 30-second sustained ping analysis
- Spike detection (>2x average)
- Latency consistency rating

### ⚡ Connection Quality Score
- **0-100 composite score** with letter grade (S/A/B/C/D/F)
- Weighted factors: Ping (30%), Jitter (25%), Loss (20%), MTU (10%), DNS (10%), Tweaks (5%)
- Visual gauge bar with per-factor breakdown

### ⚙️ Network Optimizations Applied
| Tweak | Why It Helps |
|---|---|
| **Optimal MTU** | Eliminates fragmentation latency |
| **Disable Nagle's Algorithm** | Reduces TCP buffering delay |
| **Disable TCP Auto-Tuning** | Prevents random latency spikes |
| **Enable RSS** | Better multi-core CPU network usage |
| **QoS DSCP 46** | Marks packets as high priority |
| **TCP CTCP** | Better congestion control for gaming |
| **Windows Game Mode** | OS-level gaming prioritization |
| **NIC Power Saving Off** | Prevents adapter sleep |
| **Fastest DNS** | Faster server resolution |
| **Flush DNS Cache** | Fresh connections |

### 💾 Profiles & Backups
- **Auto-backup** before any changes (safety net)
- Named profiles: save, load, compare, import/export
- One-click restore from any backup point

### 📋 Report Export
- **JSON** — machine-readable, track over time
- **HTML** — beautiful dark-themed report, shareable
- **Text** — paste in Discord/forums

### 🛣️ Advanced Tools
- **Traceroute analysis** with hop-by-hop latency coloring
- **Cloudflare WARP** detection and setup guide
- **Riot route injection** for optimal local routing
- **ISP & system detection** (auto-detect ISP, adapter speed, VPN)

---

## 🕹️ Usage

### Interactive Menu (Recommended)
```powershell
python mtu_optimizer.py
```

### CLI Modes
```
python mtu_optimizer.py --scan       Full scan, no changes
python mtu_optimizer.py --mtu-only   MTU finder only
python mtu_optimizer.py --ping       Server ping test
python mtu_optimizer.py --dns-scan   DNS benchmark
python mtu_optimizer.py --speed      Internet speed test
python mtu_optimizer.py --monitor    Real-time network monitor
python mtu_optimizer.py --stable     Connection stability test
python mtu_optimizer.py --trace      Traceroute to ME server
python mtu_optimizer.py --warp       Check Cloudflare WARP
python mtu_optimizer.py --route      Inject Riot static routes
python mtu_optimizer.py --apply      Auto-apply all tweaks
python mtu_optimizer.py --no-dns     Skip DNS change
python mtu_optimizer.py --restore    Restore all defaults
python mtu_optimizer.py --export     Export report
python mtu_optimizer.py --game CS2   Ping specific game servers
```

---

## 📦 Requirements

### Required
```
rich>=13.0.0
ping3>=4.0.3
```

### Optional (Enhanced Features)
```
requests>=2.31.0    # ISP detection, speed test
psutil>=5.9.0       # Network monitor throughput
```

Install all:
```powershell
pip install rich ping3 requests psutil
```

---

## 🏗️ Project Structure

```
mtu/
├── mtu_optimizer.py          # Entry point
├── mtu_optimizer/            # Package
│   ├── __init__.py           # Version & metadata
│   ├── core.py               # MTU finder, ping engine, stability test
│   ├── dns.py                # DNS database & benchmark engine
│   ├── servers.py            # Multi-game server databases
│   ├── tweaks.py             # Network optimizations & traceroute
│   ├── system.py             # ISP detection, system info
│   ├── scoring.py            # Connection quality scoring
│   ├── profiles.py           # Profile save/load/compare
│   ├── backup.py             # Full network state backup/restore
│   ├── speedtest.py          # Internet speed test
│   ├── monitor.py            # Real-time network monitor
│   ├── export.py             # Report export (JSON/HTML/TXT)
│   ├── ui.py                 # Rich console UI helpers
│   └── menu.py               # Interactive TUI menu & CLI
├── requirements.txt
├── LICENSE
└── README.md
```

---

## ⚠️ Notes

- **Windows only** (uses `netsh`, `winreg`, `tracert`)
- Requires **Administrator** to apply network tweaks
- Run `--restore` to undo all changes
- Reboot after applying for best results
- Backups stored in `%APPDATA%\MTUOptimizer\backups\`
- Profiles stored in `%APPDATA%\MTUOptimizer\profiles\`
- Reports stored in `%APPDATA%\MTUOptimizer\reports\`

---

## 📄 License

MIT License — see [LICENSE](LICENSE)
