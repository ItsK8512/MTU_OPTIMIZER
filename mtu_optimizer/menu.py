"""
mtu_optimizer.menu — Interactive TUI menu and CLI entry point
Provides both a keyboard-driven interactive menu and full CLI argument support.
"""

import sys
import os
import argparse
import platform
from typing import Optional

from mtu_optimizer import __version__
from mtu_optimizer.ui import (
    console, show_banner, show_system_info,
    Panel, Rule, Text, Align, box, Confirm, Prompt,
)
from mtu_optimizer.system import is_admin, get_os_info, get_public_ip_info
from mtu_optimizer.tweaks import (
    get_active_adapter, get_current_mtu,
    restore_defaults, run_tweaks, run_traceroute, check_warp, run_route_optimizer,
)
from mtu_optimizer.core import (
    run_mtu_finder, run_ping_test, run_stability_test_ui, PingResult,
)
from mtu_optimizer.dns import run_dns_scanner, DnsResult
from mtu_optimizer.servers import GAMES
from mtu_optimizer.scoring import compute_quality_score, show_quality_score
from mtu_optimizer.profiles import (
    auto_save_current_state, show_profiles_menu,
)
from mtu_optimizer.backup import create_backup, show_backup_menu
from mtu_optimizer.speedtest import run_speed_test
from mtu_optimizer.monitor import run_network_monitor
from mtu_optimizer.export import run_export_menu


# ── Summary panel ─────────────────────────────────────────────────────────────
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
    if mtu_diff != 0:
        direction = "↑ increased" if mtu_diff > 0 else "↓ decreased"
        diff_str = f"({direction}  {abs(mtu_diff)} bytes)"
    else:
        diff_str = "(no change needed)"
    lines.append(Text(f"   Optimal MTU  : {recommended_mtu} bytes  {diff_str}",
                      style="bold bright_green"))
    lines.append(Text(""))

    if best_region:
        lines.append(Text("  Best Server Region", style="bold bright_white"))
        lines.append(Text(f"   Region  : {best_region.region.strip()}", style="bold bright_cyan"))
        from mtu_optimizer.ui import ping_color
        lines.append(Text(f"   Avg ping: {best_region.avg_ms} ms",
                          style=ping_color(best_region.avg_ms)))
        lines.append(Text(f"   Jitter  : {best_region.jitter_ms} ms", style="dim"))
        lines.append(Text(""))

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

    out = Text()
    for line in lines:
        out.append_text(line)
        out.append("\n")

    return Panel(
        out,
        title="[bold bright_red]🚀 Optimization Summary[/]",
        border_style="bright_red",
        box=box.DOUBLE_EDGE,
        padding=(1, 2),
    )


# ── Interactive menu ──────────────────────────────────────────────────────────
MENU_OPTIONS = """
  ┌──────────────────────────────────────────────────────────┐
  │                                                          │
  │   [bold cyan][1][/]   🔍  [bold]Full Network Scan[/]        (MTU + Ping + DNS)  │
  │   [bold cyan][2][/]   📡  [bold]Ping Game Servers[/]        (multi-game)         │
  │   [bold cyan][3][/]   🌐  [bold]DNS Speed Scanner[/]        (25+ providers)      │
  │   [bold cyan][4][/]   ⚡  [bold]Internet Speed Test[/]      (DL/UL/bufferbloat)  │
  │   [bold cyan][5][/]   📊  [bold]Network Monitor[/]          (real-time)          │
  │   [bold cyan][6][/]   📈  [bold]Stability Test[/]           (30s sustained)      │
  │   [bold cyan][7][/]   🛣️   [bold]Traceroute Analysis[/]                           │
  │   [bold cyan][8][/]   ⚙️   [bold]Apply Optimizations[/]      (requires admin)     │
  │   [bold cyan][9][/]   💾  [bold]Profiles & Backups[/]                            │
  │   [bold cyan][0][/]   ♻️   [bold]Restore Defaults[/]                              │
  │   [bold cyan][Q][/]   🚪  [bold]Exit[/]                                          │
  │                                                          │
  └──────────────────────────────────────────────────────────┘
"""


