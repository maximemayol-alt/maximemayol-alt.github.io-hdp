"""Boucle principale — scan + réponses interactives Telegram.

Workflow :
  1. Détecte match HT → envoie alerte pace-only "Vérifie PS3838"
  2. L'utilisateur répond /line 183.5 1.869 1.854
  3. Bot calcule GAP + EV → envoie verdict final

Chaîne de cotes : PS3838 auto → Odds API → /line manuelle → pace-only
"""

import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from config import SCAN_INTERVAL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ODDS_API_KEY
from sofascore import get_halftime_events, get_match_stats, HalftimeData
from odds import fetch_live_ou_lines, find_line_for_match, OULine
from ps3838 import fetch_ps3838_lines, find_ps3838_line
from analyzer import analyze_with_line, analyze_pace_only, Verdict
from telegram_bot import send_verdict, send_status

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


# ── État global ────────────────────────────────────────────────

# Matchs en attente de ligne manuelle : event_id → HalftimeData
_pending: dict[int, HalftimeData] = {}

# Matchs déjà traités (verdict envoyé ou skip)
_done: set[int] = set()

# Shadow tracker : historique des verdicts pour /stats
_tracker: list[dict] = []

# PS3838 disponible ?
_ps3838_available = True

# Polling offset Telegram
_tg_offset = 0


# ── Shadow Tracker ─────────────────────────────────────────────

def _track(verdict: Verdict, source: str) -> None:
    """Enregistre un verdict pour le shadow tracker."""
    _tracker.append({
        "match": verdict.match,
        "league": verdict.league,
        "signal": verdict.signal,
        "pace": verdict.pace,
        "line": verdict.line,
        "gap": verdict.gap,
        "ev": verdict.ev,
        "source": source,
        "ts": int(time.time()),
    })


# ── Scan ───────────────────────────────────────────────────────

async def _get_ps3838_lines() -> list:
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
        return []


async def scan_once() -> None:
    """Un cycle de scan."""
    log.info("── Scan en cours… ──")

    try:
        ht_events = await get_halftime_events()
    except Exception as e:
        log.error(f"Erreur Sofascore : {e}")
        return

    if not ht_events:
        log.info("Aucun match mi-temps dans les ligues cibles.")
        return

    log.info(f"{len(ht_events)} match(s) mi-temps détecté(s).")

    # Récupérer les cotes automatiques
    ps_lines = await _get_ps3838_lines()
    ou_lines = {}
    if ODDS_API_KEY:
        try:
            ou_lines = await fetch_live_ou_lines()
        except Exception as e:
            log.error(f"Erreur Odds API : {e}")

    for ev in ht_events:
        event_id = ev["id"]
        match_name = f"{ev['home']} vs {ev['away']}"

        if event_id in _done or event_id in _pending:
            continue

        stats = await get_match_stats(event_id, ev)
        if not stats:
            continue

        # Chercher une cote auto
        line = None
        source = ""

        ps_match = find_ps3838_line(ps_lines, stats.home_team, stats.away_team)
        if ps_match:
            line = OULine(
                total=ps_match.total,
                over_odds=ps_match.over_odds,
                under_odds=ps_match.under_odds,
                bookmaker="ps3838",
                home_ml=ps_match.home_ml,
                away_ml=ps_match.away_ml,
            )
            source = "PS3838"

        if not line:
            api_line = find_line_for_match(ou_lines, stats.home_team, stats.away_team)
            if api_line:
                line = api_line
                source = f"Odds API ({api_line.bookmaker})"

        if line:
            # Cote trouvée → verdict complet direct
            verdict = analyze_with_line(stats, line)
            log.info(f"[{source}] {match_name}: {verdict.signal} (GAP={verdict.gap:+.1f})")
            await send_verdict(verdict)
            _track(verdict, source)
            _done.add(event_id)
        else:
            # Pas de cote → alerte pace-only + en attente de /line
            _pending[event_id] = stats
            pace_verdict = analyze_pace_only(stats)
            total_ht = stats.home_score + stats.away_score
            pace = total_ht / 20 * 40

            await send_status(
                f"🏀 <b>{match_name}</b> — {stats.league}\n"
                f"📊 Score MT : {stats.home_score}-{stats.away_score}\n"
                f"⚡️ Pace projeté : {pace:.0f}\n"
                f"🎯 Shooting : {stats.home_fg_pct:.0f}% / {stats.away_fg_pct:.0f}%\n"
                f"⚠️ Fautes : {stats.total_fouls} | Reb Off : {stats.total_off_reb}\n"
                f"📌 Vérifie la ligne sur PS3838\n"
                f"→ Signal directionnel : <b>{pace_verdict.signal}</b>\n"
                f"\n"
                f"💬 Réponds avec :\n"
                f"<code>/line {pace:.0f}.5 1.87 1.93</code>\n"
                f"ou <code>/skip</code> pour ignorer"
            )
            log.info(f"[ATTENTE] {match_name} — en attente de /line (pace={pace:.0f})")


