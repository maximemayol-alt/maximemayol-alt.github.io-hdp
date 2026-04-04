"""Logique de verdict O/U — pace, GAP, signaux contextuels, EV."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

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
    home_fg_pct: float
    away_fg_pct: float
    total_fouls: int
    total_off_reb: int
    reasoning: str
    # Présents uniquement si cote disponible (mode complet)
    has_line: bool = False
    line: float = 0.0
    gap: float = 0.0
    ev: float = 0.0
    over_odds: float = 0.0
    under_odds: float = 0.0
    home_ml: float = 0.0
    away_ml: float = 0.0


def _ml_is_blowout(home_ml: float, away_ml: float) -> bool:
    """Détecte si un favori écrase le match (ML < 1.30)."""
    if home_ml > 0 and home_ml < ML_BLOWOUT:
        return True
    if away_ml > 0 and away_ml < ML_BLOWOUT:
        return True
    return False


def _directional_signal(pace: float, home_fg: float, away_fg: float, fouls: int) -> tuple[str, list[str]]:
    """Signal directionnel basé sur le pace et le contexte, sans ligne."""
    reasons = []

    shooting_hot = home_fg > SHOOTING_HIGH or away_fg > SHOOTING_HIGH
    fouls_high = fouls > FOULS_HIGH

    if pace >= 180:
        if shooting_hot:
            signal = "OVER ✅"
            reasons.append(f"Pace élevé ({pace:.0f}) mais FG% chaud → régression possible")
        else:
            signal = "OVER ✅"
            reasons.append(f"Pace très élevé ({pace:.0f})")
        if fouls_high:
            reasons.append(f"Fautes élevées ({fouls}) → LF à venir")
    elif pace <= 140:
        if fouls_high:
            signal = "PASSER ⏭️"
            reasons.append(f"Pace bas ({pace:.0f}) mais fautes ({fouls}) → LF possibles")
        else:
            signal = "UNDER ✅"
            reasons.append(f"Pace bas ({pace:.0f})")
        if shooting_hot:
            reasons.append("FG% insoutenable → renforce UNDER")
    else:
        # Zone neutre 140–180
        if shooting_hot and not fouls_high:
            signal = "UNDER ✅"
            reasons.append(f"Pace neutre ({pace:.0f}) + FG% insoutenable → régression")
        elif fouls_high and not shooting_hot:
            signal = "OVER ✅"
            reasons.append(f"Pace neutre ({pace:.0f}) + fautes élevées ({fouls})")
        else:
            signal = "PASSER ⏭️"
            reasons.append(f"Pace neutre ({pace:.0f}) — pas de signal clair")

    return signal, reasons


def analyze_with_line(data: HalftimeData, line: OULine) -> Verdict:
    """Analyse complète avec cote O/U — GAP + EV + signal ML."""
    total_ht = data.home_score + data.away_score
    pace = total_ht / 20 * 40
    gap = pace - line.total

    home_fg = data.home_fg_pct
    away_fg = data.away_fg_pct
    fouls = data.total_fouls

    shooting_unsustainable = home_fg > SHOOTING_HIGH or away_fg > SHOOTING_HIGH
    fouls_high = fouls > FOULS_HIGH
    blowout = _ml_is_blowout(line.home_ml, line.away_ml)

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
        # GAP trop faible
        signal = "PASSER ⏭️"
        reasons.append(f"GAP insuffisant ({gap:+.1f})")
    else:
        # Zone grise (3–8) → contexte décide
        if gap > 0:
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
            if fouls_high:
                signal = "PASSER ⏭️"
                reasons.append(f"GAP {gap:.1f} mais fautes élevées contrebalancent")
            elif shooting_unsustainable:
                signal = "UNDER ✅"
                reasons.append(f"GAP {gap:.1f} renforcé par FG% insoutenable")
            else:
                signal = "UNDER ✅"
                reasons.append(f"GAP modéré {gap:.1f}")

    # Signal ML : favori écrasant + GAP faible → PASSER
    if blowout and abs_gap < GAP_STRONG:
        fav_ml = min(line.home_ml, line.away_ml) if line.home_ml > 0 and line.away_ml > 0 else 0
        if fav_ml > 0:
            signal = "PASSER ⏭️"
            reasons.append(f"ML favori {fav_ml:.2f} < {ML_BLOWOUT} → gestion tempo")

    # EV estimé
    if "OVER" in signal:
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
        home_fg_pct=home_fg,
        away_fg_pct=away_fg,
        total_fouls=fouls,
        total_off_reb=data.total_off_reb,
        reasoning=" | ".join(reasons),
        has_line=True,
        line=line.total,
        gap=round(gap, 1),
        ev=round(ev, 4),
        over_odds=line.over_odds,
        under_odds=line.under_odds,
        home_ml=line.home_ml,
        away_ml=line.away_ml,
    )


def analyze_pace_only(data: HalftimeData) -> Verdict:
    """Analyse pace-only — sans cote, signal directionnel."""
    total_ht = data.home_score + data.away_score
    pace = total_ht / 20 * 40

    signal, reasons = _directional_signal(
        pace, data.home_fg_pct, data.away_fg_pct, data.total_fouls,
    )

    return Verdict(
        match=f"{data.home_team} vs {data.away_team}",
        league=data.league,
        signal=signal,
        home_score=data.home_score,
        away_score=data.away_score,
        pace=round(pace, 1),
        home_fg_pct=data.home_fg_pct,
        away_fg_pct=data.away_fg_pct,
        total_fouls=data.total_fouls,
        total_off_reb=data.total_off_reb,
        reasoning=" | ".join(reasons),
        has_line=False,
    )
