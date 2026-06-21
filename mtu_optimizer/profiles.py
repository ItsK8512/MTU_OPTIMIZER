"""
mtu_optimizer.profiles — Configuration profile management
Save, load, compare, import/export optimization profiles as JSON.
Stored in %APPDATA%/MTUOptimizer/profiles/
"""

import os
import json
import time
from pathlib import Path
from typing import Optional

from mtu_optimizer.ui import console, Panel, Table, Rule, box, Confirm, Prompt


# ── Profile directory ─────────────────────────────────────────────────────────
def _profiles_dir() -> Path:
    base = Path(os.environ.get("APPDATA", os.path.expanduser("~")))
    d = base / "MTUOptimizer" / "profiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _profile_path(name: str) -> Path:
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name)
    return _profiles_dir() / f"{safe_name}.json"


# ── Profile data ──────────────────────────────────────────────────────────────
def save_profile(name: str, data: dict) -> str:
    """Save a profile. Returns the file path."""
    profile = {
        "name": name,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "settings": data,
    }
    path = _profile_path(name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)
    return str(path)


def load_profile(name: str) -> Optional[dict]:
    """Load a profile by name. Returns None if not found."""
    path = _profile_path(name)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_profiles() -> list[dict]:
    """List all saved profiles with metadata."""
    profiles = []
    for f in _profiles_dir().glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                profiles.append({
                    "name": data.get("name", f.stem),
                    "created_at": data.get("created_at", "Unknown"),
                    "path": str(f),
                    "settings": data.get("settings", {}),
                })
        except Exception:
            pass
    return sorted(profiles, key=lambda p: p["created_at"], reverse=True)


def delete_profile(name: str) -> bool:
    """Delete a profile by name."""
    path = _profile_path(name)
    if path.exists():
        path.unlink()
        return True
    return False


def export_profile(name: str, export_path: str) -> bool:
    """Export a profile to an arbitrary path (for sharing)."""
    profile = load_profile(name)
    if not profile:
        return False
    with open(export_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)
    return True


def import_profile(import_path: str) -> Optional[str]:
    """Import a profile from a JSON file. Returns profile name or None."""
    try:
        with open(import_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        name = data.get("name", Path(import_path).stem)
        path = _profile_path(name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return name
    except Exception:
        return None


# ── Auto-save before changes ──────────────────────────────────────────────────
def auto_save_current_state(snapshot: dict) -> str:
    """Auto-save current network state before applying changes."""
    name = f"auto_backup_{time.strftime('%Y%m%d_%H%M%S')}"
    return save_profile(name, snapshot)


# ── UI ────────────────────────────────────────────────────────────────────────
def show_profiles_menu() -> None:
    """Interactive profile management menu."""
    console.print(Rule("[bold cyan]💾 Profile Manager[/]", style="cyan"))
    console.print()

    profiles = list_profiles()

    if not profiles:
        console.print("  [dim]No saved profiles yet.[/]")
        console.print("  [dim]Profiles are created automatically when you apply optimizations.[/]")
        console.print()
        return

    # Show table
    table = Table(
        title="[bold bright_cyan]Saved Profiles[/]",
        box=box.ROUNDED,
        border_style="cyan",
        header_style="bold white",
    )
    table.add_column("#", justify="right", style="dim", min_width=3)
    table.add_column("Name", style="bold white", min_width=30)
    table.add_column("Created", style="dim", min_width=20)
    table.add_column("MTU", justify="right", min_width=6)
    table.add_column("DNS", min_width=20)

    for i, p in enumerate(profiles):
        settings = p.get("settings", {})
        mtu = str(settings.get("mtu", "?"))
        dns = settings.get("dns", "?")
        table.add_row(str(i + 1), p["name"], p["created_at"], mtu, str(dns))

    console.print(table)
    console.print()

    # Actions
    console.print("  [bold]Actions:[/]")
    console.print("    [cyan]L[/] Load a profile  |  [cyan]D[/] Delete  |  [cyan]C[/] Compare  |  [cyan]Q[/] Back")
    console.print()

    choice = Prompt.ask(
        "  [bold yellow]Choose action[/]",
        choices=["l", "d", "c", "q"],
        default="q",
        console=console,
    )

    if choice == "l":
        idx = Prompt.ask("  Profile # to load", console=console)
        try:
            idx = int(idx) - 1
            if 0 <= idx < len(profiles):
                profile = profiles[idx]
                console.print(f"\n  Loaded profile: [bold cyan]{profile['name']}[/]")
                settings = profile.get("settings", {})
                for k, v in settings.items():
                    console.print(f"    {k}: [dim]{v}[/]")
                console.print()
                console.print("  [dim]To apply this profile, run optimizations with these settings.[/]")
            else:
                console.print("  [red]Invalid profile number.[/]")
        except ValueError:
            console.print("  [red]Invalid input.[/]")

    elif choice == "d":
        idx = Prompt.ask("  Profile # to delete", console=console)
        try:
            idx = int(idx) - 1
            if 0 <= idx < len(profiles):
                name = profiles[idx]["name"]
                if Confirm.ask(f"  Delete [bold]{name}[/]?", default=False, console=console):
                    delete_profile(name)
                    console.print(f"  ✅ [green]Deleted '{name}'[/]")
            else:
                console.print("  [red]Invalid profile number.[/]")
        except ValueError:
            console.print("  [red]Invalid input.[/]")

    elif choice == "c":
        if len(profiles) < 2:
            console.print("  [yellow]Need at least 2 profiles to compare.[/]")
            return

        idx1 = Prompt.ask("  First profile #", console=console)
        idx2 = Prompt.ask("  Second profile #", console=console)
        try:
            i1, i2 = int(idx1) - 1, int(idx2) - 1
            if 0 <= i1 < len(profiles) and 0 <= i2 < len(profiles):
                compare_profiles(profiles[i1], profiles[i2])
            else:
                console.print("  [red]Invalid profile numbers.[/]")
        except ValueError:
            console.print("  [red]Invalid input.[/]")

    console.print()


def compare_profiles(p1: dict, p2: dict) -> None:
    """Side-by-side comparison of two profiles."""
    table = Table(
        title="[bold cyan]Profile Comparison[/]",
        box=box.DOUBLE_EDGE,
        border_style="cyan",
        header_style="bold white",
    )
    table.add_column("Setting", style="bold white", min_width=20)
    table.add_column(p1["name"], min_width=25)
    table.add_column(p2["name"], min_width=25)

    s1 = p1.get("settings", {})
    s2 = p2.get("settings", {})
    all_keys = sorted(set(list(s1.keys()) + list(s2.keys())))

    for key in all_keys:
        v1 = str(s1.get(key, "[dim]—[/]"))
        v2 = str(s2.get(key, "[dim]—[/]"))
        if v1 != v2:
            v1 = f"[bold yellow]{v1}[/]"
            v2 = f"[bold yellow]{v2}[/]"
        table.add_row(key, v1, v2)

    console.print()
    console.print(table)
    console.print()
