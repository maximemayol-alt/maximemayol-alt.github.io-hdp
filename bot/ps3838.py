"""Scraping des cotes O/U sur PS3838 (ps898989.com) via Playwright.

Ce scraper nécessite un vrai navigateur (Playwright + Chromium).
Il ne fonctionne PAS depuis un serveur — uniquement en local avec
une IP résidentielle (Cloudflare bloque les datacenter IPs).

Usage :
    from ps3838 import fetch_ps3838_lines
    lines = await fetch_ps3838_lines()
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Optional

from playwright.async_api import async_playwright, Page

log = logging.getLogger(__name__)

PS3838_URL = "https://ps898989.com/m/fr/asian/sp"

# Temps d'attente pour le chargement JS (SPA)
PAGE_LOAD_WAIT = 5


@dataclass
class PS3838Line:
    """Ligne O/U PS3838 pour un match."""
    home_team: str
    away_team: str
    total: float          # Ligne (ex: 165.5)
    over_odds: float      # Cote OVER décimale
    under_odds: float     # Cote UNDER décimale


async def fetch_ps3838_lines() -> list[PS3838Line]:
    """Lance Playwright, navigue vers PS3838 basket, extrait les lignes O/U.

    Retourne une liste vide si le scraping échoue.
    """
    lines: list[PS3838Line] = []

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
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

            log.info("Navigation vers PS3838...")
            await page.goto(PS3838_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(PAGE_LOAD_WAIT)

            # Cliquer sur Basketball si nécessaire (menu sports)
            try:
                basketball_btn = page.locator("text=Basketball").first
                if await basketball_btn.is_visible(timeout=3000):
                    await basketball_btn.click()
                    await asyncio.sleep(2)
            except Exception:
                pass  # Peut-être déjà sur la page basket

            # Extraire les lignes O/U depuis le DOM
            lines = await _extract_lines(page)
            log.info(f"{len(lines)} ligne(s) O/U extraites de PS3838.")

            await browser.close()

    except Exception as e:
        log.error(f"Erreur scraping PS3838 : {e}")

    return lines


async def _extract_lines(page: Page) -> list[PS3838Line]:
    """Extrait les lignes O/U depuis la page PS3838.

    PS3838 mobile affiche les matchs dans des blocs avec :
    - Noms d'équipes
    - Lignes spread/total
    - Cotes associées

    La structure varie selon les versions, on essaie plusieurs sélecteurs.
    """
    lines: list[PS3838Line] = []

    # ── Stratégie 1 : structure SPA moderne ────────────────────
    # PS3838 utilise des conteneurs de match avec des data-attributes
    events = await page.query_selector_all(
        "[class*='event-row'], [class*='match-row'], [class*='game-line'], "
        "[class*='event_'], [data-event-id], [class*='matchup']"
    )

    if events:
        lines = await _parse_event_rows(page, events)
        if lines:
            return lines

    # ── Stratégie 2 : extraction par tables ────────────────────
    # Certaines versions utilisent des tables HTML
    tables = await page.query_selector_all("table")
    for table in tables:
        table_lines = await _parse_table(table)
        lines.extend(table_lines)

    if lines:
        return lines

    # ── Stratégie 3 : extraction brute du texte visible ────────
    # Fallback : parser le texte de la page entière
    log.warning("Sélecteurs spécifiques non trouvés — fallback texte brut.")
    content = await page.inner_text("body")
    lines = _parse_raw_text(content)

    return lines


async def _parse_event_rows(page: Page, events) -> list[PS3838Line]:
    """Parse les blocs d'événements individuels."""
    lines = []

    for event in events:
        try:
            text = await event.inner_text()
            text_lines = [l.strip() for l in text.split("\n") if l.strip()]

            # Chercher des noms d'équipes (au moins 2 lignes de texte)
            teams = []
            ou_data = {"total": 0.0, "over": 0.0, "under": 0.0}

            for i, line in enumerate(text_lines):
                # Détecter les cotes (nombres décimaux entre 1.0 et 9.99)
                odds_matches = re.findall(r"\b(\d\.\d{2,3})\b", line)

                # Détecter les lignes O/U (nombre avec .5 typiquement)
                total_match = re.search(r"\b(\d{2,3}\.5)\b", line)

                if total_match:
                    ou_data["total"] = float(total_match.group(1))

                if odds_matches and ou_data["total"] > 0:
                    for odds_str in odds_matches:
                        odds_val = float(odds_str)
                        if 1.01 < odds_val < 5.0:
                            if ou_data["over"] == 0:
                                ou_data["over"] = odds_val
                            elif ou_data["under"] == 0:
                                ou_data["under"] = odds_val

                # Noms d'équipe : texte qui n'est pas un nombre
                if not re.match(r"^[\d.\s+\-o/u]+$", line, re.IGNORECASE):
                    if len(line) > 2 and not any(c in line for c in ["@", ":", "/"]):
                        teams.append(line)

            if (
                len(teams) >= 2
                and ou_data["total"] > 50
                and ou_data["over"] > 1
                and ou_data["under"] > 1
            ):
                lines.append(PS3838Line(
                    home_team=teams[0],
                    away_team=teams[1],
                    total=ou_data["total"],
                    over_odds=ou_data["over"],
                    under_odds=ou_data["under"],
                ))
        except Exception:
            continue

    return lines


