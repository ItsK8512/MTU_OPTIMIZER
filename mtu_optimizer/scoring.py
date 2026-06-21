"""
mtu_optimizer.scoring — Connection quality scoring system
Computes a 0-100 composite score and letter grade (S/A/B/C/D/F)
based on ping, jitter, packet loss, MTU, DNS speed, and applied tweaks.
"""

from dataclasses import dataclass
from typing import Optional

from mtu_optimizer.core import PingResult, StabilityResult
from mtu_optimizer.dns import DnsResult
from mtu_optimizer.ui import (
    console, score_color, score_grade, grade_color, gauge_bar,
    Panel, box,
)


@dataclass
class QualityScore:
    total: int
    grade: str
    ping_score: int
    jitter_score: int
    loss_score: int
    mtu_score: int
    dns_score: int
    tweaks_score: int
    breakdown: dict


def _score_ping(avg_ms: float) -> int:
    """Score ping on a 0-100 scale."""
    if avg_ms < 0:
        return 0
    if avg_ms < 30:
        return 100
    if avg_ms < 50:
        return 90
    if avg_ms < 70:
        return 75
    if avg_ms < 100:
        return 60
    if avg_ms < 150:
        return 30
    return 10


def _score_jitter(jitter_ms: float) -> int:
    if jitter_ms < 0:
        return 0
    if jitter_ms < 3:
        return 100
    if jitter_ms < 5:
        return 85
    if jitter_ms < 10:
        return 70
    if jitter_ms < 20:
        return 40
    return 10


def _score_loss(loss_pct: float) -> int:
    if loss_pct <= 0:
        return 100
    if loss_pct < 0.5:
        return 90
    if loss_pct < 1:
        return 80
    if loss_pct < 3:
        return 50
    if loss_pct < 5:
        return 25
    return 0


def _score_mtu(current_mtu: int, optimal_mtu: int) -> int:
    diff = abs(current_mtu - optimal_mtu)
    if diff == 0:
        return 100
    if diff <= 20:
        return 90
    if diff <= 50:
        return 80
    if diff <= 100:
        return 60
    return 50


def _score_dns(avg_ms: float) -> int:
    if avg_ms < 0:
        return 0
    if avg_ms < 10:
        return 100
    if avg_ms < 20:
        return 90
    if avg_ms < 30:
        return 80
    if avg_ms < 60:
        return 50
    return 20


def _score_tweaks(applied: int, total: int) -> int:
    if total == 0:
        return 50
    return int(applied / total * 100)


def compute_quality_score(
    best_ping: Optional[PingResult] = None,
    dns_result: Optional[DnsResult] = None,
    current_mtu: int = 1500,
    optimal_mtu: int = 1500,
    tweaks_applied: int = 0,
    tweaks_total: int = 8,
) -> QualityScore:
    """
    Compute a weighted composite quality score (0-100).

    Weights:
      Ping:   30%
      Jitter: 25%
      Loss:   20%
      MTU:    10%
      DNS:    10%
      Tweaks:  5%
    """
    # Extract values
    ping_ms = best_ping.avg_ms if best_ping and best_ping.avg_ms >= 0 else 999
    jitter_ms = best_ping.jitter_ms if best_ping else 99
    loss_pct = best_ping.loss_pct if best_ping else 100
    dns_ms = dns_result.avg_ms if dns_result and dns_result.avg_ms >= 0 else 999

    # Individual scores
    ps = _score_ping(ping_ms)
    js = _score_jitter(jitter_ms)
    ls = _score_loss(loss_pct)
    ms = _score_mtu(current_mtu, optimal_mtu)
    ds = _score_dns(dns_ms)
    ts = _score_tweaks(tweaks_applied, tweaks_total)

    # Weighted total
    total = int(
        ps * 0.30 +
        js * 0.25 +
        ls * 0.20 +
        ms * 0.10 +
        ds * 0.10 +
        ts * 0.05
    )
    total = max(0, min(100, total))
    grade = score_grade(total)

    breakdown = {
        "Ping":    {"score": ps, "weight": "30%", "value": f"{ping_ms}ms"},
        "Jitter":  {"score": js, "weight": "25%", "value": f"{jitter_ms}ms"},
        "Loss":    {"score": ls, "weight": "20%", "value": f"{loss_pct}%"},
        "MTU":     {"score": ms, "weight": "10%", "value": f"{current_mtu}/{optimal_mtu}"},
        "DNS":     {"score": ds, "weight": "10%", "value": f"{dns_ms}ms"},
        "Tweaks":  {"score": ts, "weight": "5%",  "value": f"{tweaks_applied}/{tweaks_total}"},
    }

    return QualityScore(
        total=total, grade=grade,
        ping_score=ps, jitter_score=js, loss_score=ls,
        mtu_score=ms, dns_score=ds, tweaks_score=ts,
        breakdown=breakdown,
    )


def show_quality_score(qs: QualityScore) -> None:
    """Display the quality score with a visual gauge and breakdown."""
    sc = score_color(qs.total)
    gc = grade_color(qs.grade)

    # Build breakdown lines
    breakdown_lines = []
    for name, info in qs.breakdown.items():
        bar_filled = int(info["score"] / 100 * 15)
        bar_empty = 15 - bar_filled
        bar = "█" * bar_filled + "░" * bar_empty
        sc2 = score_color(info["score"])
        breakdown_lines.append(
            f"    {name:<8} [{sc2}]{bar} {info['score']:>3}/100[/]  "
            f"[dim]({info['weight']}, {info['value']})[/]"
        )

    breakdown_text = "\n".join(breakdown_lines)

    console.print(Panel(
        f"\n  [{gc}]   ██████  GRADE: {qs.grade}  ██████   [/]\n\n"
        f"  [{sc}]{gauge_bar(qs.total, width=40)}[/]\n\n"
        f"  [bold white]Score Breakdown:[/]\n"
        f"{breakdown_text}\n",
        title="[bold bright_cyan]⚡ Connection Quality Score[/]",
        border_style="bright_cyan",
        box=box.DOUBLE_EDGE,
        padding=(1, 3),
    ))
    console.print()
