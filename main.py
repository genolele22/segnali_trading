import os, logging, threading, time as time_module
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, time
import pytz

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
ROME_TZ = pytz.timezone("Europe/Rome")

# ── Health server — avvia PRIMA di qualsiasi import pesante ──────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def log_message(self, format, *args): pass

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info(f"Health server su porta {port}")
    server.serve_forever()

# Avvia health server nel thread principale subito
health_thread = threading.Thread(target=run_health_server, daemon=True)
health_thread.start()
time_module.sleep(2)  # dai tempo al server di partire
logger.info("Health server avviato")

# ── Ora importa il resto ──────────────────────────────────────────────────────
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.events import EVENT_JOB_ERROR
    logger.info("APScheduler importato OK")
except Exception as e:
    logger.error(f"Errore import APScheduler: {e}")

try:
    from strategies import (
        check_vwap_reversal_gold, check_london_sweep_gold,
        check_orb_sp500, check_kumo_gold_4h, check_kumo_nasdaq_1h,
    )
    logger.info("Strategies importate OK")
except Exception as e:
    logger.error(f"Errore import strategies: {e}")

try:
    from notifier import send_telegram, send_startup_message
    logger.info("Notifier importato OK")
except Exception as e:
    logger.error(f"Errore import notifier: {e}")

try:
    from news_filter import is_news_window
    logger.info("News filter importato OK")
except Exception as e:
    logger.error(f"Errore import news_filter: {e}")
    def is_news_window(): return False

# ── Logica bot ────────────────────────────────────────────────────────────────
last_signals: dict = {}

def should_send(name, direction, cooldown_h=4):
    now = datetime.now(ROME_TZ)
    if name not in last_signals: return True
    last = last_signals[name]
    hours = (now - last["timestamp"]).total_seconds() / 3600
    return not (last["direction"] == direction and hours < cooldown_h)

def register(name, direction):
    last_signals[name] = {"direction": direction, "timestamp": datetime.now(ROME_TZ)}

def run_check(name, fn, cooldown_h=4):
    try:
        if is_news_window(): return
        signal = fn()
        if signal and should_send(name, signal["direzione"], cooldown_h):
            send_telegram(signal)
            register(name, signal["direzione"])
    except Exception as e:
        logger.error(f"[{name}] Errore: {e}")

def job_vwap_gold():
    logger.info("▶ VWAP Reversal Oro")
    run_check("vwap_gold", check_vwap_reversal_gold, 4)

def job_london_sweep():
    now = datetime.now(ROME_TZ)
    if not (time(8,0) <= now.time() <= time(10,0)): return
    logger.info("▶ London Sweep Oro")
    run_check("london_sweep", check_london_sweep_gold, 12)

def job_orb_sp500():
    now = datetime.now(ROME_TZ)
    if not (time(15,45) <= now.time() <= time(21,45)): return
    logger.info("▶ ORB S&P500")
    run_check("orb_sp500", check_orb_sp500, 8)

def job_kumo_gold_4h():
    logger.info("▶ Kumo Rider Oro 4H")
    run_check("kumo_gold_4h", check_kumo_gold_4h, 12)

def job_kumo_nasdaq():
    now = datetime.now(ROME_TZ)
    if not (time(15,30) <= now.time() <= time(21,0)): return
    logger.info("▶ Kumo Rider Nasdaq 1H")
    run_check("kumo_nasdaq", check_kumo_nasdaq_1h, 8)

# ── Main ──────────────────────────────────────────────────────────────────────
logger.info("═══════════════════════════════════════")
logger.info("  TRADING BOT — 5 Strategie Profittevoli")
logger.info("═══════════════════════════════════════")

try:
    scheduler = BackgroundScheduler(timezone=ROME_TZ)
    scheduler.add_listener(lambda e: logger.error(f"Job error: {e.exception}"), EVENT_JOB_ERROR)
    scheduler.add_job(job_vwap_gold,    "interval", minutes=15, id="vwap_gold")
    scheduler.add_job(job_london_sweep, "interval", minutes=15, id="london_sweep")
    scheduler.add_job(job_orb_sp500,    "interval", minutes=15, id="orb_sp500")
    scheduler.add_job(job_kumo_gold_4h, "cron", hour="0,4,8,12,16,20", minute=20, id="kumo_gold_4h")
    scheduler.add_job(job_kumo_nasdaq,  "cron", minute=5, id="kumo_nasdaq")
    scheduler.start()
    logger.info("Scheduler avviato")
except Exception as e:
    logger.error(f"Errore scheduler: {e}")

try:
    send_startup_message()
    logger.info("Messaggio avvio inviato")
except Exception as e:
    logger.error(f"Errore startup message: {e}")

logger.info("Bot in ascolto...")
while True:
    time_module.sleep(60)
