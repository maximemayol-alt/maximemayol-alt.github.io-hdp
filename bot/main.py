"""Point d'entrée du bot — boucle de scan des matchs live."""

import asyncio
import logging
import sys

from config import SCAN_INTERVAL, TELEGRAM_BOT_TOKEN
from scraper import get_live_basketball_events, get_halftime_stats
from pinnacle import fetch_pinnacle_lines, find_matching_line
from calculator import analyze
from telegram_bot import send_verdict, send_status, poll_commands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# Garde les matchs déjà signalés pour ne pas spammer
_already_signaled: set[str] = set()


async def scan_once() -> None:
    """Un cycle de scan : matchs live → stats → lignes → verdicts."""
    log.info("Début du scan…")

    try:
        events = await get_live_basketball_events()
    except Exception as e:
        log.error(f"Erreur récupération matchs live : {e}")
        return

    if not events:
        log.info("Aucun match live détecté.")
        return

    log.info(f"{len(events)} match(s) live trouvé(s).")

    # Récupérer les lignes Pinnacle (retourne [] si géo-bloqué)
    try:
        pinnacle_lines = await fetch_pinnacle_lines()
    except Exception as e:
        log.error(f"Erreur récupération Pinnacle : {e}")
        pinnacle_lines = []

    for ev in events:
        event_id = ev["id"]
        match_key = f"{ev['home']} vs {ev['away']}"

        # Filtrer les matchs déjà signalés
        if match_key in _already_signaled:
            continue

        # Récupérer les stats détaillées
        try:
            stats = await get_halftime_stats(event_id)
        except Exception as e:
            log.warning(f"Stats indisponibles pour {match_key}: {e}")
            continue

        if not stats or stats.minutes_played < 5:
            continue  # Trop tôt pour analyser

        # Trouver la ligne correspondante (manuelle ou Pinnacle)
        line = find_matching_line(pinnacle_lines, stats.home_team, stats.away_team)
        if not line:
            log.info(f"Pas de ligne pour {match_key}")
            continue

        # Calculer le verdict
        verdict = analyze(stats, line)

        if "PASSER" not in verdict.signal:
            log.info(f"Signal détecté : {verdict.signal} pour {match_key}")
            await send_verdict(verdict)
            _already_signaled.add(match_key)
        else:
            log.info(f"PASSER pour {match_key} (GAP={verdict.gap:+.1f}, EV={verdict.ev:+.1%})")


async def main() -> None:
    """Boucle principale du bot."""
    if not TELEGRAM_BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN manquant ! Crée un fichier .env (voir .env.example)")
        sys.exit(1)

    log.info("Bot démarré — scan toutes les %d secondes.", SCAN_INTERVAL)
    await send_status("🤖 Bot O/U Basketball démarré.\nTape /help pour les commandes.")

    while True:
        # Traiter les commandes Telegram
        try:
            actions = await poll_commands()
        except Exception as e:
            log.warning(f"Erreur polling commandes : {e}")
            actions = []

        # Scan si intervalle atteint ou commande /scan
        try:
            await scan_once()
        except Exception as e:
            log.error(f"Erreur dans le scan : {e}", exc_info=True)

        await asyncio.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
