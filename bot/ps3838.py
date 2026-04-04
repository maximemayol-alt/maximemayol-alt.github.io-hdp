"""Scraping des cotes O/U sur PS3838 (ps898989.com) via Playwright.

Stratégie : intercepter les réponses JSON de l'API interne Pinnacle
que la SPA charge automatiquement. Plus fiable que parser le HTML.

Nécessite Playwright + Chromium. Ne fonctionne qu'avec une IP
résidentielle (Cloudflare bloque les IPs datacenter).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from playwright.async_api import async_playwright, Response

log = logging.getLogger(__name__)

PS3838_URL = "https://ps898989.com/m/fr/asian/sp"
PS3838_BASKETBALL_URL = "https://ps898989.com/m/fr/asian/sp/4"  # 4 = basketball


@dataclass
class PS3838Line:
    """Ligne O/U PS3838 pour un match."""
    home_team: str
    away_team: str
    total: float          # Ligne O/U (ex: 165.5)
    over_odds: float      # Cote OVER décimale
    under_odds: float     # Cote UNDER décimale
    home_ml: float = 0.0  # Cote ML domicile
    away_ml: float = 0.0  # Cote ML extérieur


# ── Données capturées via interception réseau ──────────────────
_captured_matchups: list[dict] = []
_captured_odds: list[dict] = []


async def _on_response(response: Response) -> None:
    """Callback : capture les réponses JSON de l'API Pinnacle interne."""
    url = response.url.lower()
    try:
        if response.status == 200 and "application/json" in (response.headers.get("content-type", "")):
            # Matchups (liste des matchs)
            if "matchups" in url and "sports" in url:
                data = await response.json()
                if isinstance(data, list):
                    _captured_matchups.extend(data)
                    log.info(f"PS3838: {len(data)} matchups capturés")
            # Odds / Markets (cotes)
            elif "markets" in url or "odds" in url or "straight" in url:
                data = await response.json()
                if isinstance(data, list):
                    _captured_odds.extend(data)
                    log.info(f"PS3838: {len(data)} lignes de cotes capturées")
    except Exception:
        pass


async def fetch_ps3838_lines() -> list[PS3838Line]:
    """Ouvre PS3838 basket via Playwright, intercepte les données JSON,
    et retourne les lignes O/U de tous les matchs live."""

    global _captured_matchups, _captured_odds
    _captured_matchups = []
    _captured_odds = []

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                    "Version/17.0 Mobile/15E148 Safari/604.1"
                ),
                viewport={"width": 390, "height": 844},
                locale="fr-FR",
            )

            page = await context.new_page()

            # Intercepter toutes les réponses réseau
            page.on("response", _on_response)

            # 1) Charger la page basket
            log.info("PS3838: chargement de la page basket...")
            await page.goto(PS3838_BASKETBALL_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            # 2) Cliquer sur "Live" si un onglet existe
            try:
                live_btn = page.locator("text=/live|en direct|en cours/i").first
                if await live_btn.is_visible(timeout=2000):
                    await live_btn.click()
                    await asyncio.sleep(2)
            except Exception:
                pass

            # 3) Scroller pour charger tous les matchs
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, 800)")
                await asyncio.sleep(1)

            # 4) Si l'API interception n'a rien donné, fallback HTML
            if not _captured_matchups and not _captured_odds:
                log.info("PS3838: pas de données API interceptées, fallback HTML...")
                lines = await _extract_from_html(page)
            else:
                lines = _parse_api_data()

            log.info(f"PS3838: {len(lines)} ligne(s) O/U extraites au total.")
            await browser.close()
            return lines

    except Exception as e:
        log.error(f"PS3838: erreur scraping — {e}")
        return []


