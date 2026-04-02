"""Envoi des verdicts sur Telegram."""

from __future__ import annotations

import telegram
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from calculator import Verdict


async def send_verdict(verdict: Verdict) -> None:
    """Envoie un message Telegram formaté avec le verdict."""
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

    message = (
        f"🏀 <b>{verdict.match}</b>\n"
        f"{'━' * 28}\n"
        f"\n"
        f"🚦 Signal : <b>{verdict.signal}</b>\n"
        f"\n"
        f"{verdict.details}\n"
        f"{'━' * 28}\n"
    )

    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=message,
        parse_mode="HTML",
    )


async def send_status(text: str) -> None:
    """Envoie un message de statut simple."""
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=text,
        parse_mode="HTML",
    )


async def send_no_games() -> None:
    """Notifie qu'aucun match live n'a été trouvé."""
    await send_status("🏀 Aucun match de basket live détecté. Prochain scan bientôt…")
