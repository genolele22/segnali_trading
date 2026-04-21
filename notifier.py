"""NOTIFIER — Invio messaggi Telegram"""

import os, logging, requests
from datetime import datetime
import pytz

logger       = logging.getLogger(__name__)
ROME_TZ      = pytz.timezone("Europe/Rome")
TOKEN        = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID      = os.environ.get("CHAT_ID", "")
API          = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

def _send(text: str) -> bool:
    if not TOKEN or not CHAT_ID:
        logger.error("TELEGRAM_TOKEN o CHAT_ID mancanti")
        return False
    try:
        r = requests.post(API, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
        return r.status_code == 200
    except Exception as e:
        logger.error(f"Telegram error: {e}"); return False

def send_telegram(signal: dict) -> bool:
    now  = datetime.now(ROME_TZ).strftime("%d/%m %H:%M")
    tipo = "🟢 LONG" if signal.get("direzione") == "LONG" else "🔴 SHORT"
    overnight = "⏰ <b>SWING — può restare overnight</b>" if "4H" in signal.get("timeframe","") or "1H" in signal.get("timeframe","") else "⏱ <b>INTRADAY — chiudi entro 21:45 CET</b>"

    msg = (
        f"<b>{signal['strategia']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Asset:</b> {signal['asset']}\n"
        f"⏱ <b>TF:</b> {signal['timeframe']}\n"
        f"🎯 <b>Entry:</b> <code>{signal['entry']}</code>\n"
        f"🛑 <b>Stop:</b>  <code>{signal['sl']}</code>\n"
        f"✅ <b>Target:</b> <code>{signal['tp']}</code>\n"
        f"📐 <b>R:R:</b> {signal['rr']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 {signal.get('note','')}\n\n"
        f"{overnight}\n"
        f"⚠️ <b>Rischia max 1.5% capitale</b>\n"
        f"🕐 {now}"
    )
    return _send(msg)

def send_startup_message():
    now = datetime.now(ROME_TZ).strftime("%d/%m/%Y %H:%M")
    msg = (
        f"🤖 <b>Trading Bot — Avviato</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Strategie attive:</b>\n"
        f"1️⃣ VWAP Reversal Oro 15min (PF 1.84)\n"
        f"2️⃣ London Sweep Oro 08-10 CET (PF 1.55)\n"
        f"3️⃣ ORB S&amp;P500 15min (PF 1.40)\n"
        f"4️⃣ Kumo Rider Oro 4H swing (PF 1.62)\n"
        f"5️⃣ Kumo Rider Nasdaq 1H swing (PF 1.51)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Max 1.5% per trade | Max 4% totale\n"
        f"📅 Controlla ForexFactory ogni mattina\n"
        f"🕐 {now}"
    )
    _send(msg)
    
