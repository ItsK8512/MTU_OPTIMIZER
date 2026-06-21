"""
mtu_optimizer.export — Report export (JSON, HTML, plain text)
Exports scan results with system info, timestamps, and before/after comparison.
"""

import os
import json
import time
from pathlib import Path
from typing import Optional

from mtu_optimizer.ui import console, Panel, Rule, box, Prompt


def _export_dir() -> Path:
    base = Path(os.environ.get("APPDATA", os.path.expanduser("~")))
    d = base / "MTUOptimizer" / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def export_json(data: dict, filename: str = "") -> str:
    """Export report as JSON. Returns file path."""
    if not filename:
        filename = f"mtu_report_{time.strftime('%Y%m%d_%H%M%S')}.json"
    path = _export_dir() / filename

    report = {
        "tool": "MTU Optimizer",
        "version": "3.0.0",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        **data,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    return str(path)


def export_text(data: dict, filename: str = "") -> str:
    """Export report as plain text (good for Discord/forums)."""
    if not filename:
        filename = f"mtu_report_{time.strftime('%Y%m%d_%H%M%S')}.txt"
    path = _export_dir() / filename

    lines = [
        "=" * 60,
        "  MTU OPTIMIZER v3.0 — Network Report",
        f"  Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
    ]

    # System info
    if "system" in data:
        sys_info = data["system"]
        lines.append("── System Info ──")
        for k, v in sys_info.items():
            lines.append(f"  {k}: {v}")
        lines.append("")

    # MTU
    if "mtu" in data:
        lines.append("── MTU ──")
        mtu_info = data["mtu"]
        lines.append(f"  Current:  {mtu_info.get('current', '?')}")
        lines.append(f"  Optimal:  {mtu_info.get('optimal', '?')}")
        lines.append("")

    # Ping results
    if "ping_results" in data:
        lines.append("── Server Ping Results ──")
        lines.append(f"  {'Region':<30} {'Avg':>8} {'Min':>8} {'Jitter':>8} {'Loss':>8} {'Rating':>12}")
        lines.append("  " + "-" * 74)
        for r in data["ping_results"]:
            lines.append(
                f"  {r.get('region', '?'):<30} "
                f"{r.get('avg_ms', '?'):>6}ms "
                f"{r.get('min_ms', '?'):>6}ms "
                f"{r.get('jitter_ms', '?'):>6}ms "
                f"{r.get('loss_pct', '?'):>6}% "
                f"{r.get('rating', '?'):>12}"
            )
        lines.append("")

    # DNS results
    if "dns_results" in data:
        lines.append("── DNS Benchmark Results ──")
        lines.append(f"  {'#':>3} {'Provider':<30} {'Avg':>8} {'Rating':>12}")
        lines.append("  " + "-" * 53)
        for r in data["dns_results"][:10]:
            lines.append(
                f"  {r.get('rank', '?'):>3} "
                f"{r.get('name', '?'):<30} "
                f"{r.get('avg_ms', '?'):>6}ms "
                f"{r.get('rating', '?'):>12}"
            )
        lines.append("")

    # Speed test
    if "speedtest" in data:
        st = data["speedtest"]
        lines.append("── Speed Test ──")
        lines.append(f"  Download:  {st.get('download_mbps', '?')} Mbps")
        lines.append(f"  Upload:    {st.get('upload_mbps', '?')} Mbps")
        lines.append(f"  Idle Ping: {st.get('idle_ping_ms', '?')} ms")
        lines.append(f"  Bufferbloat: {st.get('bufferbloat', '?')}")
        lines.append("")

    # Quality score
    if "quality_score" in data:
        qs = data["quality_score"]
        lines.append("── Quality Score ──")
        lines.append(f"  Score: {qs.get('total', '?')}/100  Grade: {qs.get('grade', '?')}")
        lines.append("")

    # Tweaks
    if "tweaks" in data:
        lines.append("── Tweaks Applied ──")
        for ok, msg in data["tweaks"]:
            icon = "OK" if ok else "FAIL"
            lines.append(f"  [{icon}] {msg}")
        lines.append("")

    lines.append("=" * 60)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return str(path)


def export_html(data: dict, filename: str = "") -> str:
    """Export report as a styled HTML file."""
    if not filename:
        filename = f"mtu_report_{time.strftime('%Y%m%d_%H%M%S')}.html"
    path = _export_dir() / filename

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    # Build HTML sections
    sections = []

    # System info
    if "system" in data:
        rows = ""
        for k, v in data["system"].items():
            rows += f"<tr><td class='key'>{k}</td><td>{v}</td></tr>"
        sections.append(f"""
        <div class="card">
            <h2>🖥️ System Info</h2>
            <table>{rows}</table>
        </div>""")

    # Ping results
    if "ping_results" in data:
        rows = ""
        for r in data["ping_results"]:
            avg = r.get("avg_ms", -1)
            color = "#4caf50" if avg < 50 else "#ff9800" if avg < 100 else "#f44336" if avg > 0 else "#666"
            rows += f"""<tr>
                <td>{r.get('region', '?')}</td>
                <td style='color:{color};font-weight:bold'>{avg}ms</td>
                <td>{r.get('min_ms', '?')}ms</td>
                <td>{r.get('jitter_ms', '?')}ms</td>
                <td>{r.get('loss_pct', '?')}%</td>
                <td style='color:{color}'>{r.get('rating', '?')}</td>
            </tr>"""
        sections.append(f"""
        <div class="card">
            <h2>📡 Server Ping Results</h2>
            <table>
                <tr><th>Region</th><th>Avg</th><th>Min</th><th>Jitter</th><th>Loss</th><th>Rating</th></tr>
                {rows}
            </table>
        </div>""")

    # Quality score
    if "quality_score" in data:
        qs = data["quality_score"]
        score = qs.get("total", 0)
        grade = qs.get("grade", "?")
        color = "#4caf50" if score >= 75 else "#ff9800" if score >= 50 else "#f44336"
        sections.append(f"""
        <div class="card score-card">
            <h2>⚡ Quality Score</h2>
            <div class="score" style="color:{color}">{score}/100</div>
            <div class="grade" style="color:{color}">Grade: {grade}</div>
        </div>""")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MTU Optimizer Report — {timestamp}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            padding: 2rem;
        }}
        .header {{
            text-align: center;
            margin-bottom: 2rem;
            padding: 2rem;
            background: linear-gradient(135deg, #1a1a2e, #16213e);
            border-radius: 12px;
            border: 1px solid #30363d;
        }}
        .header h1 {{
            color: #ff4444;
            font-size: 2rem;
            margin-bottom: 0.5rem;
        }}
        .header .subtitle {{
            color: #8b949e;
            font-size: 0.9rem;
        }}
        .card {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }}
        .card h2 {{
            color: #58a6ff;
            margin-bottom: 1rem;
            font-size: 1.2rem;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 0.5rem 1rem;
            text-align: left;
            border-bottom: 1px solid #21262d;
        }}
        th {{ color: #8b949e; font-weight: 600; }}
        .key {{ color: #8b949e; width: 150px; }}
        .score-card {{ text-align: center; }}
        .score {{ font-size: 3rem; font-weight: 800; margin: 1rem 0; }}
        .grade {{ font-size: 1.5rem; font-weight: 600; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>⚡ MTU Optimizer v3.0</h1>
        <div class="subtitle">Network Report — {timestamp}</div>
    </div>
    {''.join(sections)}
</body>
</html>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    return str(path)


# ── UI ────────────────────────────────────────────────────────────────────────
def run_export_menu(data: dict) -> None:
    """Interactive export menu."""
    console.print(Rule("[bold cyan]📋 Export Report[/]", style="cyan"))
    console.print()
    console.print("  Choose export format:")
    console.print("    [cyan]1[/] JSON (machine-readable)")
    console.print("    [cyan]2[/] HTML (beautiful, shareable)")
    console.print("    [cyan]3[/] Text (for Discord/forums)")
    console.print("    [cyan]4[/] All formats")
    console.print()

    choice = Prompt.ask(
        "  [bold yellow]Format[/]",
        choices=["1", "2", "3", "4"],
        default="4",
        console=console,
    )

    paths = []
    if choice in ("1", "4"):
        p = export_json(data)
        paths.append(("JSON", p))
    if choice in ("2", "4"):
        p = export_html(data)
        paths.append(("HTML", p))
    if choice in ("3", "4"):
        p = export_text(data)
        paths.append(("Text", p))

    console.print()
    for fmt, path in paths:
        console.print(f"  ✅ [green]{fmt}:[/] [dim]{path}[/]")

    console.print()
    console.print(Panel(
        f"  Reports saved to: [dim]{_export_dir()}[/]",
        border_style="dim", box=box.ROUNDED,
    ))
    console.print()
