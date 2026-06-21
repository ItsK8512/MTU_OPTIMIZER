# 🎮 MTU Optimizer for Valorant / Gaming

A Python CLI tool to find your network's optimal MTU, measure Valorant server pings across all regions, and apply Windows network tweaks for the lowest possible latency.

---

## 🚀 Quick Start

```powershell
# 1. Install dependencies
pip install rich ping3

# 2. Run (as Administrator for applying tweaks)
python mtu_optimizer.py
```

> **Run as Administrator** (right-click → *Run as administrator*) to apply network tweaks.

---

## ✨ What It Does

### 🔍 MTU Finder
- Uses **binary search** between 576–1500 bytes
- Sets the **Don't Fragment (DF)** bit — finds the largest packet that won't be fragmented by your router
- Fragmented packets = extra latency spikes in gaming

### 📡 Valorant Server Ping
Pings real Valorant/Riot relay IPs across **10 regions**:
- 🇺🇸 NA (Ashburn, Chicago)
- 🇩🇪🇬🇧 EU (Frankfurt, London)
- 🇯🇵🇸🇬 AP (Tokyo, Singapore)
- 🇰🇷 KR (Seoul) · 🇧🇷 BR (São Paulo) · 🇦🇺 OCE (Sydney) · 🇿🇦 AF (Johannesburg)

Reports **avg / min / max ping, jitter, and packet loss** per region.

### ⚙️ Network Tweaks Applied
| Tweak | Why It Helps |
|---|---|
| **Optimal MTU** | Eliminates fragmentation latency |
| **Disable Nagle's Algorithm** | Reduces TCP buffering delay (TCP_NODELAY) |
| **Disable TCP Auto-Tuning** | Prevents random latency spikes from window scaling |
| **Enable RSS** | Better multi-core CPU usage for network |
| **QoS DSCP 46** | Marks packets as high priority on routers |
| **Cloudflare DNS (1.1.1.1)** | Faster DNS resolution for server matching |
| **Flush DNS Cache** | Ensures fresh server connections |

---

## 🕹️ Usage

```
python mtu_optimizer.py              Full scan + ask to apply
python mtu_optimizer.py --scan       Scan only, no changes
python mtu_optimizer.py --mtu-only   MTU finder only
python mtu_optimizer.py --ping       Server ping test only
python mtu_optimizer.py --apply      Auto-apply without asking
python mtu_optimizer.py --no-dns     Skip DNS change
python mtu_optimizer.py --restore    Restore all defaults
```

---

## 📦 Requirements

```
rich>=13.0.0
ping3>=4.0.3
```

Install: `pip install rich ping3`

---

## ⚠️ Notes
- **Windows only** (uses `netsh`, `winreg`)
- Requires **Administrator** to apply tweaks
- Run `--restore` to undo all changes
- Reboot after applying for best results
