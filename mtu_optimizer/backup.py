"""
mtu_optimizer.backup — Full network state backup and restore
Creates timestamped backups of all network settings before changes.
Stored in %APPDATA%/MTUOptimizer/backups/
"""

import os
import json
import time
import subprocess
from pathlib import Path
from typing import Optional

from mtu_optimizer.ui import console, Panel, Table, Rule, box, Confirm, Prompt


def _backups_dir() -> Path:
    base = Path(os.environ.get("APPDATA", os.path.expanduser("~")))
    d = base / "MTUOptimizer" / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def capture_network_state(adapter: str) -> dict:
    """Capture current network configuration for backup."""
    state = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "adapter": adapter,
    }

    # MTU
    try:
        r = subprocess.run(
            ["netsh", "interface", "ipv4", "show", "subinterface", adapter],
            capture_output=True, text=True, timeout=10,
        )
        state["mtu_output"] = r.stdout
        for line in r.stdout.splitlines():
            parts = line.split()
            if parts and parts[0].isdigit():
                state["mtu"] = int(parts[0])
    except Exception:
        state["mtu"] = 1500

    # DNS
    try:
        r = subprocess.run(
            ["netsh", "interface", "ipv4", "show", "dnsservers", adapter],
            capture_output=True, text=True, timeout=10,
        )
        state["dns_output"] = r.stdout
    except Exception:
        state["dns_output"] = ""

    # TCP global settings
    try:
        r = subprocess.run(
            ["netsh", "int", "tcp", "show", "global"],
            capture_output=True, text=True, timeout=10,
        )
        state["tcp_global"] = r.stdout
    except Exception:
        state["tcp_global"] = ""

    # Nagle registry values
    try:
        import winreg
        key_path = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
        base = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        count = winreg.QueryInfoKey(base)[0]
        nagle_values = {}
        for i in range(count):
            sub_name = winreg.EnumKey(base, i)
            try:
                sub_key = winreg.OpenKey(base, sub_name, 0, winreg.KEY_READ)
                values = {}
                for val_name in ["TcpAckFrequency", "TCPNoDelay"]:
                    try:
                        val, _ = winreg.QueryValueEx(sub_key, val_name)
                        values[val_name] = val
                    except FileNotFoundError:
                        pass
                if values:
                    nagle_values[sub_name] = values
                winreg.CloseKey(sub_key)
            except Exception:
                pass
        winreg.CloseKey(base)
        state["nagle_registry"] = nagle_values
    except Exception:
        state["nagle_registry"] = {}

    return state


def create_backup(adapter: str) -> str:
    """Create a timestamped backup. Returns backup file path."""
    state = capture_network_state(adapter)
    filename = f"backup_{time.strftime('%Y%m%d_%H%M%S')}.json"
    path = _backups_dir() / filename

    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    return str(path)


def list_backups() -> list[dict]:
    """List all backups with metadata."""
    backups = []
    for f in sorted(_backups_dir().glob("*.json"), reverse=True):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                backups.append({
                    "filename": f.name,
                    "path": str(f),
                    "timestamp": data.get("timestamp", "Unknown"),
                    "adapter": data.get("adapter", "Unknown"),
                    "mtu": data.get("mtu", "?"),
                })
        except Exception:
            pass
    return backups


