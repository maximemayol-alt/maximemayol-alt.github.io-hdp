"""Récupération des lignes O/U Pinnacle (PS3838) via leur API publique."""

from __future__ import annotations

import httpx
from typing import Optional
from dataclasses import dataclass


@dataclass
class PinnacleLine:
    """Ligne O/U Pinnacle pour un match."""
    total: float          # Ligne (ex: 210.5)
    over_odds: float      # Cote OVER décimale
    under_odds: float     # Cote UNDER décimale
    home_team: str = ""
    away_team: str = ""


# API publique Pinnacle (pas besoin de clé)
PINNACLE_ODDS_URL = "https://guest.api.arcadia.pinnacle.com/0.1/sports/4/markets/straight"
PINNACLE_MATCHUPS_URL = "https://guest.api.arcadia.pinnacle.com/0.1/sports/4/matchups"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.pinnacle.com/",
    "X-Api-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
}


async def fetch_pinnacle_lines() -> list[dict]:
    """Récupère toutes les lignes O/U basket live depuis Pinnacle."""
    async with httpx.AsyncClient(timeout=15) as client:
        # 1) Récupérer les matchups (matchs)
        resp_matchups = await client.get(
            PINNACLE_MATCHUPS_URL,
            headers=HEADERS,
            params={"isLive": "true"},
        )
        resp_matchups.raise_for_status()
        matchups = resp_matchups.json()

        # 2) Récupérer les odds
        resp_odds = await client.get(
            PINNACLE_ODDS_URL,
            headers=HEADERS,
            params={"isLive": "true"},
        )
        resp_odds.raise_for_status()
        odds_data = resp_odds.json()

    # Indexer les matchups par ID
    matchup_map = {}
    for m in matchups:
        mid = m.get("id")
        participants = m.get("participants", [])
        if len(participants) >= 2:
            home = next((p["name"] for p in participants if p.get("alignment") == "home"), participants[0]["name"])
            away = next((p["name"] for p in participants if p.get("alignment") == "away"), participants[1]["name"])
            matchup_map[mid] = {"home": home, "away": away}

    # Extraire les lignes totals (O/U)
    lines = []
    for item in odds_data:
        matchup_id = item.get("matchupId")
        if matchup_id not in matchup_map:
            continue

        for price in item.get("prices", []):
            if price.get("type") != "total":
                continue
            points = price.get("points")
            designation = price.get("designation")  # "over" ou "under"
            dec_odds = price.get("price", 0)

            if points is None:
                continue

            # Chercher ou créer l'entrée pour ce match + ligne
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
    """Convertit une cote américaine en décimale."""
    if american >= 100:
        return 1 + american / 100
    elif american <= -100:
        return 1 + 100 / abs(american)
    else:
        # Déjà en décimale ou format spécial Pinnacle
        return american if american > 1 else 2.0


def find_matching_line(
    pinnacle_lines: list[dict],
    home_team: str,
    away_team: str,
) -> Optional[PinnacleLine]:
    """Trouve la ligne Pinnacle correspondant au match Sofascore."""
    home_lower = home_team.lower()
    away_lower = away_team.lower()

    best_match = None
    best_score = 0

    for line in pinnacle_lines:
        pin_home = line["home"].lower()
        pin_away = line["away"].lower()

        score = 0
        # Matching par mots communs
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
        )
    return None
