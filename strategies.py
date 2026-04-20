"""
STRATEGIE DI TRADING
Ogni funzione ritorna None (nessun segnale) o un dict con i dettagli del segnale.
"""

import logging
from datetime import datetime, date, time
from typing import Optional

import numpy as np
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import pytz

logger = logging.getLogger(__name__)

ROME_TZ = pytz.timezone("Europe/Rome")
ET_TZ   = pytz.timezone("America/New_York")

# ── Ticker yfinance (più vicini ai CFD Revolut) ───────────────────────────────
TICKER_SP500  = "^GSPC"
TICKER_NASDAQ = "^NDX"
TICKER_GOLD   = "GC=F"
TICKER_WTI    = "CL=F"


# ── Helper: scarica dati ──────────────────────────────────────────────────────
def get_data(ticker: str, period: str, interval: str) -> Optional[pd.DataFrame]:
    try:
        df = yf.download(ticker, period=period, interval=interval,
                         progress=False, auto_adjust=True)
        if df is None or len(df) < 30:
            logger.warning(f"Dati insufficienti per {ticker}")
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        return df.dropna()
    except Exception as e:
        logger.error(f"Errore download {ticker}: {e}")
        return None


# ── Helper: VWAP giornaliero ──────────────────────────────────────────────────
def calc_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Calcola il VWAP resettato ogni giorno.
    Funziona solo su dati intraday con DatetimeIndex timezone-aware.
    """
    df = df.copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")

    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    df["_tp_vol"] = typical * df["Volume"]
    df["_date"]   = df.index.date

    vwap_values = []
    for d, group in df.groupby("_date"):
        cum_tp_vol = group["_tp_vol"].cumsum()
        cum_vol    = group["Volume"].cumsum()
        vwap_day   = cum_tp_vol / cum_vol
        vwap_values.append(vwap_day)

    return pd.concat(vwap_values).reindex(df.index)


# ── Helper: resample 1H → 4H ──────────────────────────────────────────────────
def resample_4h(df: pd.DataFrame) -> pd.DataFrame:
    return df.resample("4h").agg({
        "Open":  "first",
        "High":  "max",
        "Low":   "min",
        "Close": "last",
        "Volume":"sum"
    }).dropna()


# ── Helper: formatta prezzo ───────────────────────────────────────────────────
def fmt(value, decimals=2) -> str:
    try:
        return f"{float(value):.{decimals}f}"
    except Exception:
        return str(value)


# ══════════════════════════════════════════════════════════════════════════════
# STRATEGIA 1 — "SURFISTA" — Trend Following S&P500 1H
# Logica: EMA 9 cross EMA 21 + RSI 14 confermato
# ══════════════════════════════════════════════════════════════════════════════
def check_surfista() -> Optional[dict]:
    df = get_data(TICKER_SP500, period="30d", interval="1h")
    if df is None or len(df) < 50:
        return None

    # Indicatori
    df["ema9"]  = ta.ema(df["Close"], length=9)
    df["ema21"] = ta.ema(df["Close"], length=21)
    df["rsi"]   = ta.rsi(df["Close"], length=14)
    atr_series  = ta.atr(df["High"], df["Low"], df["Close"], length=14)
    df["atr"]   = atr_series

    df.dropna(inplace=True)
    if len(df) < 3:
        return None

    # Filtro orario: 15:30–21:00 CET
    last_bar_cet = df.index[-1].tz_convert(ROME_TZ)
    if not (time(15, 30) <= last_bar_cet.time() <= time(21, 0)):
        logger.info("[Surfista] Fuori orario operativo")
        return None

    prev  = df.iloc[-2]
    curr  = df.iloc[-1]

    # Crossover EMA (barra precedente ema9 < ema21, barra corrente ema9 > ema21)
    cross_up   = prev["ema9"] <= prev["ema21"] and curr["ema9"] > curr["ema21"]
    cross_down = prev["ema9"] >= prev["ema21"] and curr["ema9"] < curr["ema21"]

    entry = curr["Close"]
    atr   = curr["atr"]

    if cross_up and curr["rsi"] > 50:
        sl = entry - 1.5 * atr
        tp = entry + 3.0 * atr
        return {
            "strategia": "🟢 SURFISTA",
            "asset":      "S&P 500",
            "timeframe":  "1H",
            "direzione":  "LONG",
            "entry":      fmt(entry, 2),
            "sl":         fmt(sl, 2),
            "tp":         fmt(tp, 2),
            "rr":         "1:2",
            "note":       "EMA9 incrocia al rialzo EMA21 | RSI > 50"
        }

    if cross_down and curr["rsi"] < 50:
        sl = entry + 1.5 * atr
        tp = entry - 3.0 * atr
        return {
            "strategia": "🔴 SURFISTA",
            "asset":      "S&P 500",
            "timeframe":  "1H",
            "direzione":  "SHORT",
            "entry":      fmt(entry, 2),
            "sl":         fmt(sl, 2),
            "tp":         fmt(tp, 2),
            "rr":         "1:2",
            "note":       "EMA9 incrocia al ribasso EMA21 | RSI < 50"
        }

    return None


# ══════════════════════════════════════════════════════════════════════════════
# STRATEGIA 2 — "IL PENDOLO" — Mean Reversion Oro 1H
# Logica: BB (20, 2.2) + RSI estremo (< 25 / > 75) + VWAP
# ══════════════════════════════════════════════════════════════════════════════
def check_pendolo() -> Optional[dict]:
    df = get_data(TICKER_GOLD, period="30d", interval="1h")
    if df is None or len(df) < 50:
        return None

    # Bollinger Bands
    bb = ta.bbands(df["Close"], length=20, std=2.2)
    df["bb_upper"] = bb["BBU_20_2.2"]
    df["bb_lower"] = bb["BBL_20_2.2"]
    df["bb_mid"]   = bb["BBM_20_2.2"]

    df["rsi"] = ta.rsi(df["Close"], length=14)
    atr_s     = ta.atr(df["High"], df["Low"], df["Close"], length=14)
    df["atr"] = atr_s

    # VWAP
    try:
        df["vwap"] = calc_vwap(df)
    except Exception:
        df["vwap"] = df["Close"].rolling(20).mean()  # fallback

    df.dropna(inplace=True)
    if len(df) < 3:
        return None

    # Filtro orario: 08:00–18:00 CET
    last_bar_cet = df.index[-1].tz_convert(ROME_TZ)
    if not (time(8, 0) <= last_bar_cet.time() <= time(18, 0)):
        logger.info("[Pendolo] Fuori orario operativo")
        return None

    curr  = df.iloc[-1]
    entry = curr["Close"]
    atr   = curr["atr"]

    # LONG: prezzo sotto BB inferiore + RSI ipervenduto + sotto VWAP
    if (curr["Close"] < curr["bb_lower"] and
            curr["rsi"] < 25 and
            curr["Close"] < curr["vwap"]):
        sl = entry - 1.3 * atr
        tp = curr["bb_mid"]  # target: ritorno alla media
        return {
            "strategia": "🟡 IL PENDOLO",
            "asset":      "Oro (XAU/USD)",
            "timeframe":  "1H",
            "direzione":  "LONG",
            "entry":      fmt(entry, 2),
            "sl":         fmt(sl, 2),
            "tp":         fmt(tp, 2),
            "rr":         "~1.3:1 – 1.8:1",
            "note":       "Prezzo < BB Lower | RSI < 25 | Sotto VWAP → mean reversion"
        }

    # SHORT: prezzo sopra BB superiore + RSI ipercomprato + sopra VWAP
    if (curr["Close"] > curr["bb_upper"] and
            curr["rsi"] > 75 and
            curr["Close"] > curr["vwap"]):
        sl = entry + 1.3 * atr
        tp = curr["bb_mid"]
        return {
            "strategia": "🔴 IL PENDOLO",
            "asset":      "Oro (XAU/USD)",
            "timeframe":  "1H",
            "direzione":  "SHORT",
            "entry":      fmt(entry, 2),
            "sl":         fmt(sl, 2),
            "tp":         fmt(tp, 2),
            "rr":         "~1.3:1 – 1.8:1",
            "note":       "Prezzo > BB Upper | RSI > 75 | Sopra VWAP → mean reversion"
        }

    return None


# ══════════════════════════════════════════════════════════════════════════════
# STRATEGIA 3 — "ROMPIGHIACCIO" — Breakout Apertura USA Nasdaq 15min
# Logica: range prime 2 candele (9:30–10:00 ET) + EMA + VWAP
# ══════════════════════════════════════════════════════════════════════════════
def check_rompighiaccio() -> Optional[dict]:
    df = get_data(TICKER_NASDAQ, period="5d", interval="15m")
    if df is None or len(df) < 20:
        return None

    # Converti in ET per lavorare con la sessione NYSE
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert(ET_TZ)

    today_et = datetime.now(ET_TZ).date()
    today_df = df[df.index.date == today_et].copy()

    if len(today_df) < 3:
        return None

    # Dati dalla sessione (9:30 ET in poi)
    session = today_df[today_df.index.time >= time(9, 30)].copy()
    if len(session) < 3:
        return None

    # Range iniziale: prime 2 candele (9:30–10:00 ET)
    range_candles = session.iloc[:2]
    range_high = range_candles["High"].max()
    range_low  = range_candles["Low"].min()

    # Indicatori sull'intero df (per avere abbastanza dati per EMA)
    df_full = df.copy()
    df_full["ema21"] = ta.ema(df_full["Close"], length=21)
    df_full["ema50"] = ta.ema(df_full["Close"], length=50)
    atr_s            = ta.atr(df_full["High"], df_full["Low"], df_full["Close"], length=14)
    df_full["atr"]   = atr_s

    try:
        df_full["vwap"] = calc_vwap(df_full)
    except Exception:
        df_full["vwap"] = df_full["Close"].rolling(20).mean()

    df_full.dropna(inplace=True)

    # Ultima candela disponibile
    curr_idx = df_full.index[-1]
    if curr_idx.date() != today_et:
        return None

    curr = df_full.iloc[-1]

    # Solo nella finestra 9:30–11:30 ET
    curr_time = curr_idx.time()
    if not (time(9, 30) <= curr_time <= time(11, 30)):
        return None

    entry  = curr["Close"]
    atr    = curr["atr"]
    buffer = 0.3 * atr

    # LONG breakout
    if (curr["Close"] > range_high + buffer and
            curr["Close"] > curr["vwap"] and
            curr["ema21"] > curr["ema50"]):
        sl = entry - 1.5 * atr
        tp = entry + 3.0 * atr
        return {
            "strategia": "🔵 ROMPIGHIACCIO",
            "asset":      "Nasdaq 100",
            "timeframe":  "15min",
            "direzione":  "LONG",
            "entry":      fmt(entry, 2),
            "sl":         fmt(sl, 2),
            "tp":         fmt(tp, 2),
            "rr":         "1:2",
            "note":       f"Breakout range apertura (H: {fmt(range_high,2)}) | Sopra VWAP | ⚠️ Spread NAS100 alto su Revolut"
        }

    # SHORT breakout
    if (curr["Close"] < range_low - buffer and
            curr["Close"] < curr["vwap"] and
            curr["ema21"] < curr["ema50"]):
        sl = entry + 1.5 * atr
        tp = entry - 3.0 * atr
        return {
            "strategia": "🔴 ROMPIGHIACCIO",
            "asset":      "Nasdaq 100",
            "timeframe":  "15min",
            "direzione":  "SHORT",
            "entry":      fmt(entry, 2),
            "sl":         fmt(sl, 2),
            "tp":         fmt(tp, 2),
            "rr":         "1:2",
            "note":       f"Breakout range apertura (L: {fmt(range_low,2)}) | Sotto VWAP | ⚠️ Spread NAS100 alto su Revolut"
        }

    return None


# ══════════════════════════════════════════════════════════════════════════════
# STRATEGIA 4 — "BARILE CALDO" — Momentum WTI 4H
# Logica: Supertrend (10, 3) cambia direzione + EMA 200
# ══════════════════════════════════════════════════════════════════════════════
def check_barile_caldo() -> Optional[dict]:
    # Scarica 1H e resample a 4H
    df_1h = get_data(TICKER_WTI, period="120d", interval="1h")
    if df_1h is None or len(df_1h) < 50:
        return None

    df = resample_4h(df_1h)
    if len(df) < 50:
        return None

    # Supertrend
    st = ta.supertrend(df["High"], df["Low"], df["Close"],
                       length=10, multiplier=3.0)
    col_dir  = [c for c in st.columns if c.startswith("SUPERTd")]
    col_line = [c for c in st.columns if c.startswith("SUPERT_")]

    if not col_dir or not col_line:
        logger.error("[Barile Caldo] Colonne Supertrend non trovate")
        return None

    df["st_dir"]  = st[col_dir[0]]
    df["st_line"] = st[col_line[0]]
    df["ema200"]  = ta.ema(df["Close"], length=200)
    atr_s         = ta.atr(df["High"], df["Low"], df["Close"], length=14)
    df["atr"]     = atr_s

    df.dropna(inplace=True)
    if len(df) < 3:
        return None

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    entry = curr["Close"]
    atr   = curr["atr"]

    # Supertrend girato da BEAR a BULL (dir: da 1 a -1 in pandas_ta = bullish)
    # Nota: in pandas_ta SUPERTd = 1 quando bearish, -1 quando bullish
    turned_bull = prev["st_dir"] == 1  and curr["st_dir"] == -1
    turned_bear = prev["st_dir"] == -1 and curr["st_dir"] == 1

    if turned_bull and curr["Close"] > curr["ema200"]:
        sl   = curr["st_line"]
        risk = entry - sl
        tp   = entry + 2.0 * risk
        return {
            "strategia": "🛢️ BARILE CALDO",
            "asset":      "Petrolio WTI",
            "timeframe":  "4H (swing)",
            "direzione":  "LONG",
            "entry":      fmt(entry, 2),
            "sl":         fmt(sl, 2),
            "tp":         fmt(tp, 2),
            "rr":         "1:2",
            "note":       "Supertrend girato RIALZISTA | Prezzo sopra EMA200 | ⚠️ Verifica rollover future WTI"
        }

    if turned_bear and curr["Close"] < curr["ema200"]:
        sl   = curr["st_line"]
        risk = sl - entry
        tp   = entry - 2.0 * risk
        return {
            "strategia": "🔴 BARILE CALDO",
            "asset":      "Petrolio WTI",
            "timeframe":  "4H (swing)",
            "direzione":  "SHORT",
            "entry":      fmt(entry, 2),
            "sl":         fmt(sl, 2),
            "tp":         fmt(tp, 2),
            "rr":         "1:2",
            "note":       "Supertrend girato RIBASSISTA | Prezzo sotto EMA200 | ⚠️ Verifica rollover future WTI"
        }

    return None
