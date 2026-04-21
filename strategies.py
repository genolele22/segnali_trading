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
