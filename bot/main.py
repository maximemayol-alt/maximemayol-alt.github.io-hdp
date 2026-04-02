"""Boucle principale — scan toutes les 2 minutes, détecte mi-temps, envoie verdicts."""

import asyncio
import logging
import sys

from config import SCAN_INTERVAL, TELEGRAM_BOT_TOKEN, ODDS_API_KEY
from sofascore import get_halftime_events, get_match_stats
from odds import fetch_live_ou_lines, find_line_for_match
from analyzer import analyze_with_line, analyze_pace_only
from telegram_bot import send_verdict, send_status

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# Matchs déjà signalés (évite les doublons si le match reste en "HT")
_signaled: set[int] = set()


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

    # 2) Récupérer les lignes O/U (si clé API dispo)
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

        # Chercher la ligne O/U
        line = find_line_for_match(ou_lines, stats.home_team, stats.away_team)

        if line:
            # Mode complet — avec GAP et EV
            verdict = analyze_with_line(stats, line)
            log.info(f"[COMPLET] {match_name}: {verdict.signal} (GAP={verdict.gap:+.1f}, EV={verdict.ev:+.1%})")
        else:
            # Mode pace-only — signal directionnel
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
        log.warning("ODDS_API_KEY manquante — mode pace-only pour tous les matchs.")

    log.info("Bot O/U Basketball démarré — scan toutes les %d secondes.", SCAN_INTERVAL)
    await send_status(
        "🤖 <b>Bot O/U Basketball démarré</b>\n"
        f"Scan toutes les {SCAN_INTERVAL}s — ligues cibles activées."
    )

    while True:
        try:
            await scan_once()
        except Exception as e:
            log.error(f"Erreur scan : {e}", exc_info=True)
        await asyncio.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
