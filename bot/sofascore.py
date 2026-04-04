"""Scraping Sofascore — matchs live mi-temps + stats détaillées."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

import httpx

from config import SOFASCORE_API, TARGET_LEAGUES

log = logging.getLogger(__name__)

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
class HalftimeData:
    """Stats d'un match à la mi-temps."""
    event_id: int
    home_team: str
    away_team: str
    league: str              # Label affiché (ex: "Turquie BSL")
    home_score: int = 0
    away_score: int = 0
    # FG% (pourcentage paniers)
    home_fg_pct: float = 0.0
    away_fg_pct: float = 0.0
    # Fautes combinées
    total_fouls: int = 0
    # Rebonds offensifs combinés
    total_off_reb: int = 0


def _match_league(event: dict) -> Optional[str]:
    """Vérifie si le match appartient à une ligue cible.
    Retourne le label affiché ou None."""
    tournament = event.get("tournament", {})
    category = tournament.get("category", {})

    # Construire une chaîne de recherche avec tous les noms disponibles
    search_parts = [
        tournament.get("name", ""),
        tournament.get("slug", ""),
        category.get("name", ""),
        category.get("slug", ""),
        event.get("season", {}).get("name", ""),
    ]
    search_str = " ".join(search_parts).lower()

    for key, label in TARGET_LEAGUES.items():
        if key in search_str:
            return label
    return None


async def get_halftime_events() -> list[dict]:
    """Récupère les matchs de basket live qui sont à la mi-temps
    dans les ligues cibles."""
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        resp = await client.get(f"{SOFASCORE_API}/sport/basketball/events/live")
        resp.raise_for_status()
        data = resp.json()

    results = []
    for ev in data.get("events", []):
        # Vérifier que c'est bien du basket
        sport = (
            ev.get("tournament", {})
            .get("category", {})
            .get("sport", {})
            .get("slug", "")
        )
        if sport != "basketball":
            continue

        # Vérifier la ligue
        league = _match_league(ev)
        if not league:
            continue

        # Détecter la mi-temps
        # Sofascore codes basket :
        #   13=Q1, 14=Q2, 15=Q3, 16=Q4, 31=Halftime
        # Le code 31 est le seul fiable pour la vraie mi-temps
        status = ev.get("status", {})
        status_code = status.get("code", 0)
        status_desc = status.get("description", "").lower()

        is_halftime = (
            status_code == 31
            or status_desc == "halftime"
            or status_desc == "half time"
            or status_desc == "ht"
        )

        if not is_halftime:
            continue

        home_score = ev.get("homeScore", {}).get("current", 0)
        away_score = ev.get("awayScore", {}).get("current", 0)

        log.info(
            f"HT détecté : {ev['homeTeam']['name']} vs {ev['awayTeam']['name']} "
            f"({home_score}-{away_score}) — code={status_code} desc=\"{status_desc}\" "
            f"league={league}"
        )

        results.append({
            "id": ev["id"],
            "home": ev["homeTeam"]["name"],
            "away": ev["awayTeam"]["name"],
            "league": league,
            "home_score": home_score,
            "away_score": away_score,
        })

    return results


async def get_match_stats(event_id: int, match_info: dict) -> Optional[HalftimeData]:
    """Récupère les stats détaillées d'un match à la mi-temps."""
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        try:
            resp = await client.get(
                f"{SOFASCORE_API}/event/{event_id}/statistics"
            )
            resp.raise_for_status()
            stats_data = resp.json()
        except httpx.HTTPStatusError:
            log.warning(f"Stats indisponibles pour event {event_id}")
            stats_data = {}

    ht = HalftimeData(
        event_id=event_id,
        home_team=match_info["home"],
        away_team=match_info["away"],
        league=match_info["league"],
        home_score=match_info["home_score"],
        away_score=match_info["away_score"],
    )

    # Parser les statistiques Sofascore
    for group in stats_data.get("statistics", []):
        for section in group.get("groups", []):
            for item in section.get("statisticsItems", []):
                key = item.get("name", "").lower()
                home_val = item.get("home", "")
                away_val = item.get("away", "")

                if key == "field goals":
                    # Format: "19/35 (54%)" → extraire le % entre parenthèses
                    ht.home_fg_pct = _parse_pct(home_val)
                    ht.away_fg_pct = _parse_pct(away_val)
                elif key in ("fouls", "personal fouls", "fautes"):
                    ht.total_fouls = _parse_int(home_val) + _parse_int(away_val)
                elif key in ("offensive rebounds", "offensive rebound"):
                    ht.total_off_reb = _parse_int(home_val) + _parse_int(away_val)

    return ht


def _parse_pct(val) -> float:
    """Extrait le % depuis '19/35 (54%)' → 54.0, ou '54.2%' → 54.2."""
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val)
    # Chercher le % entre parenthèses : "19/35 (54%)"
    m = re.search(r"\((\d+)%?\)", s)
    if m:
        return float(m.group(1))
    # Fallback : chercher un nombre suivi de %
    m = re.search(r"([\d.]+)%", s)
    if m:
        return float(m.group(1))
    return 0.0


def _parse_int(val) -> int:
    if isinstance(val, int):
        return val
    m = re.search(r"(\d+)", str(val))
    return int(m.group(1)) if m else 0
