"""
FILTRO ANTI-NEWS
Blocca i segnali durante le finestre temporali ad alto rischio.
Non usa API esterne — basato su orari fissi noti.
"""

from datetime import datetime, time
import pytz

ROME_TZ = pytz.timezone("Europe/Rome")


# Finestre ad alto rischio ogni settimana (ora CET/CEST)
# NFP: primo venerdì del mese ore 14:30
# FOMC: ~8 volte l'anno ore 20:00
# CPI: mensile ore 14:30
# Crude Oil Inventories: mercoledì 16:30
DAILY_RISK_WINDOWS = {
    # (giorno_settimana 0=Lun, ora_inizio, ora_fine)
    # Mercoledì: Crude Oil Inventories 16:00–17:30 CET
    2: [(time(15, 50), time(17, 30))],
    # Venerdì: possibile NFP / dati USA 14:00–15:30 CET
    4: [(time(14, 0), time(15, 30))],
}

# Ore universalmente rischiose ogni giorno (intorno alle 14:30 CET = dati USA)
UNIVERSAL_RISK_WINDOWS = [
    (time(14, 20), time(15, 00)),   # Buffer pre-dati USA (14:30 CET)
    (time(19, 50), time(20, 30)),   # Buffer FOMC / Fed speeches (20:00 CET)
]


def is_news_window() -> bool:
    """
    Ritorna True se siamo in una finestra temporale ad alto rischio.
    In quel caso il bot salta il controllo dei segnali.
    """
    now      = datetime.now(ROME_TZ)
    weekday  = now.weekday()  # 0=Lunedì, 6=Domenica
    cur_time = now.time()

    # Controllo finestre universali
    for start, end in UNIVERSAL_RISK_WINDOWS:
        if start <= cur_time <= end:
            return True

    # Controllo finestre giornaliere specifiche
    if weekday in DAILY_RISK_WINDOWS:
        for start, end in DAILY_RISK_WINDOWS[weekday]:
            if start <= cur_time <= end:
                return True

    # Lunedì mattina: gap weekend, mercati instabili
    if weekday == 0 and cur_time <= time(10, 0):
        return True

    return False


def is_trading_day() -> bool:
    """Ritorna True se oggi è un giorno lavorativo (Lun–Ven)."""
    return datetime.now(ROME_TZ).weekday() < 5
