"""Logique de verdict O/U — pace, GAP, signaux contextuels, EV."""

from __future__ import annotations

from dataclasses import dataclass

from sofascore import HalftimeData
from odds import OULine
from config import GAP_STRONG, GAP_WEAK, SHOOTING_HIGH, FOULS_HIGH, ML_BLOWOUT


@dataclass
class Verdict:
    """Résultat de l'analyse O/U à la mi-temps."""
    match: str
    league: str
    signal: str           # "OVER ✅", "UNDER ✅", "PASSER ⏭️"
    home_score: int
    away_score: int
    pace: float
    line: float
    gap: float
    home_fg_pct: float
    away_fg_pct: float
    total_fouls: int
    total_off_reb: int
    ev: float
    over_odds: float
    under_odds: float
    reasoning: str        # Explication courte du verdict


def analyze(data: HalftimeData, line: OULine) -> Verdict:
    """Analyse complète mi-temps → verdict O/U.

    Logique :
    - Pace = score_total / 20 * 40  (mi-temps = 20 min)
    - GAP = pace - ligne
    - |GAP| >= 8 → signal fort
    - |GAP| < 3  → PASSER
    - Entre 3 et 8 → analyser contexte (shooting, fautes, tempo)
    """
    total_ht = data.home_score + data.away_score
    pace = total_ht / 20 * 40
    gap = pace - line.total

    home_fg = data.home_fg_pct
    away_fg = data.away_fg_pct
    fouls = data.total_fouls

    # ── Signaux contextuels ────────────────────────────────────
    # Shooting insoutenable → régression vers la moyenne = UNDER
    shooting_unsustainable = home_fg > SHOOTING_HIGH or away_fg > SHOOTING_HIGH

    # Fautes élevées → lancers francs à venir = OVER
    fouls_high = fouls > FOULS_HIGH

    # ── Verdict ────────────────────────────────────────────────
    abs_gap = abs(gap)
    reasons = []

    if abs_gap >= GAP_STRONG:
        # Signal fort
        if gap > 0:
            signal = "OVER ✅"
            reasons.append(f"GAP fort +{gap:.1f}")
            if shooting_unsustainable:
                reasons.append("⚠️ FG% élevé → régression possible")
        else:
            signal = "UNDER ✅"
            reasons.append(f"GAP fort {gap:.1f}")
            if fouls_high:
                reasons.append("⚠️ Fautes élevées → LF à venir")

    elif abs_gap < GAP_WEAK:
        # GAP trop faible → PASSER
        signal = "PASSER ⏭️"
        reasons.append(f"GAP insuffisant ({gap:+.1f})")

    else:
        # Zone grise (3–8) → contexte décide
        if gap > 0:
            # Tendance OVER
            if shooting_unsustainable:
                signal = "PASSER ⏭️"
                reasons.append(f"GAP modéré +{gap:.1f} mais FG% insoutenable")
            elif fouls_high:
                signal = "OVER ✅"
                reasons.append(f"GAP +{gap:.1f} renforcé par fautes élevées ({fouls})")
            else:
                signal = "OVER ✅"
                reasons.append(f"GAP modéré +{gap:.1f}")
        else:
            # Tendance UNDER
            if fouls_high:
                signal = "PASSER ⏭️"
                reasons.append(f"GAP {gap:.1f} mais fautes élevées contrebalancent")
            elif shooting_unsustainable:
                signal = "UNDER ✅"
                reasons.append(f"GAP {gap:.1f} renforcé par FG% insoutenable")
            else:
                signal = "UNDER ✅"
                reasons.append(f"GAP modéré {gap:.1f}")

    # ── EV estimé ──────────────────────────────────────────────
    if "OVER" in signal:
        # Probabilité estimée = 50% + 2% par point de GAP
        fair_prob = min(0.95, 0.50 + abs_gap * 0.02)
        ev = (fair_prob * line.over_odds) - 1
    elif "UNDER" in signal:
        fair_prob = min(0.95, 0.50 + abs_gap * 0.02)
        ev = (fair_prob * line.under_odds) - 1
    else:
        ev = 0.0

    return Verdict(
        match=f"{data.home_team} vs {data.away_team}",
        league=data.league,
        signal=signal,
        home_score=data.home_score,
        away_score=data.away_score,
        pace=round(pace, 1),
        line=line.total,
        gap=round(gap, 1),
        home_fg_pct=home_fg,
        away_fg_pct=away_fg,
        total_fouls=fouls,
        total_off_reb=data.total_off_reb,
        ev=round(ev, 4),
        over_odds=line.over_odds,
        under_odds=line.under_odds,
        reasoning=" | ".join(reasons),
    )
