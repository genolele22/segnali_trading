def get_data(ticker: str, period: str, interval: str) -> Optional[pd.DataFrame]:
    try:
        import yfinance as yf
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        ticker_obj = yf.Ticker(ticker, session=session)
        df = ticker_obj.history(period=period, interval=interval, auto_adjust=True)
        if df is None or len(df) < 30:
            logger.warning(f"Dati insufficienti per {ticker}")
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        return df.dropna()
    except Exception as e:
        logger.error(f"Errore download {ticker}: {e}")
        return None


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


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()

def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0).ewm(span=length, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(span=length, adjust=False).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(span=length, adjust=False).mean()

def bollinger(series: pd.Series, length: int = 20, std: float = 2.2):
    mid   = series.rolling(length).mean()
    sigma = series.rolling(length).std()
    return mid, mid + std * sigma, mid - std * sigma

def supertrend(df: pd.DataFrame, length: int = 10, multiplier: float = 3.0):
    atr_s  = atr(df, length)
    hl2    = (df["High"] + df["Low"]) / 2
    upper  = (hl2 + multiplier * atr_s).copy()
    lower  = (hl2 - multiplier * atr_s).copy()
    st     = pd.Series(index=df.index, dtype=float)
    trend  = pd.Series(index=df.index, dtype=int)

    for i in range(1, len(df)):
        prev_lower = lower.iloc[i-1]
        prev_upper = upper.iloc[i-1]
        prev_close = df["Close"].iloc[i-1]

        lower.iloc[i] = lower.iloc[i] if (lower.iloc[i] > prev_lower or prev_close < prev_lower) else prev_lower
        upper.iloc[i] = upper.iloc[i] if (upper.iloc[i] < prev_upper or prev_close > prev_upper) else prev_upper

        if df["Close"].iloc[i] > prev_upper:
            trend.iloc[i] = 1
        elif df["Close"].iloc[i] < prev_lower:
            trend.iloc[i] = -1
        else:
            trend.iloc[i] = trend.iloc[i-1] if i > 0 else 1

        st.iloc[i] = lower.iloc[i] if trend.iloc[i] == 1 else upper.iloc[i]

    return st, trend

def calc_vwap(df: pd.DataFrame) -> pd.Series:
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    typical    = (df["High"] + df["Low"] + df["Close"]) / 3
    df         = df.copy()
    df["_tp"]  = typical * df["Volume"]
    df["_date"]= df.index.date
    parts = []
    for d, g in df.groupby("_date"):
        parts.append(g["_tp"].cumsum() / g["Volume"].cumsum())
    return pd.concat(parts).reindex(df.index)

def resample_4h(df: pd.DataFrame) -> pd.DataFrame:
    return df.resample("4h").agg({
        "Open": "first", "High": "max",
        "Low": "min",    "Close": "last", "Volume": "sum"
    }).dropna()

def fmt(value, decimals=2) -> str:
    try:
        return f"{float(value):.{decimals}f}"
    except Exception:
        return str(value)


def check_surfista() -> Optional[dict]:
    df = get_data(TICKER_SP500, period="30d", interval="1h")
    if df is None or len(df) < 50:
        return None

    df["ema9"]  = ema(df["Close"], 9)
    df["ema21"] = ema(df["Close"], 21)
    df["rsi"]   = rsi(df["Close"], 14)
    df["atr"]   = atr(df, 14)
    df.dropna(inplace=True)
    if len(df) < 3:
        return None

    last_cet = df.index[-1].tz_convert(ROME_TZ)
    if not (time(15, 30) <= last_cet.time() <= time(21, 0)):
        logger.info("[Surfista] Fuori orario")
        return None

    prev, curr = df.iloc[-2], df.iloc[-1]
    cross_up   = prev["ema9"] <= prev["ema21"] and curr["ema9"] > curr["ema21"]
    cross_down = prev["ema9"] >= prev["ema21"] and curr["ema9"] < curr["ema21"]
    entry = curr["Close"]
    a     = curr["atr"]

    if cross_up and curr["rsi"] > 50:
        return {"strategia": "🟢 SURFISTA", "asset": "S&P 500", "timeframe": "1H",
                "direzione": "LONG",  "entry": fmt(entry),
                "sl": fmt(entry - 1.5*a), "tp": fmt(entry + 3.0*a),
                "rr": "1:2", "note": "EMA9 cross rialzista EMA21 | RSI > 50"}

    if cross_down and curr["rsi"] < 50:
        return {"strategia": "🔴 SURFISTA", "asset": "S&P 500", "timeframe": "1H",
                "direzione": "SHORT", "entry": fmt(entry),
                "sl": fmt(entry + 1.5*a), "tp": fmt(entry - 3.0*a),
                "rr": "1:2", "note": "EMA9 cross ribassista EMA21 | RSI < 50"}
    return None


def check_pendolo() -> Optional[dict]:
    df = get_data(TICKER_GOLD, period="30d", interval="1h")
    if df is None or len(df) < 50:
        return None

    df["rsi"]                               = rsi(df["Close"], 14)
    df["atr"]                               = atr(df, 14)
    df["bb_mid"], df["bb_up"], df["bb_low"] = bollinger(df["Close"], 20, 2.2)

    try:
        df["vwap"] = calc_vwap(df)
    except Exception:
        df["vwap"] = df["Close"].rolling(20).mean()

    df.dropna(inplace=True)
    if len(df) < 3:
        return None

    last_cet = df.index[-1].tz_convert(ROME_TZ)
    if not (time(8, 0) <= last_cet.time() <= time(18, 0)):
        logger.info("[Pendolo] Fuori orario")
        return None

    curr  = df.iloc[-1]
    entry = curr["Close"]
    a     = curr["atr"]

    if curr["Close"] < curr["bb_low"] and curr["rsi"] < 25 and curr["Close"] < curr["vwap"]:
        return {"strategia": "🟡 IL PENDOLO", "asset": "Oro (XAU/USD)", "timeframe": "1H",
                "direzione": "LONG",  "entry": fmt(entry),
                "sl": fmt(entry - 1.3*a), "tp": fmt(curr["bb_mid"]),
                "rr": "~1.5:1", "note": "Prezzo < BB Lower | RSI < 25 | Sotto VWAP"}

    if curr["Close"] > curr["bb_up"] and curr["rsi"] > 75 and curr["Close"] > curr["vwap"]:
        return {"strategia": "🔴 IL PENDOLO", "asset": "Oro (XAU/USD)", "timeframe": "1H",
                "direzione": "SHORT", "entry": fmt(entry),
                "sl": fmt(entry + 1.3*a), "tp": fmt(curr["bb_mid"]),
                "rr": "~1.5:1", "note": "Prezzo > BB Upper | RSI > 75 | Sopra VWAP"}
    return None


def check_rompighiaccio() -> Optional[dict]:
    df = get_data(TICKER_NASDAQ, period="5d", interval="15m")
    if df is None or len(df) < 20:
        return None

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert(ET_TZ)

    today_et = datetime.now(ET_TZ).date()
    today_df = df[df.index.date == today_et].copy()
    if len(today_df) < 3:
        return None

    session = today_df[today_df.index.time >= time(9, 30)].copy()
    if len(session) < 3:
        return None

    range_high = session.iloc[:2]["High"].max()
    range_low  = session.iloc[:2]["Low"].min()

    df["ema21"] = ema(df["Close"], 21)
    df["ema50"] = ema(df["Close"], 50)
    df["atr"]   = atr(df, 14)
    try:
        df["vwap"] = calc_vwap(df)
    except Exception:
        df["vwap"] = df["Close"].rolling(20).mean()
    df.dropna(inplace=True)

    curr_idx = df.index[-1]
    if curr_idx.date() != today_et:
        return None

    curr      = df.iloc[-1]
    curr_time = curr_idx.time()
    if not (time(9, 30) <= curr_time <= time(11, 30)):
        return None

    entry = curr["Close"]
    a     = curr["atr"]
    buf   = 0.3 * a

    if curr["Close"] > range_high + buf and curr["Close"] > curr["vwap"] and curr["ema21"] > curr["ema50"]:
        return {"strategia": "🔵 ROMPIGHIACCIO", "asset": "Nasdaq 100", "timeframe": "15min",
                "direzione": "LONG",  "entry": fmt(entry),
                "sl": fmt(entry - 1.5*a), "tp": fmt(entry + 3.0*a),
                "rr": "1:2", "note": f"Breakout H:{fmt(range_high)} | Sopra VWAP | ⚠️ Spread alto NAS100"}

    if curr["Close"] < range_low - buf and curr["Close"] < curr["vwap"] and curr["ema21"] < curr["ema50"]:
        return {"strategia": "🔴 ROMPIGHIACCIO", "asset": "Nasdaq 100", "timeframe": "15min",
                "direzione": "SHORT", "entry": fmt(entry),
                "sl": fmt(entry + 1.5*a), "tp": fmt(entry - 3.0*a),
                "rr": "1:2", "note": f"Breakout L:{fmt(range_low)} | Sotto VWAP | ⚠️ Spread alto NAS100"}
    return None


def check_barile_caldo() -> Optional[dict]:
    df_1h = get_data(TICKER_WTI, period="120d", interval="1h")
    if df_1h is None or len(df_1h) < 50:
        return None

    df = resample_4h(df_1h)
    if len(df) < 50:
        return None

    df["ema200"]           = ema(df["Close"], 200)
    df["atr"]              = atr(df, 14)
    df["st"], df["st_dir"] = supertrend(df, 10, 3.0)
    df.dropna(inplace=True)
    if len(df) < 3:
        return None

    prev, curr = df.iloc[-2], df.iloc[-1]
    entry = curr["Close"]

    turned_bull = prev["st_dir"] == -1 and curr["st_dir"] == 1
    turned_bear = prev["st_dir"] == 1  and curr["st_dir"] == -1

    if turned_bull and curr["Close"] > curr["ema200"]:
        sl   = curr["st"]
        risk = entry - sl
        return {"strategia": "🛢️ BARILE CALDO", "asset": "Petrolio WTI", "timeframe": "4H",
                "direzione": "LONG",  "entry": fmt(entry),
                "sl": fmt(sl), "tp": fmt(entry + 2.0*risk),
                "rr": "1:2", "note": "Supertrend BULL | Sopra EMA200 | ⚠️ Verifica rollover WTI"}

    if turned_bear and curr["Close"] < curr["ema200"]:
        sl   = curr["st"]
        risk = sl - entry
        return {"strategia": "🔴 BARILE CALDO", "asset": "Petrolio WTI", "timeframe": "4H",
                "direzione": "SHORT", "entry": fmt(entry),
                "sl": fmt(sl), "tp": fmt(entry - 2.0*risk),
                "rr": "1:2", "note": "Supertrend BEAR | Sotto EMA200 | ⚠️ Verifica rollover WTI"}
    return None
