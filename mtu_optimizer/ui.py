"""
mtu_optimizer.ui — Rich console UI helpers
Centralises all styling, color mappings, table builders, and banner rendering.
"""

from rich.console import Console
from rich.text import Text
from rich.align import Align
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich import box
from rich.style import Style
from rich.prompt import Confirm, Prompt
from rich.markup import escape
from rich.live import Live
from rich.layout import Layout
from rich.columns import Columns

from mtu_optimizer import __version__

console = Console()

# ── Banner ────────────────────────────────────────────────────────────────────
BANNER = r"""
  __  __ _____ _   _    ___  ____ _____ ___ __  __ ___ ___________ ____  
 |  \/  |_   _| | | |  / _ \|  _ \_   _|_ _|  \/  |_ _|__  / ____|  _ \ 
 | |\/| | | | | | | | | | | | |_) || |  | || |\/| || |  / /|  _| | |_) |
 | |  | | | | | |_| | | |_| |  __/ | |  | || |  | || | / /_| |___|  _ < 
 |_|  |_| |_|  \___/   \___/|_|    |_| |___|_|  |_|___/____|_____|_| \_\
"""

SUBTITLE_GAMES = "Valorant · CS2 · League · Apex · Fortnite"


def show_banner():
    """Display the main application banner."""
    try:
        console.print(Text(BANNER, style="bold bright_red"), justify="center")
    except Exception:
        console.print("[bold bright_red]  MTU OPTIMIZER[/] — Gaming Network Suite")
    console.print(
        Align.center(
            Text(
                f"  v{__version__}  |  {SUBTITLE_GAMES}  |  Windows  ",
                style="dim white on grey11",
            )
        )
    )
    console.print()


# ── Color mappings ────────────────────────────────────────────────────────────
def ping_color(ms: float) -> str:
    """Return Rich color style for a latency value."""
    if ms < 0:
        return "dim"
    if ms < 40:
        return "bold bright_green"
    if ms < 70:
        return "bold green"
    if ms < 100:
        return "bold yellow"
    if ms < 150:
        return "bold red"
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


def score_color(score: int) -> str:
    """Color for the 0-100 quality score."""
    if score >= 90:
        return "bold bright_green"
    if score >= 75:
        return "bold green"
    if score >= 60:
        return "bold yellow"
    if score >= 40:
        return "bold red"
    return "bold bright_red"


def score_grade(score: int) -> str:
    """Letter grade from a 0-100 score."""
    if score >= 95:
        return "S"
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def grade_color(grade: str) -> str:
    return {
        "S": "bold bright_cyan",
        "A": "bold bright_green",
        "B": "bold green",
        "C": "bold yellow",
        "D": "bold red",
        "F": "bold bright_red",
    }.get(grade, "white")


# ── Sparkline ─────────────────────────────────────────────────────────────────
SPARK_CHARS = "▁▂▃▄▅▆▇█"


def sparkline(values: list[float], width: int = 20) -> str:
    """Return a sparkline string for a list of numeric values."""
    if not values:
        return ""
    mn, mx = min(values), max(values)
    rng = mx - mn if mx != mn else 1
    # Take last `width` values
    recent = values[-width:]
    return "".join(
        SPARK_CHARS[min(len(SPARK_CHARS) - 1, int((v - mn) / rng * (len(SPARK_CHARS) - 1)))]
        for v in recent
    )


# ── Progress factory ─────────────────────────────────────────────────────────
def make_progress(description_width: int = 40, bar_width: int = 35,
                  bar_color: str = "red", extra_columns: list | None = None) -> Progress:
    """Create a consistently-styled Rich Progress bar."""
    cols = [
        SpinnerColumn(spinner_name="dots12", style=f"bold {bar_color}"),
        TextColumn("[bold white]{task.description}", table_column=None),
        BarColumn(bar_width=bar_width, style=bar_color, complete_style="bright_green"),
    ]
    if extra_columns:
        cols.extend(extra_columns)
    cols.append(TimeElapsedColumn())
    return Progress(*cols, console=console, transient=False)


# ── Gauge bar ─────────────────────────────────────────────────────────────────
def gauge_bar(value: int, max_val: int = 100, width: int = 30) -> str:
    """Return a text-based gauge bar: [████████░░░░░░] 75/100."""
    filled = int(value / max_val * width)
    empty = width - filled
    bar = "█" * filled + "░" * empty
    return f"[{bar}] {value}/{max_val}"


# ── System info header ────────────────────────────────────────────────────────
def show_system_info(adapter: str, mtu: int, os_info: str,
                     isp: str = "", public_ip: str = "", score: int = -1):
    """Display the system information header bar."""
    lines = []
    lines.append(f"  🖥️  Adapter    : [cyan]{adapter}[/]")
    lines.append(f"  📦 Current MTU : [yellow]{mtu}[/] bytes")
    lines.append(f"  🖥️  OS         : [dim]{os_info}[/]")
    if isp:
        lines.append(f"  🌐 ISP        : [cyan]{isp}[/]")
    if public_ip:
        lines.append(f"  🌍 Public IP  : [dim]{public_ip}[/]")
    if score >= 0:
        grade = score_grade(score)
        gc = grade_color(grade)
        sc = score_color(score)
        lines.append(f"  ⚡ Quality    : [{sc}]{gauge_bar(score)}[/]  [{gc}]Grade: {grade}[/]")

    console.print(Panel(
        "\n".join(lines),
        title="[bold bright_white]System Info[/]",
        border_style="dim",
        box=box.ROUNDED,
        padding=(0, 1),
    ))
    console.print()
