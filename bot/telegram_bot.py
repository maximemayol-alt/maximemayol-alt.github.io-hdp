"""Envoi des verdicts sur Telegram via l'API HTTP directe (httpx)."""

from __future__ import annotations

import httpx
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from calculator import Verdict

API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


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