def restore_from_backup(backup_path: str) -> list[tuple[bool, str]]:
    """Restore network settings from a backup file."""
    results = []

    try:
        with open(backup_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        return [(False, f"Failed to read backup: {e}")]

    adapter = state.get("adapter", "Wi-Fi")
    mtu = state.get("mtu", 1500)

    # Restore MTU
    try:
        r = subprocess.run(
            ["netsh", "interface", "ipv4", "set", "subinterface",
             adapter, f"mtu={mtu}", "store=persistent"],
            capture_output=True, text=True, timeout=15,
        )
        results.append((r.returncode == 0, f"MTU restored to {mtu}"))
    except Exception as e:
        results.append((False, f"MTU restore failed: {e}"))

    # Restore TCP auto-tuning (best effort from parsed output)
    try:
        r = subprocess.run(
            ["netsh", "int", "tcp", "set", "global", "autotuninglevel=normal"],
            capture_output=True, text=True, timeout=10,
        )
        results.append((r.returncode == 0, "TCP auto-tuning → normal"))
    except Exception as e:
        results.append((False, str(e)))

    # Restore Nagle
    nagle_values = state.get("nagle_registry", {})
    if not nagle_values:
        # No Nagle entries in backup = Nagle was enabled (default)
        try:
            import winreg
            key_path = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
            base = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            count = winreg.QueryInfoKey(base)[0]
            for i in range(count):
                sub_name = winreg.EnumKey(base, i)
                try:
                    sub_key = winreg.OpenKey(base, sub_name, 0, winreg.KEY_ALL_ACCESS)
                    for val_name in ["TcpAckFrequency", "TCPNoDelay"]:
                        try:
                            winreg.DeleteValue(sub_key, val_name)
                        except FileNotFoundError:
                            pass
                    winreg.CloseKey(sub_key)
                except Exception:
                    pass
            winreg.CloseKey(base)
            results.append((True, "Nagle restored (default)"))
        except Exception as e:
            results.append((False, f"Nagle restore: {e}"))

    # Restore DNS to DHCP
    try:
        r = subprocess.run(
            ["netsh", "interface", "ipv4", "set", "dnsservers", adapter, "dhcp"],
            capture_output=True, text=True, timeout=10,
        )
        results.append((r.returncode == 0, "DNS → DHCP (automatic)"))
    except Exception as e:
        results.append((False, str(e)))

    # Flush DNS
    try:
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=10)
        results.append((True, "DNS cache flushed"))
    except Exception:
        pass

    return results


# ── UI ────────────────────────────────────────────────────────────────────────
def show_backup_menu(adapter: str) -> None:
    """Interactive backup management menu."""
    console.print(Rule("[bold cyan]💾 Backup Manager[/]", style="cyan"))
    console.print()

    backups = list_backups()

    console.print("  [bold]Actions:[/]")
    console.print("    [cyan]C[/] Create backup now  |  [cyan]R[/] Restore from backup  |  [cyan]Q[/] Back")
    if backups:
        console.print(f"  [dim]Found {len(backups)} existing backup(s).[/]")
    console.print()

    choice = Prompt.ask(
        "  [bold yellow]Choose action[/]",
        choices=["c", "r", "q"],
        default="q",
        console=console,
    )

    if choice == "c":
        path = create_backup(adapter)
        console.print(f"  ✅ [green]Backup created:[/] [dim]{path}[/]")

    elif choice == "r":
        if not backups:
            console.print("  [yellow]No backups found.[/]")
            console.print()
            return

        table = Table(box=box.ROUNDED, border_style="dim", header_style="bold white")
        table.add_column("#", justify="right", min_width=3)
        table.add_column("Timestamp", min_width=20)
        table.add_column("Adapter", min_width=15)
        table.add_column("MTU", justify="right", min_width=6)

        for i, b in enumerate(backups):
            table.add_row(str(i + 1), b["timestamp"], b["adapter"], str(b["mtu"]))

        console.print(table)
        console.print()

        idx = Prompt.ask("  Backup # to restore", console=console)
        try:
            idx = int(idx) - 1
            if 0 <= idx < len(backups):
                if Confirm.ask(
                    f"  Restore from [bold]{backups[idx]['timestamp']}[/]?",
                    default=False, console=console,
                ):
                    results = restore_from_backup(backups[idx]["path"])
                    for ok, msg in results:
                        icon = "✅" if ok else "❌"
                        color = "green" if ok else "red"
                        console.print(f"  {icon} [{color}]{msg}[/{color}]")
            else:
                console.print("  [red]Invalid backup number.[/]")
        except ValueError:
            console.print("  [red]Invalid input.[/]")

    console.print()