def _parse_api_data() -> list[PS3838Line]:
    """Parse les données JSON capturées depuis l'API Pinnacle interne."""
    lines = []

    # Indexer les matchups par ID
    matchup_map: dict[int, dict] = {}
    for m in _captured_matchups:
        mid = m.get("id")
        if not mid:
            continue
        participants = m.get("participants", [])
        if len(participants) >= 2:
            home = next(
                (p.get("name", "") for p in participants if p.get("alignment") == "home"),
                participants[0].get("name", ""),
            )
            away = next(
                (p.get("name", "") for p in participants if p.get("alignment") == "away"),
                participants[1].get("name", ""),
            )
            matchup_map[mid] = {"home": home, "away": away}

    # Extraire les lignes O/U et ML depuis les cotes
    match_data: dict[int, dict] = {}

    for item in _captured_odds:
        matchup_id = item.get("matchupId")
        if matchup_id not in matchup_map:
            continue

        if matchup_id not in match_data:
            match_data[matchup_id] = {
                "total": 0, "over": 0, "under": 0,
                "home_ml": 0, "away_ml": 0,
            }

        for price in item.get("prices", []):
            ptype = price.get("type", "")
            designation = price.get("designation", "")
            points = price.get("points")
            odds = price.get("price", 0)
            dec_odds = _to_decimal(odds)

            if ptype == "total" and points:
                match_data[matchup_id]["total"] = float(points)
                if designation == "over":
                    match_data[matchup_id]["over"] = dec_odds
                elif designation == "under":
                    match_data[matchup_id]["under"] = dec_odds
            elif ptype == "moneyline":
                if designation == "home":
                    match_data[matchup_id]["home_ml"] = dec_odds
                elif designation == "away":
                    match_data[matchup_id]["away_ml"] = dec_odds

    # Construire les lignes
    for mid, data in match_data.items():
        if mid not in matchup_map:
            continue
        if data["total"] > 0 and data["over"] > 0 and data["under"] > 0:
            teams = matchup_map[mid]
            lines.append(PS3838Line(
                home_team=teams["home"],
                away_team=teams["away"],
                total=data["total"],
                over_odds=data["over"],
                under_odds=data["under"],
                home_ml=data["home_ml"],
                away_ml=data["away_ml"],
            ))

    return lines


async def _extract_from_html(page) -> list[PS3838Line]:
    """Fallback : extraire les données directement du HTML/texte visible."""
    lines = []

    try:
        content = await page.inner_text("body")
    except Exception:
        return lines

    text_lines = [l.strip() for l in content.split("\n") if l.strip()]

    i = 0
    while i < len(text_lines):
        line = text_lines[i]

        # Chercher un total O/U : nombre comme 165.5, 178.0, etc.
        total_m = re.search(r"\b(\d{2,3}(?:\.5|\.0))\b", line)
        if total_m:
            total = float(total_m.group(1))
            if 80 < total < 300:  # Plage réaliste basket
                # Chercher les cotes autour (±3 lignes)
                over_odds = 0.0
                under_odds = 0.0
                teams = []

                for j in range(max(0, i - 5), min(len(text_lines), i + 5)):
                    odds_found = re.findall(r"\b(\d\.\d{2,3})\b", text_lines[j])
                    for o in odds_found:
                        val = float(o)
                        if 1.01 < val < 5.0:
                            if over_odds == 0:
                                over_odds = val
                            elif under_odds == 0:
                                under_odds = val

                    # Noms d'équipe (texte non-numérique, > 3 chars)
                    t = text_lines[j]
                    if (
                        len(t) > 3
                        and not re.match(r"^[\d.\s+\-oOuU/]+$", t)
                        and not re.search(r"\d\.\d{2}", t)
                        and t.lower() not in ("over", "under", "total", "basketball")
                    ):
                        teams.append(t)

                if over_odds > 0 and under_odds > 0 and len(teams) >= 2:
                    lines.append(PS3838Line(
                        home_team=teams[0],
                        away_team=teams[1] if len(teams) > 1 else "",
                        total=total,
                        over_odds=over_odds,
                        under_odds=under_odds,
                    ))
        i += 1

    return lines


def _to_decimal(american: float) -> float:
    """Convertit cote américaine → décimale."""
    if american >= 100:
        return round(1 + american / 100, 3)
    elif american <= -100:
        return round(1 + 100 / abs(american), 3)
    return american if american > 1 else 2.0


def find_ps3838_line(
    ps_lines: list[PS3838Line],
    home_team: str,
    away_team: str,
) -> Optional[PS3838Line]:
    """Trouve la ligne PS3838 correspondant au match Sofascore.
    Matching par mots communs dans les noms d'équipe."""
    home_words = [w for w in home_team.lower().split() if len(w) > 2]
    away_words = [w for w in away_team.lower().split() if len(w) > 2]

    best = None
    best_score = 0

    for line in ps_lines:
        ps_home = line.home_team.lower()
        ps_away = line.away_team.lower()
        score = 0

        for w in home_words:
            if w in ps_home:
                score += 2
            elif w in ps_away:
                score += 1  # Cross-match partiel
        for w in away_words:
            if w in ps_away:
                score += 2
            elif w in ps_home:
                score += 1

        if score > best_score:
            best_score = score
            best = line

    return best if best and best_score >= 2 else None