async def _parse_table(table) -> list[PS3838Line]:
    """Parse une table HTML de cotes."""
    lines = []
    try:
        rows = await table.query_selector_all("tr")
        current_teams = []

        for row in rows:
            text = await row.inner_text()
            cells = [c.strip() for c in text.split("\t") if c.strip()]

            # Chercher les noms d'équipe et les cotes dans la même ligne
            teams_in_row = []
            odds_in_row = []
            total_in_row = None

            for cell in cells:
                # Total O/U
                total_m = re.search(r"(\d{2,3}\.5)", cell)
                if total_m:
                    total_in_row = float(total_m.group(1))

                # Cotes
                odds_m = re.findall(r"\b(\d\.\d{2,3})\b", cell)
                for o in odds_m:
                    val = float(o)
                    if 1.01 < val < 5.0:
                        odds_in_row.append(val)

                # Équipe
                if (
                    len(cell) > 2
                    and not re.match(r"^[\d.\s]+$", cell)
                    and not total_m
                ):
                    teams_in_row.append(cell)

            if teams_in_row:
                current_teams = teams_in_row

            if total_in_row and len(odds_in_row) >= 2 and len(current_teams) >= 2:
                lines.append(PS3838Line(
                    home_team=current_teams[0],
                    away_team=current_teams[-1],
                    total=total_in_row,
                    over_odds=odds_in_row[0],
                    under_odds=odds_in_row[1],
                ))
                current_teams = []

    except Exception:
        pass

    return lines


def _parse_raw_text(content: str) -> list[PS3838Line]:
    """Parse le texte brut de la page pour extraire les lignes O/U.

    Cherche des patterns comme :
        Equipe A
        Equipe B
        o 165.5  1.87
        u 165.5  1.93
    """
    lines_out = []
    text_lines = content.split("\n")
    text_lines = [l.strip() for l in text_lines if l.strip()]

    i = 0
    while i < len(text_lines) - 3:
        line = text_lines[i]

        # Chercher un pattern O/U : "o 165.5" ou "Over 165.5"
        ou_match = re.match(r"(?:o|over|O)\s+(\d{2,3}\.5)\s+(\d\.\d{2,3})", line, re.IGNORECASE)
        if ou_match:
            total = float(ou_match.group(1))
            over_odds = float(ou_match.group(2))

            # La ligne suivante devrait être Under
            if i + 1 < len(text_lines):
                under_match = re.match(
                    r"(?:u|under|U)\s+\d{2,3}\.5\s+(\d\.\d{2,3})",
                    text_lines[i + 1],
                    re.IGNORECASE,
                )
                if under_match:
                    under_odds = float(under_match.group(1))

                    # Remonter pour trouver les noms d'équipes
                    teams = []
                    for j in range(max(0, i - 5), i):
                        t = text_lines[j]
                        if (
                            len(t) > 2
                            and not re.match(r"^[\d.\s\-+]+$", t)
                            and not re.match(r"^[ou]", t, re.IGNORECASE)
                        ):
                            teams.append(t)

                    if len(teams) >= 2:
                        lines_out.append(PS3838Line(
                            home_team=teams[-2],
                            away_team=teams[-1],
                            total=total,
                            over_odds=over_odds,
                            under_odds=under_odds,
                        ))
        i += 1

    return lines_out


def find_ps3838_line(
    ps_lines: list[PS3838Line],
    home_team: str,
    away_team: str,
) -> Optional[PS3838Line]:
    """Trouve la ligne PS3838 correspondant au match Sofascore.
    Matching par mots communs dans les noms d'équipe."""
    home_lower = home_team.lower()
    away_lower = away_team.lower()

    best = None
    best_score = 0

    for line in ps_lines:
        ps_home = line.home_team.lower()
        ps_away = line.away_team.lower()
        score = 0

        for word in home_lower.split():
            if len(word) > 2 and word in ps_home:
                score += 2
        for word in away_lower.split():
            if len(word) > 2 and word in ps_away:
                score += 2
        # Cross-match
        for word in home_lower.split():
            if len(word) > 3 and (word in ps_home or word in ps_away):
                score += 1

        if score > best_score:
            best_score = score
            best = line

    return best if best and best_score >= 2 else None
