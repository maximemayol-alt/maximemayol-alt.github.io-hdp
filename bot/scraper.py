"""Scraping des stats mi-temps Sofascore via Playwright."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Optional

from playwright.async_api import async_playwright, Page

from config import SOFASCORE_BASE, SOFASCORE_API


@dataclass
class HalftimeStats:
    """Stats d'un match à la mi-temps."""
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
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        # Appel API Sofascore pour les matchs live de basket
        resp = await page.request.get(
            f"{SOFASCORE_API}/sport/basketball/events/live"
        )
        data = await resp.json()
        await browser.close()

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
    """Scrape les statistiques détaillées d'un match live."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        # Récupérer les infos de base du match
        resp_event = await page.request.get(
            f"{SOFASCORE_API}/event/{event_id}"
        )
        event_data = await resp_event.json()
        ev = event_data.get("event", {})

        home_team = ev.get("homeTeam", {}).get("name", "?")
        away_team = ev.get("awayTeam", {}).get("name", "?")
        status = ev.get("status", {})
        period = status.get("period", 0)
        time_info = status.get("clock", {})
        minutes = time_info.get("played", 0) if isinstance(time_info, dict) else 0

        home_score_data = ev.get("homeScore", {})
        away_score_data = ev.get("awayScore", {})
        home_score = home_score_data.get("current", 0)
        away_score = away_score_data.get("current", 0)

        # Récupérer les statistiques détaillées
        resp_stats = await page.request.get(
            f"{SOFASCORE_API}/event/{event_id}/statistics"
        )
        stats_data = await resp_stats.json()
        await browser.close()

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