def _select_game() -> tuple[str, dict]:
    """Let user pick a game for ping testing."""
    console.print()
    console.print("  [bold]Select a game:[/]")
    game_list = list(GAMES.keys())
    for i, name in enumerate(game_list):
        info = GAMES[name]
        console.print(f"    [cyan]{i + 1}[/]  {info['emoji']}  {name}")
    console.print(f"    [cyan]A[/]  🎮  All games")
    console.print()

    choice = Prompt.ask(
        "  [bold yellow]Game[/]",
        default="1",
        console=console,
    )

    if choice.lower() == "a":
        return "All", {}

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(game_list):
            name = game_list[idx]
            return name, GAMES[name]["servers"]
    except ValueError:
        pass

    return "Valorant", GAMES["Valorant"]["servers"]


def interactive_menu():
    """Main interactive menu loop."""
    console.clear()
    show_banner()

    admin = is_admin()
    if admin:
        console.print(Panel(
            "  ✅ [bold green]Running as Administrator[/] — all tweaks can be applied",
            border_style="green", box=box.ROUNDED,
        ))
    else:
        console.print(Panel(
            "  ⚠️  [bold yellow]NOT running as Administrator[/]\n"
            "  Scans will work, but applying tweaks requires admin rights.\n"
            "  Re-run as Administrator to apply optimizations.",
            border_style="yellow", box=box.ROUNDED,
        ))
    console.print()

    adapter = get_active_adapter()
    original_mtu = get_current_mtu(adapter)
    os_info = get_os_info()

    show_system_info(adapter, original_mtu, os_info)

    # Session data for export
    session_data: dict = {
        "system": {
            "adapter": adapter,
            "mtu": original_mtu,
            "os": os_info,
        },
    }

    while True:
        console.print(MENU_OPTIONS)
        choice = Prompt.ask(
            "  [bold bright_red]⚡ Choose option[/]",
            default="1",
            console=console,
        )

        console.print()

        if choice == "1":
            # Full scan
            recommended_mtu = run_mtu_finder()
            session_data["mtu"] = {"current": original_mtu, "optimal": recommended_mtu}

            game_name, servers = "Valorant", GAMES["Valorant"]["servers"]
            ping_results = run_ping_test(game_name, servers)
            session_data["ping_results"] = [
                {"region": r.region, "avg_ms": r.avg_ms, "min_ms": r.min_ms,
                 "max_ms": r.max_ms, "jitter_ms": r.jitter_ms,
                 "loss_pct": r.loss_pct, "rating": r.rating}
                for r in ping_results
            ]

            reachable = [r for r in ping_results if r.avg_ms > 0]
            best_region = min(reachable, key=lambda r: r.avg_ms) if reachable else None

            best_dns = run_dns_scanner(
                adapter=adapter if admin else None,
                auto_apply=False,
            )
            if best_dns:
                session_data["dns_winner"] = {
                    "name": best_dns.name, "primary": best_dns.primary,
                    "avg_ms": best_dns.avg_ms, "rating": best_dns.rating,
                }

            # Quality score
            qs = compute_quality_score(
                best_ping=best_region,
                dns_result=best_dns,
                current_mtu=original_mtu,
                optimal_mtu=recommended_mtu,
            )
            show_quality_score(qs)
            session_data["quality_score"] = {"total": qs.total, "grade": qs.grade}

            # Apply tweaks?
            tweaks_applied = []
            if admin:
                do_apply = Confirm.ask(
                    "  [bold yellow]Apply network optimizations?[/] (MTU, Nagle, QoS...)",
                    default=True, console=console,
                )
                if do_apply:
                    create_backup(adapter)
                    console.print("  [dim]Auto-backup created before changes.[/]\n")
                    tweaks_applied = run_tweaks(
                        adapter, recommended_mtu,
                        dns=True, best_dns=best_dns,
                    )
                    session_data["tweaks"] = tweaks_applied

            console.print(build_summary_panel(
                recommended_mtu, original_mtu, best_region,
                tweaks_applied, scan_only=not admin,
            ))

        elif choice == "2":
            # Ping game servers
            game_name, servers = _select_game()
            if game_name == "All":
                for gname, ginfo in GAMES.items():
                    run_ping_test(gname, ginfo["servers"])
            else:
                results = run_ping_test(game_name, servers)
                reachable = [r for r in results if r.avg_ms > 0]
                if reachable:
                    best = min(reachable, key=lambda r: r.avg_ms)
                    console.print(
                        f"  👑 Best region: [bold bright_cyan]{best.region.strip()}[/] "
                        f"@ [bold bright_green]{best.avg_ms} ms[/]"
                    )

        elif choice == "3":
            # DNS scanner
            best_dns = run_dns_scanner(
                adapter=adapter if admin else None,
                auto_apply=False,
            )
            if best_dns:
                session_data["dns_winner"] = {
                    "name": best_dns.name, "primary": best_dns.primary,
                    "avg_ms": best_dns.avg_ms, "rating": best_dns.rating,
                }

        elif choice == "4":
            # Speed test
            speed_results = run_speed_test()
            session_data["speedtest"] = speed_results

        elif choice == "5":
            # Network monitor
            monitor_results = run_network_monitor()

        elif choice == "6":
            # Stability test
            run_stability_test_ui()

        elif choice == "7":
            # Traceroute
            console.print("  [bold]Traceroute target:[/]")
            console.print("    [cyan]1[/]  ME - Bahrain (Valorant)")
            console.print("    [cyan]2[/]  EU - Frankfurt")
            console.print("    [cyan]3[/]  Custom IP")
            tr_choice = Prompt.ask("  [bold yellow]Target[/]", default="1", console=console)
            if tr_choice == "1":
                run_traceroute("99.83.199.240", "ME - Bahrain (Valorant)")
            elif tr_choice == "2":
                run_traceroute("104.160.142.3", "EU - Frankfurt (Valorant)")
            else:
                ip = Prompt.ask("  Enter IP", console=console)
                run_traceroute(ip, f"Custom ({ip})")

        elif choice == "8":
            # Apply optimizations
            if not admin:
                console.print("[bold red]  ❌ Requires Administrator. Re-run as admin.[/]")
                console.print()
                continue

            recommended_mtu = run_mtu_finder()
            best_dns = run_dns_scanner(adapter=adapter, auto_apply=False)

            create_backup(adapter)
            console.print("  [dim]Auto-backup created before changes.[/]\n")

            tweaks_applied = run_tweaks(
                adapter, recommended_mtu,
                dns=True, best_dns=best_dns,
            )
            session_data["tweaks"] = tweaks_applied

            console.print()
            console.print("[bold bright_green]  ⚡ All optimizations applied! Reboot recommended.[/]")

        elif choice == "9":
            # Profiles & Backups
            console.print("  [cyan]1[/]  Profiles  |  [cyan]2[/]  Backups  |  [cyan]3[/]  Export Report")
            sub = Prompt.ask("  [bold yellow]Choose[/]", default="1", console=console)
            if sub == "1":
                show_profiles_menu()
            elif sub == "2":
                show_backup_menu(adapter)
            elif sub == "3":
                run_export_menu(session_data)

        elif choice == "0":
            # Restore defaults
            if not admin:
                console.print("[bold red]  ❌ Requires Administrator.[/]")
                console.print()
                continue

            if Confirm.ask("  [bold yellow]Restore all network settings to defaults?[/]",
                           default=False, console=console):
                results = restore_defaults(adapter)
                for ok, msg in results:
                    icon = "✅" if ok else "❌"
                    color = "green" if ok else "red"
                    console.print(f"  {icon} [{color}]{msg}[/{color}]")
                console.print("\n[bold green]  ✅ Settings restored. Reboot recommended.[/]")

        elif choice.lower() == "q":
            console.print("  [bold]Goodbye! 🎮[/]")
            break

        else:
            console.print("  [red]Invalid choice. Try again.[/]")

        console.print()

    # Final tips
    tips = [
        "💡 Run as Administrator to apply all optimizations",
        "💡 Wired ethernet always beats Wi-Fi for gaming latency",
        "💡 Re-run DNS scan weekly — fastest DNS can change",
        "💡 Use --trace to diagnose ISP routing issues",
        "💡 Try Cloudflare WARP if your ISP routes poorly",
    ]
    console.print(Panel(
        "\n".join(f"  {t}" for t in tips),
        title="[bold bright_white]💬 Gaming Tips[/]",
        border_style="dim",
        box=box.SIMPLE_HEAVY,
        padding=(0, 1),
    ))
    console.print()


