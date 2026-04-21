"""
TRADING BOT — Revolut CFD Signal System
"""

import os
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, time
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR

from strategies import check_surfista, check_pendolo, check_rompighiaccio, check_barile_caldo
from notifier import send_telegram, send_startup_message
from news_filter import is_news_window

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

ROME_TZ = pytz.timezone("Europe/Rome")

last_signals: dict = {}


def should_send(strategy_name: str, direction: str, cooldown_hours: int = 4) -> bool:
    now = datetime.now(ROME_TZ)
    if strategy_name not in last_signals:
        return True
    last = last_signals[strategy_name]
    hours_passed = (now - last["timestamp"]).total_seconds() / 3600
    if last["direzione"] == direction and hours_passed < cooldown_hours:
        logger.info(f"[{strategy_name}] Segnale {direction} già inviato {hours_passed:.1f}h fa — skip")
        return False
    return True


def register_signal(strategy_name: str, direction: str):
    last_signals[strategy_name] = {
        "direzione": direction,
        "timestamp": datetime.now(ROME_TZ)
    }


def job_surfista():
    logger.info("▶ Controllo SURFISTA (S&P500 1H)")
    try:
        if is_news_window():
            logger.info("[Surfista] Finestra news — skip")
            return
        signal = check_surfista()
        if signal and should_send("surfista", signal["direzione"], cooldown_hours=4):
            send_telegram(signal)
            register_signal("surfista", signal["direzione"])
    except Exception as e:
        logger.error(f"[Surfista] Errore: {e}")


def job_pendolo():
    logger.info("▶ Controllo IL PENDOLO (Oro 1H)")
    try:
        if is_news_window():
            logger.info("[Pendolo] Finestra news — skip")
            return
        signal = check_pendolo()
        if signal and should_send("pendolo", signal["direzione"], cooldown_hours=4):
            send_telegram(signal)
            register_signal("pendolo", signal["direzione"])
    except Exception as e:
        logger.error(f"[Pendolo] Errore: {e}")


def job_rompighiaccio():
    now = datetime.now(ROME_TZ)
    if not (time(15, 25) <= now.time() <= time(17, 35)):
        return
    logger.info("▶ Controllo ROMPIGHIACCIO (Nasdaq 15min)")
    try:
        if is_news_window():
            logger.info("[Rompighiaccio] Finestra news — skip")
            return
        signal = check_rompighiaccio()
        if signal and should_send("rompighiaccio", signal["direzione"], cooldown_hours=8):
            send_telegram(signal)
            register_signal("rompighiaccio", signal["direzione"])
    except Exception as e:
        logger.error(f"[Rompighiaccio] Errore: {e}")


def job_barile_caldo():
    logger.info("▶ Controllo BARILE CALDO (WTI 4H)")
    try:
        signal = check_barile_caldo()
        if signal and should_send("barile_caldo", signal["direzione"], cooldown_hours=12):
            send_telegram(signal)
            register_signal("barile_caldo", signal["direzione"])
    except Exception as e:
        logger.error(f"[Barile Caldo] Errore: {e}")


def on_job_error(event):
    logger.error(f"Job fallito: {event.exception}")


# ── Health check server (richiesto da Railway) ────────────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Trading Bot OK")

    def log_message(self, format, *args):
        pass  # Silenzia i log HTTP


def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info(f"Health server avviato su porta {port}")
    server.serve_forever()


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    logger.info("═══════════════════════════════════")
    logger.info("  TRADING BOT — Avvio sistema")
    logger.info("═══════════════════════════════════")

    # Avvia health server in background (richiesto da Railway)
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()

    # Scheduler in background
    scheduler = BackgroundScheduler(timezone=ROME_TZ)
    scheduler.add_listener(on_job_error, EVENT_JOB_ERROR)

    scheduler.add_job(job_surfista,      "cron", minute=3,
                      id="surfista",      name="Surfista S&P500")
    scheduler.add_job(job_pendolo,       "cron", minute=8,
                      id="pendolo",       name="Il Pendolo Oro")
    scheduler.add_job(job_rompighiaccio, "interval", minutes=15,
                      id="rompighiaccio", name="Rompighiaccio Nasdaq")
    scheduler.add_job(job_barile_caldo,  "cron",
                      hour="0,4,8,12,16,20", minute=15,
                      id="barile_caldo",  name="Barile Caldo WTI")

    scheduler.start()
    send_startup_message()

    logger.info("Bot in ascolto...")

    # Tieni vivo il processo principale
    import time as time_module
    while True:
        time_module.sleep(60)


if __name__ == "__main__":
    main()
