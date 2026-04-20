"""
TRADING BOT — Revolut CFD Signal System
Strategie: Surfista (S&P500), Il Pendolo (Oro), Rompighiaccio (Nasdaq), Barile Caldo (WTI)
"""

import os
import logging
from datetime import datetime, time
import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.events import EVENT_JOB_ERROR

from strategies import check_surfista, check_pendolo, check_rompighiaccio, check_barile_caldo
from notifier import send_telegram, send_startup_message
from news_filter import is_news_window

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

ROME_TZ = pytz.timezone("Europe/Rome")

# ── Stato segnali (anti-duplicazione) ────────────────────────────────────────
# Tiene traccia dell'ultimo segnale inviato per ogni strategia
# Formato: {"strategia": {"direzione": "LONG", "timestamp": datetime}}
last_signals: dict = {}


def should_send(strategy_name: str, direction: str, cooldown_hours: int = 4) -> bool:
    """
    Evita di inviare lo stesso segnale più volte nello stesso periodo.
    Ritorna True se il segnale è nuovo o abbastanza distante dall'ultimo.
    """
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
    """Registra l'invio di un segnale."""
    last_signals[strategy_name] = {
        "direzione": direction,
        "timestamp": datetime.now(ROME_TZ)
    }


# ── Job: Surfista — S&P500 1H ─────────────────────────────────────────────────
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


# ── Job: Il Pendolo — Oro 1H ──────────────────────────────────────────────────
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


# ── Job: Rompighiaccio — Nasdaq 15min ─────────────────────────────────────────
def job_rompighiaccio():
    now = datetime.now(ROME_TZ)
    # Solo nella finestra apertura USA: 15:30–17:30 CET
    if not (time(15, 25) <= now.time() <= time(17, 35)):
        return
    logger.info("▶ Controllo ROMPIGHIACCIO (Nasdaq 15min)")
    try:
        if is_news_window():
            logger.info("[Rompighiaccio] Finestra news — skip")
            return
        signal = check_rompighiaccio()
        # Cooldown più breve: segnale di breakout vale una volta per sessione
        if signal and should_send("rompighiaccio", signal["direzione"], cooldown_hours=8):
            send_telegram(signal)
            register_signal("rompighiaccio", signal["direzione"])
    except Exception as e:
        logger.error(f"[Rompighiaccio] Errore: {e}")


# ── Job: Barile Caldo — WTI 4H ────────────────────────────────────────────────
def job_barile_caldo():
    logger.info("▶ Controllo BARILE CALDO (WTI 4H)")
    try:
        signal = check_barile_caldo()
        # Swing: cooldown lungo, un segnale ogni 12h al massimo
        if signal and should_send("barile_caldo", signal["direzione"], cooldown_hours=12):
            send_telegram(signal)
            register_signal("barile_caldo", signal["direzione"])
    except Exception as e:
        logger.error(f"[Barile Caldo] Errore: {e}")


# ── Error handler scheduler ───────────────────────────────────────────────────
def on_job_error(event):
    logger.error(f"Job fallito: {event.exception}")


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    logger.info("═══════════════════════════════════")
    logger.info("  TRADING BOT — Avvio sistema")
    logger.info("═══════════════════════════════════")

    scheduler = BlockingScheduler(timezone=ROME_TZ)
    scheduler.add_listener(on_job_error, EVENT_JOB_ERROR)

    # Surfista + Il Pendolo: ogni ora al minuto :03 (dati settled)
    scheduler.add_job(job_surfista, "cron", minute=3,
                      id="surfista", name="Surfista S&P500")
    scheduler.add_job(job_pendolo,  "cron", minute=8,
                      id="pendolo",  name="Il Pendolo Oro")

    # Rompighiaccio: ogni 15 minuti (il job stesso filtra l'orario)
    scheduler.add_job(job_rompighiaccio, "interval", minutes=15,
                      id="rompighiaccio", name="Rompighiaccio Nasdaq")

    # Barile Caldo: ogni 4 ore al minuto :15
    scheduler.add_job(job_barile_caldo, "cron",
                      hour="0,4,8,12,16,20", minute=15,
                      id="barile_caldo", name="Barile Caldo WTI")

    # Messaggio di avvio su Telegram
    send_startup_message()

    logger.info("Scheduler avviato. Bot in ascolto...")
    scheduler.start()


if __name__ == "__main__":
    main()