# ── CLI entry point ───────────────────────────────────────────────────────────
def main():
    """Parse CLI arguments or launch interactive menu."""
    parser = argparse.ArgumentParser(
        description="MTU Optimizer v3.0 — Gaming Network Optimization Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
INTERACTIVE:
    python mtu_optimizer.py            Launch interactive menu

CLI MODES:
    python mtu_optimizer.py --scan     Full scan (no changes)
    python mtu_optimizer.py --mtu-only MTU finder only
    python mtu_optimizer.py --ping     Server ping test only
    python mtu_optimizer.py --dns-scan DNS benchmark only
    python mtu_optimizer.py --speed    Internet speed test
    python mtu_optimizer.py --monitor  Real-time network monitor
    python mtu_optimizer.py --stable   Connection stability test
    python mtu_optimizer.py --trace    Traceroute to ME server
    python mtu_optimizer.py --warp     Check Cloudflare WARP
    python mtu_optimizer.py --route    Inject Riot static routes
    python mtu_optimizer.py --apply    Apply all tweaks
    python mtu_optimizer.py --restore  Restore defaults
    python mtu_optimizer.py --export   Export report (JSON/HTML/TXT)
    """,
    )
    parser.add_argument("--scan",     action="store_true", help="Full scan, no changes")
    parser.add_argument("--mtu-only", action="store_true", help="MTU finder only")
    parser.add_argument("--ping",     action="store_true", help="Server ping test only")
    parser.add_argument("--dns-scan", action="store_true", help="DNS benchmark only")
    parser.add_argument("--speed",    action="store_true", help="Internet speed test")
    parser.add_argument("--monitor",  action="store_true", help="Real-time network monitor")
    parser.add_argument("--stable",   action="store_true", help="Connection stability test")
    parser.add_argument("--trace",    action="store_true", help="Traceroute to ME server")
    parser.add_argument("--warp",     action="store_true", help="Check Cloudflare WARP")
    parser.add_argument("--route",    action="store_true", help="Inject Riot static routes")
    parser.add_argument("--apply",    action="store_true", help="Apply all tweaks")
    parser.add_argument("--restore",  action="store_true", help="Restore defaults")
    parser.add_argument("--no-dns",   action="store_true", help="Skip DNS change")
    parser.add_argument("--export",   action="store_true", help="Export report")
    parser.add_argument("--game",     type=str, default="Valorant",
                        help="Game for ping test (Valorant, CS2, LoL, Apex, Fortnite)")

    args = parser.parse_args()

    # Check if any CLI flag was given
    has_flags = any([
        args.scan, args.mtu_only, args.ping, args.dns_scan, args.speed,
        args.monitor, args.stable, args.trace, args.warp, args.route,
        args.apply, args.restore, args.export,
    ])

    if not has_flags:
        # Launch interactive menu
        interactive_menu()
        return

    # ── CLI mode ──────────────────────────────────────────────────────────
    console.clear()
    show_banner()

    admin = is_admin()
    if admin:
        console.print(Panel(
            "  ✅ [bold green]Running as Administrator[/]",
            border_style="green", box=box.ROUNDED,
        ))
    else:
        console.print(Panel(
            "  ⚠️  [bold yellow]NOT running as Administrator[/]",
            border_style="yellow", box=box.ROUNDED,
        ))
    console.print()

    adapter = get_active_adapter()
    original_mtu = get_current_mtu(adapter)
    os_info = get_os_info()
    show_system_info(adapter, original_mtu, os_info)

    # Dispatch
    if args.restore:
        if not admin:
            console.print("[bold red]ERROR: Administrator required.[/]")
            sys.exit(1)
        results = restore_defaults(adapter)
        for ok, msg in results:
            icon = "✅" if ok else "❌"
            color = "green" if ok else "red"
            console.print(f"  {icon} [{color}]{msg}[/{color}]")
        console.print("\n[bold green]✅ Restored. Reboot recommended.[/]")
        return

    if args.ping:
        game = args.game
        servers = GAMES.get(game, GAMES["Valorant"])["servers"]
        results = run_ping_test(game, servers)
        reachable = [r for r in results if r.avg_ms > 0]
        if reachable:
            best = min(reachable, key=lambda r: r.avg_ms)
            console.print(
                f"  👑 Best: [bold bright_cyan]{best.region.strip()}[/] "
                f"@ [bold bright_green]{best.avg_ms} ms[/]"
            )
        return

    if args.dns_scan:
        run_dns_scanner(adapter=adapter if admin else None, auto_apply=False)
        return

    if args.speed:
        run_speed_test()
        return

    if args.monitor:
        run_network_monitor()
        return

    if args.stable:
        run_stability_test_ui()
        return

    if args.trace:
        run_traceroute("99.83.199.240", "ME - Bahrain (Valorant)")
        return

    if args.warp:
        check_warp()
        return

    if args.route:
        if not admin:
            console.print("[bold red]ERROR: --route requires Administrator.[/]")
            sys.exit(1)
        run_route_optimizer()
        return

    if args.mtu_only:
        run_mtu_finder(scan_only=args.scan)
        return

    # Full scan or --apply
    recommended_mtu = run_mtu_finder(scan_only=args.scan)

    game = args.game
    servers = GAMES.get(game, GAMES["Valorant"])["servers"]
    ping_results = run_ping_test(game, servers)
    reachable = [r for r in ping_results if r.avg_ms > 0]
    best_region = min(reachable, key=lambda r: r.avg_ms) if reachable else None

    best_dns: Optional[DnsResult] = None
    if not args.no_dns:
        best_dns = run_dns_scanner(
            adapter=adapter if admin and not args.scan else None,
            auto_apply=bool(args.apply),
        )

    # Quality score
    qs = compute_quality_score(
        best_ping=best_region,
        dns_result=best_dns,
        current_mtu=original_mtu,
        optimal_mtu=recommended_mtu,
    )
    show_quality_score(qs)

    # Apply tweaks
    tweaks_applied = []
    can_apply = admin and not args.scan
    if can_apply:
        do_apply = args.apply or Confirm.ask(
            "  [bold yellow]Apply network optimizations?[/]",
            default=True, console=console,
        )
        if do_apply:
            create_backup(adapter)
            tweaks_applied = run_tweaks(
                adapter, recommended_mtu,
                dns=not args.no_dns, best_dns=best_dns,
            )

    console.print()
    console.print(build_summary_panel(
        recommended_mtu, original_mtu, best_region,
        tweaks_applied, scan_only=not can_apply,
    ))
    console.print()

    if tweaks_applied:
        console.print(Align.center(
            Text("⚡ All done! Reboot recommended for all changes to fully apply. ⚡",
                 style="bold bright_green"),
        ))
    console.print()
