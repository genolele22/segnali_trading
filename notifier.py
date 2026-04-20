"""
NOTIFIER — Invio messaggi su Telegram
"""

import os
import logging
from datetime import datetime
import pytz
import requests

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID        = os.environ.get("CHAT_ID", "")
ROME_TZ        = pytz.timezone("Europe/Rome")

TELEGRAM_API   = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"


def _send(text: str) -> bool:
    """Invia un messaggio Telegram. Ritorna True se ok."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logger.error("TELEGRAM_TOKEN o CHAT_ID non configurati nelle variabili d'ambiente")
        return False
    try:
        resp = requests.post(TELEGRAM_API, json={
            "chat_id":    CHAT_ID,
            "text":       text,
            "parse_mode": "HTML"
        }, timeout=10)
        if resp.status_code == 200:
            logger.info("Messaggio Telegram inviato")
            return True
        else:
            logger.error(f"Telegram error {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Errore invio Telegram: {e}")
        return False


def send_telegram(signal: dict) -> bool:
    """
    Formatta e invia un segnale di trading.
    signal = {
        "strategia": "🟢 SURFISTA",
        "asset":      "S&P 500",
        "timeframe":  "1H",
        "direzione":  "LONG",
        "entry":      "5120.50",
        "sl":         "5095.30",
        "tp":         "5170.90",
        "rr":         "1:2",
        "note":       "..."
    }
    """
    now  = datetime.now(ROME_TZ).strftime("%d/%m/%Y %H:%M")
    icon = "🟢" if signal.get("direzione") == "LONG" else "🔴"

    msg = (
        f"<b>{signal['strategia']} — {signal['direzione']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Asset:</b> {signal['asset']}\n"
        f"⏱ <b>Timeframe:</b> {signal['timeframe']}\n"
        f"🎯 <b>Entry:</b> <code>{signal['entry']}</code>\n"
        f"🛑 <b>Stop Loss:</b> <code>{signal['sl']}</code>\n"
        f"✅ <b>Take Profit:</b> <code>{signal['tp']}</code>\n"
        f"📐 <b>R:R:</b> {signal['rr']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 {signal.get('note', '')}\n\n"
        f"⚠️ <b>Rischia max 1% del capitale</b>\n"
        f"🕐 {now}"
    )
    return _send(msg)


def send_startup_message():
    """Messaggio di avvio bot."""
    now = datetime.now(ROME_TZ).strftime("%d/%m/%Y %H:%M")
    msg = (
        f"🤖 <b>Trading Bot — Avviato</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Strategie attive:\n"
        f"1️⃣ Surfista — S&amp;P500 1H (15:30–21:00)\n"
        f"2️⃣ Il Pendolo — Oro 1H (08:00–18:00)\n"
        f"3️⃣ Rompighiaccio — Nasdaq 15min (15:30–17:30)\n"
        f"4️⃣ Barile Caldo — WTI 4H (sempre)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <b>Ricorda:</b> max 1% rischio per trade\n"
        f"📅 Controlla ForexFactory ogni mattina\n"
        f"🕐 {now}"
    )
    _send(msg)


def send_error(message: str):
    """Invia un messaggio di errore."""
    _send(f"❌ <b>Bot Error</b>\n{message}")
