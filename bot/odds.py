"""Récupération des lignes O/U via The Odds API."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from config import ODDS_API_BASE, ODDS_API_KEY, ODDS_API_SPORTS

log = logging.getLogger(__name__)


@dataclass
class OULine:
    """Ligne Over/Under pour un match."""
    total: float          # Ligne (ex: 165.5)
    over_odds: float      # Cote OVER décimale
    under_odds: float     # Cote UNDER décimale
    home_ml: float = 0.0  # Cote ML domicile (0 = pas dispo)
    away_ml: float = 0.0  # Cote ML extérieur (0 = pas dispo)
    bookmaker: str = ""


async def fetch_live_ou_lines() -> dict[str, OULine]:
    """Récupère toutes les lignes O/U live depuis The Odds API.

    Retourne un dict : clé = "home_lower vs away_lower", valeur = OULine.
    Priorise Pinnacle, sinon prend le premier bookmaker disponible.
    """
    if not ODDS_API_KEY:
        log.warning("ODDS_API_KEY manquante — pas de cotes disponibles.")
        return {}

    all_lines: dict[str, OULine] = {}

    async with httpx.AsyncClient(timeout=15) as client:
        for sport_key in ODDS_API_SPORTS:
            try:
                resp = await client.get(
                    f"{ODDS_API_BASE}/sports/{sport_key}/odds",
                    params={
                        "apiKey": ODDS_API_KEY,
                        "regions": "eu",
                        "markets": "totals",
                        "oddsFormat": "decimal",
                    },
                )
                if resp.status_code == 404:
                    continue  # Sport pas actif
                resp.raise_for_status()
                events = resp.json()
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
                log.warning(f"Erreur Odds API pour {sport_key}: {e}")
                continue

            for event in events:
                home = event.get("home_team", "")
                away = event.get("away_team", "")
                if not home or not away:
                    continue

                match_key = f"{home.lower()} vs {away.lower()}"
                line = _extract_best_line(event)
                if line:
                    all_lines[match_key] = line

    log.info(f"{len(all_lines)} ligne(s) O/U récupérée(s) via The Odds API.")
    return all_lines


def _extract_best_line(event: dict) -> Optional[OULine]:
    """Extrait la meilleure ligne O/U — Pinnacle en priorité."""
    bookmakers = event.get("bookmakers", [])
    pinnacle_line = None
    first_line = None

    for bm in bookmakers:
        bm_name = bm.get("key", "")
        for market in bm.get("markets", []):
            if market.get("key") != "totals":
                continue

            outcomes = market.get("outcomes", [])
            over_data = next((o for o in outcomes if o.get("name") == "Over"), None)
            under_data = next((o for o in outcomes if o.get("name") == "Under"), None)

            if not over_data or not under_data:
                continue

            line = OULine(
                total=over_data.get("point", 0),
                over_odds=over_data.get("price", 0),
                under_odds=under_data.get("price", 0),
                bookmaker=bm_name,
            )

            if bm_name == "pinnacle":
                pinnacle_line = line
            elif first_line is None:
                first_line = line

    return pinnacle_line or first_line


def find_line_for_match(
    all_lines: dict[str, OULine],
    home_team: str,
    away_team: str,
) -> Optional[OULine]:
    """Trouve la ligne O/U correspondant au match Sofascore.
    Matching par mots communs dans les noms d'équipe."""
    home_lower = home_team.lower()
    away_lower = away_team.lower()

    # Match exact d'abord
    exact_key = f"{home_lower} vs {away_lower}"
    if exact_key in all_lines:
        return all_lines[exact_key]

    # Matching par mots communs
    best_match = None
    best_score = 0

    for key, line in all_lines.items():
        parts = key.split(" vs ")
        if len(parts) != 2:
            continue
        odds_home, odds_away = parts

        score = 0
        for word in home_lower.split():
            if len(word) > 2 and word in odds_home:
                score += 2
        for word in away_lower.split():
            if len(word) > 2 and word in odds_away:
                score += 2
        # Cross-match partiel
        for word in home_lower.split():
            if len(word) > 3 and word in key:
                score += 1

        if score > best_score:
            best_score = score
            best_match = line

    if best_match and best_score >= 2:
        return best_match
    return None
