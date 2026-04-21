"""
STRATEGIE DI TRADING — 5 strategie profittevoli
1. VWAP Reversal Oro 15min        (PF 1.84) — intraday
2. London Liquidity Sweep Oro     (PF 1.55) — intraday
3. ORB S&P500 15min               (PF 1.40) — intraday
4. Kumo Rider Oro 4H              (PF 1.62) — swing overnight OK
5. Kumo Rider Nasdaq 1H           (PF 1.51) — swing overnight OK
"""

import logging
from datetime import datetime, time
from typing import Optional

import numpy as np
import pandas as pd
import requests
import yfinance as yf
import pytz

logger = logging.getLogger(__name__)

ROME_TZ = pytz.timezone("Europe/Rome")
ET_TZ   = pytz.timezone("America/New_York")

TICKER_GOLD   = "GC=F"
TICKER_SP500  = "^GSPC"
TICKER_NASDAQ = "^NDX"


# ── Download dati ─────────────────────────────────────────────────────────────
def get_data(ticker: str, period: str, interval: str) -> Optional[pd.DataFrame]:
    try:
        t  = yf.Ticker(ticker)
        df = t.history(period=period, interval=interval, auto_adjust=True)
        if df is None or len(df) < 30:
            logger.warning(f"Dati insufficienti per {ticker}")
            return None
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        df.index = df.index.tz_convert(ROME_TZ)
        return df.dropna()
    except Exception as e:
        logger.error(f"Errore download {ticker}: {e}")
        return None


