"""Scraping des stats mi-temps Sofascore via leur API REST (httpx)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import httpx

from config import SOFASCORE_API


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.sofascore.com/",
}


@dataclass
class HalftimeStats:
    """Stats d'un match en live."""
    event_id: int
    home_team: str
    away_team: str
    home_score: int = 0
    away_score: int = 0
    minutes_played: int = 0
    period: int = 0           # 1 = Q1, 2 = Q2 (mi-temps), etc.
    # Pourcentages de tirs (FG%)
    home_fg_pct: float = 0.0
    away_fg_pct: float = 0.0
    # Fautes
    home_fouls: int = 0
    away_fouls: int = 0
    # Rebonds offensifs
    home_off_reb: int = 0
    away_off_reb: int = 0


async def get_live_basketball_events() -> list[dict]:
    """Récupère la liste des matchs de basket en live via l'API Sofascore."""
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        resp = await client.get(f"{SOFASCORE_API}/sport/basketball/events/live")
        resp.raise_for_status()
        data = resp.json()

    events = data.get("events", [])
    return [
        {
            "id": ev["id"],
            "home": ev["homeTeam"]["name"],
            "away": ev["awayTeam"]["name"],
            "status": ev.get("status", {}),
            "homeScore": ev.get("homeScore", {}),
            "awayScore": ev.get("awayScore", {}),
        }
        for ev in events
        if ev.get("tournament", {}).get("category", {}).get("sport", {}).get("slug") == "basketball"
    ]


async def get_halftime_stats(event_id: int) -> Optional[HalftimeStats]:
    """Récupère les statistiques détaillées d'un match live."""
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        # Infos de base du match
        resp_event = await client.get(f"{SOFASCORE_API}/event/{event_id}")
        resp_event.raise_for_status()
        ev = resp_event.json().get("event", {})

        home_team = ev.get("homeTeam", {}).get("name", "?")
        away_team = ev.get("awayTeam", {}).get("name", "?")
        status = ev.get("status", {})
        period = status.get("period", 0)

        # Temps joué — peut être dans différents champs
        minutes = 0
        if "time" in ev:
            time_info = ev["time"]
            played_raw = time_info.get("played", 0) if isinstance(time_info, dict) else 0
            # Sofascore renvoie parfois en secondes (>200) ou en minutes
            minutes = played_raw // 60 if played_raw > 200 else played_raw
        # Fallback : estimer via le quart-temps (12 min/QT en NBA)
        if minutes == 0 and period > 0:
            minutes = min(period, 4) * 12

        home_score_data = ev.get("homeScore", {})
        away_score_data = ev.get("awayScore", {})
        home_score = home_score_data.get("current", 0)
        away_score = away_score_data.get("current", 0)

        # Statistiques détaillées
        try:
            resp_stats = await client.get(f"{SOFASCORE_API}/event/{event_id}/statistics")
            resp_stats.raise_for_status()
            stats_data = resp_stats.json()
        except httpx.HTTPStatusError:
            stats_data = {}

    ht_stats = HalftimeStats(
        event_id=event_id,
        home_team=home_team,
        away_team=away_team,
        home_score=home_score,
        away_score=away_score,
        minutes_played=minutes,
        period=period,
    )

    # Parser les statistiques
    all_stats = stats_data.get("statistics", [])
    for group in all_stats:
        for item in group.get("groups", []):
            for stat in item.get("statisticsItems", []):
                key = stat.get("name", "").lower()
                home_val = stat.get("home", "")
                away_val = stat.get("away", "")

                if "field goal" in key and "%" in str(home_val):
                    ht_stats.home_fg_pct = _parse_pct(home_val)
                    ht_stats.away_fg_pct = _parse_pct(away_val)
                elif "fouls" in key or "fautes" in key:
                    ht_stats.home_fouls = _parse_int(home_val)
                    ht_stats.away_fouls = _parse_int(away_val)
                elif "offensive rebound" in key:
                    ht_stats.home_off_reb = _parse_int(home_val)
                    ht_stats.away_off_reb = _parse_int(away_val)

    return ht_stats


def _parse_pct(val) -> float:
    """Extrait un pourcentage depuis une string comme '45.2%'."""
    if isinstance(val, (int, float)):
        return float(val)
    m = re.search(r"([\d.]+)", str(val))
    return float(m.group(1)) if m else 0.0


def _parse_int(val) -> int:
    """Extrait un entier depuis une valeur."""
    if isinstance(val, int):
        return val
    m = re.search(r"(\d+)", str(val))
    return int(m.group(1)) if m else 0
