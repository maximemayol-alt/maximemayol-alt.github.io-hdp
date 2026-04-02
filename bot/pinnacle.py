"""Récupération des lignes O/U — multi-sources avec fallback."""

from __future__ import annotations

import httpx
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class PinnacleLine:
    """Ligne O/U pour un match."""
    total: float          # Ligne (ex: 210.5)
    over_odds: float      # Cote OVER décimale
    under_odds: float     # Cote UNDER décimale
    home_team: str = ""
    away_team: str = ""
    source: str = ""      # "pinnacle", "manual", etc.


# ── Lignes entrées manuellement via Telegram ──────────────────
_manual_lines: dict[str, PinnacleLine] = {}


def set_manual_line(match_key: str, total: float, over_odds: float, under_odds: float) -> PinnacleLine:
    """Enregistre une ligne O/U manuellement (via commande Telegram)."""
    line = PinnacleLine(
        total=total,
        over_odds=over_odds,
        under_odds=under_odds,
        source="manual",
    )
    _manual_lines[match_key.lower()] = line
    return line


def get_manual_line(home: str, away: str) -> Optional[PinnacleLine]:
    """Cherche une ligne manuelle correspondant au match."""
    for key, line in _manual_lines.items():
        if home.lower() in key or away.lower() in key:
            return line
    return None


def clear_manual_lines() -> None:
    """Efface toutes les lignes manuelles."""
    _manual_lines.clear()


# ── Pinnacle API (peut échouer si géo-bloqué) ─────────────────

PINNACLE_MATCHUPS_URL = "https://guest.api.arcadia.pinnacle.com/0.1/sports/4/matchups"
PINNACLE_ODDS_URL = "https://guest.api.arcadia.pinnacle.com/0.1/sports/4/markets/straight"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Origin": "https://www.pinnacle.com",
    "Referer": "https://www.pinnacle.com/",
    "X-Api-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
}


async def fetch_pinnacle_lines() -> list[dict]:
    """Récupère les lignes O/U basket live depuis Pinnacle.
    Retourne une liste vide si l'API est bloquée."""
    try:
        async with httpx.AsyncClient(timeout=10, headers=HEADERS) as client:
            resp_matchups = await client.get(
                PINNACLE_MATCHUPS_URL, params={"isLive": "true"}
            )
            resp_matchups.raise_for_status()
            matchups = resp_matchups.json()

            resp_odds = await client.get(
                PINNACLE_ODDS_URL, params={"isLive": "true"}
            )
            resp_odds.raise_for_status()
            odds_data = resp_odds.json()
    except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException):
        return []

    # Indexer les matchups
    matchup_map = {}
    for m in matchups:
        mid = m.get("id")
        participants = m.get("participants", [])
        if len(participants) >= 2:
            home = next((p["name"] for p in participants if p.get("alignment") == "home"), participants[0]["name"])
            away = next((p["name"] for p in participants if p.get("alignment") == "away"), participants[1]["name"])
            matchup_map[mid] = {"home": home, "away": away}

    # Extraire les lignes totals
    lines = []
    for item in odds_data:
        matchup_id = item.get("matchupId")
        if matchup_id not in matchup_map:
            continue

        for price in item.get("prices", []):
            if price.get("type") != "total":
                continue
            points = price.get("points")
            designation = price.get("designation")
            dec_odds = price.get("price", 0)
            if points is None:
                continue

            key = (matchup_id, points)
            existing = next((l for l in lines if (l["matchup_id"], l["total"]) == key), None)
            if not existing:
                existing = {
                    "matchup_id": matchup_id,
                    "total": points,
                    "over_odds": 0.0,
                    "under_odds": 0.0,
                    **matchup_map[matchup_id],
                }
                lines.append(existing)

            if designation == "over":
                existing["over_odds"] = _american_to_decimal(dec_odds)
            elif designation == "under":
                existing["under_odds"] = _american_to_decimal(dec_odds)

    return lines


def _american_to_decimal(american: float) -> float:
    """Convertit cote américaine → décimale."""
    if american >= 100:
        return 1 + american / 100
    elif american <= -100:
        return 1 + 100 / abs(american)
    return american if american > 1 else 2.0


def find_matching_line(
    pinnacle_lines: list[dict],
    home_team: str,
    away_team: str,
) -> Optional[PinnacleLine]:
    """Trouve la ligne correspondant au match — manuelle d'abord, puis Pinnacle."""
    # 1) Chercher une ligne manuelle
    manual = get_manual_line(home_team, away_team)
    if manual:
        return manual

    # 2) Chercher dans les lignes Pinnacle
    home_lower = home_team.lower()
    away_lower = away_team.lower()
    best_match = None
    best_score = 0

    for line in pinnacle_lines:
        pin_home = line["home"].lower()
        pin_away = line["away"].lower()
        score = 0
        for word in home_lower.split():
            if len(word) > 2 and word in pin_home:
                score += 1
        for word in away_lower.split():
            if len(word) > 2 and word in pin_away:
                score += 1
        if score > best_score:
            best_score = score
            best_match = line

    if best_match and best_score >= 1:
        return PinnacleLine(
            total=best_match["total"],
            over_odds=best_match["over_odds"],
            under_odds=best_match["under_odds"],
            home_team=best_match["home"],
            away_team=best_match["away"],
            source="pinnacle",
        )
    return None