# ── Commandes Telegram ─────────────────────────────────────────

async def poll_commands() -> None:
    """Récupère et traite les commandes Telegram."""
    global _tg_offset

    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
                params={"offset": _tg_offset, "timeout": 1},
            )
            data = resp.json()
    except Exception:
        return

    for update in data.get("result", []):
        _tg_offset = update["update_id"] + 1
        msg = update.get("message", {})
        text = msg.get("text", "").strip()
        chat_id = msg.get("chat", {}).get("id")

        if chat_id != TELEGRAM_CHAT_ID:
            continue

        cmd = text.lower()

        if cmd.startswith("/line "):
            await _handle_line(text)
        elif cmd == "/skip":
            await _handle_skip()
        elif cmd in ("/status", "/ping"):
            await _handle_status()
        elif cmd == "/stats":
            await _handle_stats()
        elif cmd in ("/start", "/help"):
            await _handle_help()


async def _handle_line(text: str) -> None:
    """Traite /line [total] [over_odds] [under_odds] [home_ml?] [away_ml?]"""
    parts = text.split()
    if len(parts) < 4:
        await send_status(
            "⚠️ Format : <code>/line 183.5 1.87 1.93</code>\n"
            "Optionnel : <code>/line 183.5 1.87 1.93 1.25 4.50</code> (avec ML)"
        )
        return

    try:
        total = float(parts[1])
        over_odds = float(parts[2])
        under_odds = float(parts[3])
        home_ml = float(parts[4]) if len(parts) > 4 else 0.0
        away_ml = float(parts[5]) if len(parts) > 5 else 0.0
    except ValueError:
        await send_status("⚠️ Nombres invalides. Ex: <code>/line 183.5 1.87 1.93</code>")
        return

    if not _pending:
        await send_status("📭 Aucun match en attente de ligne.")
        return

    # Prendre le match le plus récent en attente
    event_id, stats = list(_pending.items())[-1]
    match_name = f"{stats.home_team} vs {stats.away_team}"

    line = OULine(
        total=total,
        over_odds=over_odds,
        under_odds=under_odds,
        bookmaker="manual",
        home_ml=home_ml,
        away_ml=away_ml,
    )

    verdict = analyze_with_line(stats, line)
    await send_verdict(verdict)
    _track(verdict, "manual")

    del _pending[event_id]
    _done.add(event_id)
    log.info(f"[MANUAL] {match_name}: {verdict.signal} (GAP={verdict.gap:+.1f})")


async def _handle_skip() -> None:
    """Ignore le dernier match en attente."""
    if not _pending:
        await send_status("📭 Aucun match en attente.")
        return

    event_id, stats = list(_pending.items())[-1]
    match_name = f"{stats.home_team} vs {stats.away_team}"
    del _pending[event_id]
    _done.add(event_id)
    await send_status(f"⏭️ {match_name} — ignoré.")
    log.info(f"[SKIP] {match_name}")


