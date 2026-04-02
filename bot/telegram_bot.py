"""Envoi des verdicts + polling des commandes Telegram."""

from __future__ import annotations

import logging
import httpx
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from calculator import Verdict
from pinnacle import set_manual_line, clear_manual_lines

log = logging.getLogger(__name__)
API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Offset pour le polling des messages
_update_offset = 0


async def _send_message(text: str, parse_mode: str = "HTML") -> None:
    """Envoie un message via l'API Telegram."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{API_URL}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": parse_mode,
            },
        )
        resp.raise_for_status()


async def send_verdict(verdict: Verdict) -> None:
    """Envoie un message Telegram formaté avec le verdict."""
    message = (
        f"🏀 <b>{verdict.match}</b>\n"
        f"{'━' * 28}\n"
        f"\n"
        f"🚦 Signal : <b>{verdict.signal}</b>\n"
        f"\n"
        f"{verdict.details}\n"
        f"{'━' * 28}\n"
    )
    await _send_message(message)


async def send_status(text: str) -> None:
    """Envoie un message de statut simple."""
    await _send_message(text)


async def send_no_games() -> None:
    """Notifie qu'aucun match live n'a été trouvé."""
    await send_status("🏀 Aucun match de basket live détecté. Prochain scan bientôt…")


# ── Commandes Telegram ─────────────────────────────────────────

HELP_TEXT = """🤖 <b>Commandes disponibles :</b>

/scan — Forcer un scan immédiat
/line &lt;match&gt; &lt;total&gt; &lt;over&gt; &lt;under&gt;
  Ex: <code>/line Lakers Celtics 215.5 1.90 1.95</code>
/lines — Voir les lignes manuelles actives
/clear — Effacer les lignes manuelles
/help — Afficher cette aide
"""


async def poll_commands() -> list[str]:
    """Récupère et traite les commandes envoyées au bot.
    Retourne une liste d'actions à effectuer ('scan', etc.)."""
    global _update_offset
    actions = []

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{API_URL}/getUpdates",
                params={"offset": _update_offset, "timeout": 1},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        log.warning(f"Erreur polling Telegram : {e}")
        return actions

    for update in data.get("result", []):
        _update_offset = update["update_id"] + 1
        msg = update.get("message", {})
        text = msg.get("text", "").strip()
        chat_id = msg.get("chat", {}).get("id")

        # Ignorer les messages d'autres chats
        if chat_id != TELEGRAM_CHAT_ID:
            continue

        if text.startswith("/scan"):
            actions.append("scan")
            await send_status("🔄 Scan forcé en cours…")

        elif text.startswith("/line "):
            await _handle_line_command(text)

        elif text.startswith("/lines"):
            await _handle_lines_list()

        elif text.startswith("/clear"):
            clear_manual_lines()
            await send_status("🗑 Lignes manuelles effacées.")

        elif text.startswith("/help") or text.startswith("/start"):
            await _send_message(HELP_TEXT)

    return actions


async def _handle_line_command(text: str) -> None:
    """Parse et enregistre une ligne O/U manuelle.
    Format: /line <match_key> <total> <over_odds> <under_odds>
    Ex: /line Lakers Celtics 215.5 1.90 1.95
    """
    parts = text.split()
    # Au minimum : /line <mot1> <total> <over> <under>
    if len(parts) < 5:
        await send_status(
            "⚠️ Format : <code>/line NomEquipe 215.5 1.90 1.95</code>"
        )
        return

    try:
        under_odds = float(parts[-1])
        over_odds = float(parts[-2])
        total = float(parts[-3])
        match_key = " ".join(parts[1:-3])
    except ValueError:
        await send_status(
            "⚠️ Format : <code>/line NomEquipe 215.5 1.90 1.95</code>"
        )
        return

    line = set_manual_line(match_key, total, over_odds, under_odds)
    await send_status(
        f"✅ Ligne enregistrée : <b>{match_key}</b>\n"
        f"   Total: {line.total}  O: {line.over_odds:.2f}  U: {line.under_odds:.2f}"
    )


async def _handle_lines_list() -> None:
    """Affiche les lignes manuelles actives."""
    from pinnacle import _manual_lines
    if not _manual_lines:
        await send_status("📭 Aucune ligne manuelle enregistrée.")
        return

    text = "📋 <b>Lignes manuelles :</b>\n\n"
    for key, line in _manual_lines.items():
        text += f"• <b>{key}</b> — {line.total} (O {line.over_odds:.2f} / U {line.under_odds:.2f})\n"
    await _send_message(text)
