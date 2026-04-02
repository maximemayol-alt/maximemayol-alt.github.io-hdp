"""Calculs : pace, projection, GAP vs ligne, EV estimé."""

from __future__ import annotations

from dataclasses import dataclass
from config import PACE_LEAGUE_BASE, EV_THRESHOLD, GAP_MIN_POINTS
from scraper import HalftimeStats
from pinnacle import PinnacleLine


@dataclass
class Verdict:
    """Résultat de l'analyse O/U."""
    match: str
    signal: str           # "OVER 🟢", "UNDER 🔵", "PASSER ⚪"
    projected_total: float
    line: float
    gap: float
    ev: float
    pace: float
    confidence: str       # "FORT", "MOYEN", "FAIBLE"
    details: str


def compute_pace(total_score: int, minutes_played: int) -> float:
    """Calcule le rythme actuel en points par 48 min (NBA) ou 40 min."""
    if minutes_played <= 0:
        return 0.0
    return (total_score / minutes_played) * 48.0


def project_total(
    stats: HalftimeStats,
    game_length: int = 48,
) -> float:
    """Projette le score total fin de match à partir du rythme actuel.

    Pondère le pace actuel et des facteurs correctifs :
    - % tirs (FG%) → impact sur l'efficacité scoring
    - Fautes → possessions bonus (lancers francs)
    - Rebonds offensifs → secondes chances
    """
    total_now = stats.home_score + stats.away_score
    mins = stats.minutes_played

    if mins <= 0:
        return 0.0

    # Pace brut
    pace_per_min = total_now / mins
    raw_projection = pace_per_min * game_length

    # Facteurs correctifs
    fg_avg = (stats.home_fg_pct + stats.away_fg_pct) / 2
    fg_factor = 1.0
    if fg_avg > 0:
        # Si FG% moyen > 45%, le scoring est soutenu ; < 40%, il va baisser
        fg_factor = 1.0 + (fg_avg - 42.5) * 0.004

    # Fautes → plus de lancers francs = plus de points
    total_fouls = stats.home_fouls + stats.away_fouls
    foul_rate = total_fouls / mins if mins > 0 else 0
    foul_factor = 1.0 + max(0, foul_rate - 0.4) * 0.02

    # Rebonds offensifs → secondes chances
    total_oreb = stats.home_off_reb + stats.away_off_reb
    oreb_rate = total_oreb / mins if mins > 0 else 0
    oreb_factor = 1.0 + max(0, oreb_rate - 0.2) * 0.015

    projected = raw_projection * fg_factor * foul_factor * oreb_factor
    return round(projected, 1)


def analyze(stats: HalftimeStats, line: PinnacleLine) -> Verdict:
    """Analyse complète : projection, GAP, EV, verdict."""
    match_name = f"{stats.home_team} vs {stats.away_team}"
    total_now = stats.home_score + stats.away_score
    pace = compute_pace(total_now, stats.minutes_played)
    projected = project_total(stats)

    gap = projected - line.total
    abs_gap = abs(gap)

    # Probabilité implicite depuis les cotes
    if gap > 0:
        # Tendance OVER
        implied_prob = 1 / line.over_odds if line.over_odds > 0 else 0.5
        fair_prob = min(0.95, 0.5 + abs_gap * 0.02)
        ev = (fair_prob * line.over_odds) - 1
        side = "OVER"
        odds_used = line.over_odds
    else:
        # Tendance UNDER
        implied_prob = 1 / line.under_odds if line.under_odds > 0 else 0.5
        fair_prob = min(0.95, 0.5 + abs_gap * 0.02)
        ev = (fair_prob * line.under_odds) - 1
        side = "UNDER"
        odds_used = line.under_odds

    # Confiance
    if abs_gap >= 8 and ev >= 0.06:
        confidence = "FORT"
    elif abs_gap >= GAP_MIN_POINTS and ev >= EV_THRESHOLD:
        confidence = "MOYEN"
    else:
        confidence = "FAIBLE"

    # Signal final
    if ev >= EV_THRESHOLD and abs_gap >= GAP_MIN_POINTS:
        emoji = "🟢" if side == "OVER" else "🔵"
        signal = f"{side} {emoji}"
    else:
        signal = "PASSER ⚪"

    details = (
        f"📊 Score actuel : {stats.home_score}-{stats.away_score} "
        f"({stats.minutes_played} min)\n"
        f"⏱ Pace : {pace:.1f} pts/48min\n"
        f"🎯 Projection : {projected}\n"
        f"📏 Ligne Pinnacle : {line.total} "
        f"(O {line.over_odds:.2f} / U {line.under_odds:.2f})\n"
        f"📐 GAP : {gap:+.1f} pts\n"
        f"💰 EV estimé : {ev:+.1%}\n"
        f"🔒 Confiance : {confidence}"
    )

    return Verdict(
        match=match_name,
        signal=signal,
        projected_total=projected,
        line=line.total,
        gap=gap,
        ev=ev,
        pace=pace,
        confidence=confidence,
        details=details,
    )