async def _handle_status() -> None:
    """Affiche l'état du bot."""
    pending_count = len(_pending)
    done_count = len(_done)

    msg = f"🟢 <b>Bot actif</b>\n"
    msg += f"Matchs traités : {done_count}\n"

    if _pending:
        msg += f"\n⏳ <b>En attente de /line ({pending_count}) :</b>\n"
        for eid, stats in _pending.items():
            total_ht = stats.home_score + stats.away_score
            pace = total_ht / 20 * 40
            msg += (
                f"• {stats.home_team} vs {stats.away_team}\n"
                f"  {stats.home_score}-{stats.away_score} | Pace {pace:.0f} | {stats.league}\n"
            )
    else:
        msg += "\n📭 Aucun match en attente."

    await send_status(msg)


async def _handle_stats() -> None:
    """Affiche le shadow tracker."""
    if not _tracker:
        await send_status("📊 Aucun verdict enregistré cette session.")
        return

    total = len(_tracker)
    overs = sum(1 for t in _tracker if "OVER" in t["signal"])
    unders = sum(1 for t in _tracker if "UNDER" in t["signal"])
    passes = sum(1 for t in _tracker if "PASSER" in t["signal"])

    # Sources
    sources = {}
    for t in _tracker:
        s = t["source"]
        sources[s] = sources.get(s, 0) + 1

    # EV moyen (hors PASSER)
    evs = [t["ev"] for t in _tracker if t["ev"] != 0]
    avg_ev = sum(evs) / len(evs) if evs else 0

    msg = (
        f"📊 <b>Shadow Tracker</b>\n"
        f"{'━' * 24}\n"
        f"Verdicts : {total}\n"
        f"  OVER : {overs} | UNDER : {unders} | PASSER : {passes}\n"
        f"EV moyen : {avg_ev:+.1%}\n"
        f"\nSources :\n"
    )
    for s, c in sources.items():
        msg += f"  • {s} : {c}\n"

    # Derniers 5 verdicts
    msg += f"\n<b>Derniers verdicts :</b>\n"
    for t in _tracker[-5:]:
        gap_str = f"GAP {t['gap']:+.1f}" if t["gap"] else f"Pace {t['pace']}"
        msg += f"• {t['match'][:30]} → {t['signal']} ({gap_str})\n"

    await send_status(msg)


async def _handle_help() -> None:
    await send_status(
        "🤖 <b>Bot O/U Basketball</b>\n"
        "{'━' * 24}\n"
        "\n"
        "<b>Automatique :</b>\n"
        "Le bot scanne les matchs à la mi-temps\n"
        "et envoie les alertes automatiquement.\n"
        "\n"
        "<b>Commandes :</b>\n"
        "/line 183.5 1.87 1.93 — entrer la ligne PS3838\n"
        "/line 183.5 1.87 1.93 1.25 4.50 — avec ML\n"
        "/skip — ignorer le match en attente\n"
        "/status — matchs en cours / en attente\n"
        "/stats — shadow tracker (historique)\n"
        "/ping — vérifier que le bot tourne"
    )


# ── Boucle principale ─────────────────────────────────────────

async def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN manquant dans .env")
        sys.exit(1)
    if not ODDS_API_KEY:
        log.warning("ODDS_API_KEY manquante — fallback PS3838 + pace-only.")

    log.info("Bot O/U Basketball démarré — scan toutes les %d secondes.", SCAN_INTERVAL)
    await send_status(
        "🤖 <b>Bot O/U Basketball démarré</b>\n"
        f"Scan toutes les {SCAN_INTERVAL}s\n"
        "Sources : PS3838 → Odds API → /line manuelle\n"
        "\n"
        "Tape /help pour les commandes"
    )

    # Vider les anciens messages Telegram au démarrage
    await poll_commands()

    while True:
        await poll_commands()

        try:
            await scan_once()
        except Exception as e:
            log.error(f"Erreur scan : {e}", exc_info=True)

        await asyncio.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