# ── Indicatori ────────────────────────────────────────────────────────────────
def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    g = d.clip(lower=0).ewm(span=n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(span=n, adjust=False).mean()
    return 100 - 100 / (1 + g / l.replace(0, np.nan))

def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()

def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()

def calc_vwap_bands(df: pd.DataFrame):
    """VWAP con bande ±2σ, reset giornaliero."""
    df = df.copy()
    df["_d"] = df.index.date
    vwap_s, b2u_s, b2d_s = [], [], []
    for d, g in df.groupby("_d"):
        tp  = (g["High"] + g["Low"] + g["Close"]) / 3
        v   = (tp * g["Volume"]).cumsum() / g["Volume"].cumsum()
        var = ((tp - v) ** 2 * g["Volume"]).cumsum() / g["Volume"].cumsum()
        std = np.sqrt(var)
        vwap_s.append(v)
        b2u_s.append(v + 2 * std)
        b2d_s.append(v - 2 * std)
    vwap = pd.concat(vwap_s).reindex(df.index)
    b2u  = pd.concat(b2u_s).reindex(df.index)
    b2d  = pd.concat(b2d_s).reindex(df.index)
    return vwap, b2u, b2d

def ichimoku(df: pd.DataFrame, tenkan=9, kijun=26, senkou_b=52, disp=26):
    h, l = df["High"], df["Low"]
    t_sen = (h.rolling(tenkan).max()    + l.rolling(tenkan).min())    / 2
    k_sen = (h.rolling(kijun).max()     + l.rolling(kijun).min())     / 2
    s_a   = ((t_sen + k_sen) / 2).shift(disp)
    s_b   = ((h.rolling(senkou_b).max() + l.rolling(senkou_b).min()) / 2).shift(disp)
    chikou = df["Close"].shift(-disp)
    return t_sen, k_sen, s_a, s_b, chikou

def resample_4h(df: pd.DataFrame) -> pd.DataFrame:
    return df.resample("4h").agg({
        "Open": "first", "High": "max",
        "Low":  "min",   "Close": "last", "Volume": "sum"
    }).dropna()

def fmt(value, decimals: int = 2) -> str:
    try:
        return f"{float(value):.{decimals}f}"
    except Exception:
        return str(value)


# ══════════════════════════════════════════════════════════════════════════════
# STRATEGIA 1 — VWAP REVERSAL ORO 15min  (PF 1.84)
# Intraday — chiusura entro 21:45 CET
# Prezzo esteso oltre +2σ/−2σ VWAP + RSI estremo + candela di inversione
# ══════════════════════════════════════════════════════════════════════════════
def check_vwap_reversal_gold() -> Optional[dict]:
    df = get_data(TICKER_GOLD, period="5d", interval="15m")
    if df is None or len(df) < 40:
        return None

    df["rsi14"]        = rsi(df["Close"], 14)
    df["atr14"]        = atr(df, 14)
    df["vwap"], df["vb2u"], df["vb2d"] = calc_vwap_bands(df)
    df.dropna(inplace=True)
    if len(df) < 3:
        return None

    last_cet = df.index[-1].tz_convert(ROME_TZ)
    if not (time(8, 0) <= last_cet.time() <= time(21, 45)):
        return None

    curr = df.iloc[-1]
    prev = df.iloc[-2]
    entry = curr["Close"]
    a     = curr["atr14"]

    # LONG: prezzo sotto -2σ + RSI < 35 + candela verde
    if (entry < curr["vb2d"] and curr["rsi14"] < 35 and
            curr["Close"] > prev["Close"]):
        sl = entry - 1.2 * a
        tp = curr["vwap"]
        if (tp - entry) < 1.5 * (entry - sl):
            return None
        return {
            "strategia": "🟡 VWAP REVERSAL ORO",
            "asset":     "Oro (XAU/USD)",
            "timeframe": "15min",
            "direzione": "LONG",
            "entry":     fmt(entry),
            "sl":        fmt(sl),
            "tp":        fmt(tp),
            "rr":        "~1.8:1",
            "note":      f"Prezzo sotto VWAP -2σ | RSI {curr['rsi14']:.0f} | Rimbalzo iniziato | Chiudi entro 21:45"
        }

    # SHORT: prezzo sopra +2σ + RSI > 65 + candela rossa
    if (entry > curr["vb2u"] and curr["rsi14"] > 65 and
            curr["Close"] < prev["Close"]):
        sl = entry + 1.2 * a
        tp = curr["vwap"]
        if (entry - tp) < 1.5 * (sl - entry):
            return None
        return {
            "strategia": "🔴 VWAP REVERSAL ORO",
            "asset":     "Oro (XAU/USD)",
            "timeframe": "15min",
            "direzione": "SHORT",
            "entry":     fmt(entry),
            "sl":        fmt(sl),
            "tp":        fmt(tp),
            "rr":        "~1.8:1",
            "note":      f"Prezzo sopra VWAP +2σ | RSI {curr['rsi14']:.0f} | Inversione | Chiudi entro 21:45"
        }

    return None


# ══════════════════════════════════════════════════════════════════════════════
# STRATEGIA 2 — LONDON LIQUIDITY SWEEP ORO  (PF 1.55)
# Intraday — finestra 08:00-10:00 CET
# Falso breakdown del range asiatico 06:00-08:00 → entrata LONG
# ══════════════════════════════════════════════════════════════════════════════
def check_london_sweep_gold() -> Optional[dict]:
    df = get_data(TICKER_GOLD, period="3d", interval="15m")
    if df is None or len(df) < 20:
        return None

    df["sma20"] = sma(df["Close"], 20)
    df["atr14"] = atr(df, 14)
    df.dropna(inplace=True)

    now_cet = datetime.now(ROME_TZ)
    if not (time(8, 0) <= now_cet.time() <= time(10, 0)):
        return None

    today = now_cet.date()
    today_df = df[df.index.date == today]

    # Range asiatico 06:00-08:00 CET
    asia = today_df[(today_df.index.time >= time(6, 0)) &
                    (today_df.index.time < time(8, 0))]
    if len(asia) < 3:
        return None

    asia_low  = asia["Low"].min()
    asia_high = asia["High"].max()

    # Ultime 2 candele nella finestra operativa
    window = today_df[(today_df.index.time >= time(8, 0)) &
                      (today_df.index.time <= now_cet.time())]
    if len(window) < 2:
        return None

    curr = window.iloc[-1]
    a    = curr["atr14"]

    # Sweep: candela corrente ha toccato sotto asia_low di $2-$5
    sweep_depth = asia_low - curr["Low"]
    if not (2.0 <= sweep_depth <= 5.0):
        return None

    # Reclaim: chiude sopra asia_low
    if curr["Close"] <= asia_low:
        return None

    # SMA20 piatta o in discesa (trapped shorts)
    sma_slope = df["sma20"].iloc[-1] - df["sma20"].iloc[-4]
    if sma_slope > 0.5:
        return None

    entry = curr["Close"]
    sl    = curr["Low"] - 3.0
    tp    = asia_high
    risk  = entry - sl

    if risk <= 0 or risk > 15:
        return None

    return {
        "strategia": "🟡 LONDON SWEEP ORO",
        "asset":     "Oro (XAU/USD)",
        "timeframe": "15min",
        "direzione": "LONG",
        "entry":     fmt(entry),
        "sl":        fmt(sl),
        "tp":        fmt(tp),
        "rr":        f"1:{(tp-entry)/risk:.1f}",
        "note":      f"Sweep ${sweep_depth:.2f} sotto range asiatico | Reclaim | TP1=50% a {fmt(tp)} | Trailing $4 dopo TP1"
    }


# ══════════════════════════════════════════════════════════════════════════════
# STRATEGIA 3 — ORB S&P500 15min  (PF 1.40)
# Intraday — OR = prima candela 15:30, trading 15:45-21:45 CET
# ══════════════════════════════════════════════════════════════════════════════
def check_orb_sp500() -> Optional[dict]:
    df = get_data(TICKER_SP500, period="5d", interval="15m")
    if df is None or len(df) < 40:
        return None

    df["atr14"] = atr(df, 14)
    df["rsi14"] = rsi(df["Close"], 14)
    df["ema20"] = ema(df["Close"], 20)

    # VWAP giornaliero
    df_copy = df.copy()
    df_copy["_d"] = df_copy.index.date
    parts = []
    for d, g in df_copy.groupby("_d"):
        tp = (g["High"] + g["Low"] + g["Close"]) / 3
        parts.append((tp * g["Volume"]).cumsum() / g["Volume"].cumsum())
    df["vwap"] = pd.concat(parts).reindex(df.index)
    df.dropna(inplace=True)

    now_cet = datetime.now(ROME_TZ)
    if not (time(15, 45) <= now_cet.time() <= time(21, 45)):
        return None

    today = now_cet.date()
    today_df = df[df.index.date == today]

    # Opening Range: prima candela 15:30
    or_bar = today_df[today_df.index.time == time(15, 30)]
    if len(or_bar) == 0:
        return None

    or_high = or_bar["High"].iloc[0]
    or_low  = or_bar["Low"].iloc[0]
    or_range = or_high - or_low

    # Salta se OR troppo ampio
    atr_day = today_df["atr14"].mean()
    if or_range > 2.5 * atr_day:
        return None

    curr = df.iloc[-1]
    prev = df.iloc[-2]
    entry = curr["Close"]
    a     = curr["atr14"]

    # LONG: breakout sopra OR high + sopra VWAP + EMA20 crescente + RSI > 52
    if (entry > or_high + 0.1 * a and
            entry > curr["vwap"] and
            curr["ema20"] > prev["ema20"] and
            curr["rsi14"] > 52):
        sl   = max(or_low, entry - 2.0 * a)
        risk = entry - sl
        if risk <= 0:
            return None
        tp1 = entry + 1.5 * risk
        tp2 = entry + 2.5 * risk
        return {
            "strategia": "🟢 ORB S&P500",
            "asset":     "S&P 500",
            "timeframe": "15min",
            "direzione": "LONG",
            "entry":     fmt(entry),
            "sl":        fmt(sl),
            "tp":        fmt(tp2),
            "rr":        "1:2.5",
            "note":      f"Breakout OR high {fmt(or_high)} | Sopra VWAP | TP1 {fmt(tp1)} → sposta SL a BE | Chiudi entro 21:45"
        }

    # SHORT: breakout sotto OR low + sotto VWAP + EMA20 decrescente + RSI < 48
    if (entry < or_low - 0.1 * a and
            entry < curr["vwap"] and
            curr["ema20"] < prev["ema20"] and
            curr["rsi14"] < 48):
        sl   = min(or_high, entry + 2.0 * a)
        risk = sl - entry
        if risk <= 0:
            return None
        tp1 = entry - 1.5 * risk
        tp2 = entry - 2.5 * risk
        return {
            "strategia": "🔴 ORB S&P500",
            "asset":     "S&P 500",
            "timeframe": "15min",
            "direzione": "SHORT",
            "entry":     fmt(entry),
            "sl":        fmt(sl),
            "tp":        fmt(tp2),
            "rr":        "1:2.5",
            "note":      f"Breakout sotto OR low {fmt(or_low)} | Sotto VWAP | TP1 {fmt(tp1)} → sposta SL a BE | Chiudi entro 21:45"
        }

    return None


# ══════════════════════════════════════════════════════════════════════════════
# STRATEGIA 4 — KUMO RIDER ORO 4H  (PF 1.62)
# Swing — overnight OK se segnale forte
# Ichimoku 9/26/52 + RSI 40-65
# ══════════════════════════════════════════════════════════════════════════════
def check_kumo_gold_4h() -> Optional[dict]:
    df_1h = get_data(TICKER_GOLD, period="2y", interval="1h")
    if df_1h is None or len(df_1h) < 100:
        return None

    df = resample_4h(df_1h)
    if len(df) < 60:
        return None

    t_sen, k_sen, s_a, s_b, chikou = ichimoku(df)
    df["t_sen"]  = t_sen
    df["k_sen"]  = k_sen
    df["s_a"]    = s_a
    df["s_b"]    = s_b
    df["chikou"] = chikou
    df["rsi14"]  = rsi(df["Close"], 14)
    df["atr14"]  = atr(df, 14)
    df.dropna(inplace=True)

    if len(df) < 3:
        return None

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    kumo_top = max(curr["s_a"], curr["s_b"])
    kumo_bot = min(curr["s_a"], curr["s_b"])

    cross_up = prev["t_sen"] <= prev["k_sen"] and curr["t_sen"] > curr["k_sen"]
    cross_dn = prev["t_sen"] >= prev["k_sen"] and curr["t_sen"] < curr["k_sen"]

    entry       = curr["Close"]
    a           = curr["atr14"]
    chikou_ref  = df["Close"].iloc[-27] if len(df) > 27 else df["Close"].iloc[0]

    if (cross_up and entry > kumo_top and
            40 < curr["rsi14"] < 65 and
            curr["chikou"] > chikou_ref and
            curr["t_sen"] > curr["s_a"] and curr["t_sen"] > curr["s_b"]):
        sl   = curr["k_sen"] - 0.3 * a
        risk = entry - sl
        if risk <= 0:
            return None
        return {
            "strategia": "🟡 KUMO RIDER ORO 4H",
            "asset":     "Oro (XAU/USD)",
            "timeframe": "4H (swing)",
            "direzione": "LONG",
            "entry":     fmt(entry),
            "sl":        fmt(sl),
            "tp":        fmt(entry + 2.0 * risk),
            "rr":        "1:2",
            "note":      f"Tenkan cross Kijun | Sopra nuvola | RSI {curr['rsi14']:.0f} | ⚠️ Overnight OK se R:R ≥ 1.5 già raggiunto"
        }

    if (cross_dn and entry < kumo_bot and
            35 < curr["rsi14"] < 60 and
            curr["chikou"] < chikou_ref and
            curr["t_sen"] < curr["s_a"] and curr["t_sen"] < curr["s_b"]):
        sl   = curr["k_sen"] + 0.3 * a
        risk = sl - entry
        if risk <= 0:
            return None
        return {
            "strategia": "🔴 KUMO RIDER ORO 4H",
            "asset":     "Oro (XAU/USD)",
            "timeframe": "4H (swing)",
            "direzione": "SHORT",
            "entry":     fmt(entry),
            "sl":        fmt(sl),
            "tp":        fmt(entry - 2.0 * risk),
            "rr":        "1:2",
            "note":      f"Tenkan cross Kijun al ribasso | Sotto nuvola | RSI {curr['rsi14']:.0f} | ⚠️ Overnight OK se R:R ≥ 1.5"
        }

    return None


# ══════════════════════════════════════════════════════════════════════════════
# STRATEGIA 5 — KUMO RIDER NASDAQ 1H  (PF 1.51)
# Swing — overnight OK se segnale forte
# Ichimoku 9/26/52 + RSI 40-65 + filtro orario 15:30-21:00
# ══════════════════════════════════════════════════════════════════════════════
def check_kumo_nasdaq_1h() -> Optional[dict]:
    df = get_data(TICKER_NASDAQ, period="2y", interval="1h")
    if df is None or len(df) < 60:
        return None

    t_sen, k_sen, s_a, s_b, chikou = ichimoku(df)
    df["t_sen"]  = t_sen
    df["k_sen"]  = k_sen
    df["s_a"]    = s_a
    df["s_b"]    = s_b
    df["chikou"] = chikou
    df["rsi14"]  = rsi(df["Close"], 14)
    df["atr14"]  = atr(df, 14)
    df.dropna(inplace=True)

    if len(df) < 3:
        return None

    last_cet = df.index[-1].tz_convert(ROME_TZ)
    if not (time(15, 30) <= last_cet.time() <= time(21, 0)):
        return None

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    kumo_top = max(curr["s_a"], curr["s_b"])
    kumo_bot = min(curr["s_a"], curr["s_b"])

    cross_up = prev["t_sen"] <= prev["k_sen"] and curr["t_sen"] > curr["k_sen"]
    cross_dn = prev["t_sen"] >= prev["k_sen"] and curr["t_sen"] < curr["k_sen"]

    entry      = curr["Close"]
    a          = curr["atr14"]
    chikou_ref = df["Close"].iloc[-27] if len(df) > 27 else df["Close"].iloc[0]

    if (cross_up and entry > kumo_top and
            40 < curr["rsi14"] < 65 and
            curr["chikou"] > chikou_ref and
            curr["t_sen"] > curr["s_a"] and curr["t_sen"] > curr["s_b"]):
        sl   = curr["k_sen"] - 0.3 * a
        risk = entry - sl
        if risk <= 0:
            return None
        return {
            "strategia": "🔵 KUMO RIDER NASDAQ 1H",
            "asset":     "Nasdaq 100",
            "timeframe": "1H (swing)",
            "direzione": "LONG",
            "entry":     fmt(entry),
            "sl":        fmt(sl),
            "tp":        fmt(entry + 2.0 * risk),
            "rr":        "1:2",
            "note":      f"Tenkan cross Kijun | Sopra nuvola | RSI {curr['rsi14']:.0f} | ⚠️ Overnight OK se R:R ≥ 1.5"
        }

    if (cross_dn and entry < kumo_bot and
            35 < curr["rsi14"] < 60 and
            curr["chikou"] < chikou_ref and
            curr["t_sen"] < curr["s_a"] and curr["t_sen"] < curr["s_b"]):
        sl   = curr["k_sen"] + 0.3 * a
        risk = sl - entry
        if risk <= 0:
            return None
        return {
            "strategia": "🔴 KUMO RIDER NASDAQ 1H",
            "asset":     "Nasdaq 100",
            "timeframe": "1H (swing)",
            "direzione": "SHORT",
            "entry":     fmt(entry),
            "sl":        fmt(sl),
            "tp":        fmt(entry - 2.0 * risk),
            "rr":        "1:2",
            "note":      f"Tenkan cross Kijun al ribasso | Sotto nuvola | RSI {curr['rsi14']:.0f} | ⚠️ Overnight OK se R:R ≥ 1.5"
        }

    return None
