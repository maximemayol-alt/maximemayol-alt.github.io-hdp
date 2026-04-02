"""Boucle principale — scan toutes les 2 minutes, détecte mi-temps, envoie verdicts.

Chaîne de cotes (priorité) :
  1. PS3838 (Playwright) — couvre toutes les ligues exotiques
  2. The Odds API — fallback pour Euroleague/NBL/NBA
  3. Pace-only — si aucune cote trouvée
"""

import asyncio
import logging
import sys

from config import SCAN_INTERVAL, TELEGRAM_BOT_TOKEN, ODDS_API_KEY
from sofascore import get_halftime_events, get_match_stats
from odds import fetch_live_ou_lines, find_line_for_match, OULine
from ps3838 import fetch_ps3838_lines, find_ps3838_line
from analyzer import analyze_with_line, analyze_pace_only
from telegram_bot import send_verdict, send_status

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# Matchs déjà signalés (évite les doublons si le match reste en "HT")
_signaled: set[int] = set()

# Flag : PS3838 disponible ? (désactivé si Playwright échoue)
_ps3838_available = True


async def _get_ps3838_lines() -> list:
    """Tente de récupérer les lignes PS3838. Désactive si échec répété."""
    global _ps3838_available
    if not _ps3838_available:
        return []
    try:
        lines = await fetch_ps3838_lines()
        if lines:
            log.info(f"{len(lines)} ligne(s) PS3838 récupérée(s).")
        return lines
    except Exception as e:
        log.warning(f"PS3838 indisponible : {e}")
        _ps3838_available = False
        log.info("PS3838 désactivé — fallback sur The Odds API + pace-only.")
        return []


async def scan_once() -> None:
    """Un cycle : matchs mi-temps → stats → cotes → verdicts."""
    log.info("── Scan en cours… ──")

    # 1) Matchs à la mi-temps dans les ligues cibles
    try:
        ht_events = await get_halftime_events()
    except Exception as e:
        log.error(f"Erreur Sofascore : {e}")
        return

    if not ht_events:
        log.info("Aucun match mi-temps dans les ligues cibles.")
        return

    log.info(f"{len(ht_events)} match(s) mi-temps détecté(s).")

    # 2) Récupérer les cotes — PS3838 d'abord, puis The Odds API
    ps_lines = await _get_ps3838_lines()

    ou_lines = {}
    if ODDS_API_KEY:
        try:
            ou_lines = await fetch_live_ou_lines()
        except Exception as e:
            log.error(f"Erreur Odds API : {e}")

    # 3) Analyser chaque match
    for ev in ht_events:
        event_id = ev["id"]
        match_name = f"{ev['home']} vs {ev['away']}"

        if event_id in _signaled:
            continue

        # Stats détaillées
        stats = await get_match_stats(event_id, ev)
        if not stats:
            continue

        # Chercher la ligne O/U — PS3838 prioritaire
        line = None
        source = ""

        # Source 1 : PS3838
        ps_match = find_ps3838_line(ps_lines, stats.home_team, stats.away_team)
        if ps_match:
            line = OULine(
                total=ps_match.total,
                over_odds=ps_match.over_odds,
                under_odds=ps_match.under_odds,
                bookmaker="ps3838",
            )
            source = "PS3838"

        # Source 2 : The Odds API
        if not line:
            line = find_line_for_match(ou_lines, stats.home_team, stats.away_team)
            if line:
                source = f"Odds API ({line.bookmaker})"

        # Verdict
        if line:
            verdict = analyze_with_line(stats, line)
            log.info(f"[{source}] {match_name}: {verdict.signal} (GAP={verdict.gap:+.1f}, EV={verdict.ev:+.1%})")
        else:
            verdict = analyze_pace_only(stats)
            log.info(f"[PACE] {match_name}: {verdict.signal} (Pace={verdict.pace})")

        await send_verdict(verdict)
        _signaled.add(event_id)


async def main() -> None:
    """Point d'entrée."""
    if not TELEGRAM_BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN manquant dans .env")
        sys.exit(1)
    if not ODDS_API_KEY:
        log.warning("ODDS_API_KEY manquante — fallback PS3838 + pace-only.")

    log.info("Bot O/U Basketball démarré — scan toutes les %d secondes.", SCAN_INTERVAL)
    await send_status(
        "🤖 <b>Bot O/U Basketball démarré</b>\n"
        f"Scan toutes les {SCAN_INTERVAL}s\n"
        f"Sources : PS3838 → Odds API → Pace-only"
    )

    while True:
        try:
            await scan_once()
        except Exception as e:
            log.error(f"Erreur scan : {e}", exc_info=True)
        await asyncio.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
