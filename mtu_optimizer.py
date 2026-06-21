#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, io
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
"""
╔══════════════════════════════════════════════════════════════╗
║        MTU OPTIMIZER v3.0 — Gaming Network Suite             ║
║  Valorant · CS2 · League · Apex · Fortnite                   ║
║  Find optimal MTU · Ping servers · Benchmark DNS · Optimize  ║
╚══════════════════════════════════════════════════════════════╝

USAGE:
    python mtu_optimizer.py            — Launch interactive menu
    python mtu_optimizer.py --scan     — Full scan (no changes)
    python mtu_optimizer.py --mtu-only — MTU finder only
    python mtu_optimizer.py --ping     — Server ping test
    python mtu_optimizer.py --dns-scan — DNS benchmark
    python mtu_optimizer.py --speed    — Internet speed test
    python mtu_optimizer.py --monitor  — Real-time network monitor
    python mtu_optimizer.py --stable   — Connection stability test
    python mtu_optimizer.py --apply    — Apply all tweaks
    python mtu_optimizer.py --restore  — Restore default settings
    python mtu_optimizer.py --export   — Export report

Requires: pip install rich ping3
Optional: pip install requests psutil
Run as Administrator for applying network tweaks.
"""

import sys

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

from mtu_optimizer.menu import main

if __name__ == "__main__":
    main()
