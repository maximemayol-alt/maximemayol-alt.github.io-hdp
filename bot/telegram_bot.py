"""Envoi des alertes formatées sur Telegram via l'API HTTP."""

from __future__ import annotations

import logging
import httpx

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from analyzer import Verdict

log = logging.getLogger(__name__)
API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


async def _send(text: str) -> None:
    """Envoie un message via l'API Telegram."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{API_URL}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
            },
        )
        resp.raise_for_status()


async def send_verdict(v: Verdict) -> None:
    """Envoie un verdict — format complet si cote dispo, pace-only sinon."""
    if v.has_line:
        ml_str = ""
        if v.home_ml > 0 and v.away_ml > 0:
            ml_str = f"\n💰 ML : {v.home_ml:.2f} / {v.away_ml:.2f}"
        msg = (
            f"🏀 <b>{v.match}</b> — {v.league}\n"
            f"📊 Score MT : {v.home_score}-{v.away_score}\n"
            f"⚡ Pace : {v.pace} | Ligne : {v.line} | GAP : {v.gap:+.1f}\n"
            f"🎯 Shooting : {v.home_fg_pct:.0f}% / {v.away_fg_pct:.0f}%\n"
            f"⚠️ Fautes : {v.total_fouls} | Reb Off : {v.total_off_reb}{ml_str}\n"
            f"→ <b>{v.signal}</b>\n"
            f"📈 EV estimé : {v.ev:+.1%}\n"
            f"\n"
            f"<i>{v.reasoning}</i>"
        )
    else:
        msg = (
            f"🏀 <b>{v.match}</b> — {v.league}\n"
            f"📊 Score MT : {v.home_score}-{v.away_score}\n"
            f"⚡️ Pace projeté : {v.pace}\n"
            f"🎯 Shooting : {v.home_fg_pct:.0f}% / {v.away_fg_pct:.0f}%\n"
            f"⚠️ Fautes : {v.total_fouls} | Reb Off : {v.total_off_reb}\n"
            f"📌 Vérifie la ligne sur PS3838\n"
            f"→ Signal directionnel : <b>{v.signal}</b>\n"
            f"\n"
            f"<i>{v.reasoning}</i>"
        )
    await _send(msg)


async def send_status(text: str) -> None:
    """Envoie un message de statut."""
    await _send(text)
