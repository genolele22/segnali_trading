"""
TRADING BOT — 5 Strategie Profittevoli
1. VWAP Reversal Oro 15min    (PF 1.84) — intraday
2. London Sweep Oro 15min     (PF 1.55) — intraday 08-10 CET
3. ORB S&P500 15min           (PF 1.40) — intraday
4. Kumo Rider Oro 4H          (PF 1.62) — swing
5. Kumo Rider Nasdaq 1H       (PF 1.51) — swing
"""

import os
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, time
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR

from strategies import (
    check_vwap_reversal_gold,
    check_london_sweep_gold,
    check_orb_sp500,
    check_kumo_gold_4h,
    check_kumo_nasdaq_1h,
)
from notifier import send_telegram, send_startup_message
from news_filter import is_news_window

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)
ROME_TZ = pytz.timezone("Europe/Rome")

# Anti-duplicazione segnali
last_signals: dict = {}

def should_send(name: str, direction: str, cooldown_h: int = 4) -> bool:
    now = datetime.now(ROME_TZ)
    if name not in last_signals:
        return True
    last = last_signals[name]
    hours = (now - last["timestamp"]).total_seconds() / 3600
    if last["direction"] == direction and hours < cooldown_h:
        logger.info(f"[{name}] Segnale {direction} già inviato {hours:.1f}h fa — skip")
        return False
    return True

def register(name: str, direction: str):
    last_signals[name] = {"direction": direction, "timestamp": datetime.now(ROME_TZ)}

def run_check(name: str, fn, cooldown_h: int = 4):
    try:
        if is_news_window():
            logger.info(f"[{name}] Finestra news — skip")
            return
        signal = fn()
        if signal and should_send(name, signal["direzione"], cooldown_h):
            send_telegram(signal)
            register(name, signal["direzione"])
    except Exception as e:
        logger.error(f"[{name}] Errore: {e}")

# ── Job functions ─────────────────────────────────────────────────────────────
def job_vwap_gold():
    logger.info("▶ VWAP Reversal Oro (15min)")
    run_check("vwap_gold", check_vwap_reversal_gold, cooldown_h=4)

def job_london_sweep():
    now = datetime.now(ROME_TZ)
    if not (time(8, 0) <= now.time() <= time(10, 0)):
        return
    logger.info("▶ London Sweep Oro (15min)")
    run_check("london_sweep", check_london_sweep_gold, cooldown_h=12)

def job_orb_sp500():
    now = datetime.now(ROME_TZ)
    if not (time(15, 45) <= now.time() <= time(21, 45)):
        return
    logger.info("▶ ORB S&P500 (15min)")
    run_check("orb_sp500", check_orb_sp500, cooldown_h=8)

def job_kumo_gold_4h():
    logger.info("▶ Kumo Rider Oro (4H)")
    run_check("kumo_gold_4h", check_kumo_gold_4h, cooldown_h=12)

def job_kumo_nasdaq():
    now = datetime.now(ROME_TZ)
    if not (time(15, 30) <= now.time() <= time(21, 0)):
        return
    logger.info("▶ Kumo Rider Nasdaq (1H)")
    run_check("kumo_nasdaq", check_kumo_nasdaq_1h, cooldown_h=8)

# ── Health server ─────────────────────────────────────────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Trading Bot OK")
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    logger.info("═══════════════════════════════════════")
    logger.info("  TRADING BOT — 5 Strategie Profittevoli")
    logger.info("═══════════════════════════════════════")

    threading.Thread(target=run_health_server, daemon=True).start()

    scheduler = BackgroundScheduler(timezone=ROME_TZ)
    scheduler.add_listener(lambda e: logger.error(f"Job error: {e.exception}"), EVENT_JOB_ERROR)

    # VWAP Reversal Oro: ogni 15min (orario filtrato internamente)
    scheduler.add_job(job_vwap_gold,    "interval", minutes=15, id="vwap_gold")

    # London Sweep: ogni 15min dalle 08-10 (filtro interno)
    scheduler.add_job(job_london_sweep, "interval", minutes=15, id="london_sweep")

    # ORB S&P500: ogni 15min dalle 15:45-21:45 (filtro interno)
    scheduler.add_job(job_orb_sp500,    "interval", minutes=15, id="orb_sp500")

    # Kumo Gold 4H: ogni 4 ore
    scheduler.add_job(job_kumo_gold_4h, "cron",
                      hour="0,4,8,12,16,20", minute=20, id="kumo_gold_4h")

    # Kumo Nasdaq 1H: ogni ora durante sessione USA
    scheduler.add_job(job_kumo_nasdaq,  "cron", minute=5, id="kumo_nasdaq")

    scheduler.start()
    send_startup_message()
    logger.info("Bot in ascolto...")

    import time as time_module
    while True:
        time_module.sleep(60)

if __name__ == "__main__":
    main()
