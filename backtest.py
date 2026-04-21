"""
BACKTEST — Simulazione storica delle 4 strategie
Esegui con: python3 backtest.py
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, time
import pytz

ROME_TZ = pytz.timezone("Europe/Rome")
ET_TZ   = pytz.timezone("America/New_York")

COSTS    = {"SP500": 2.0, "GOLD": 2.5, "NASDAQ": 4.0, "WTI": 4.0}
CAPITAL  = 1000.0
RISK_PCT = 0.01


# ── Helper ────────────────────────────────────────────────────────────────────
def get_data(ticker, period, interval):
    try:
        df = yf.download(ticker, period=period, interval=interval,
                         progress=False, auto_adjust=True)
        if df is None or len(df) < 30:
            print(f"  Dati insufficienti per {ticker}")
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        return df.dropna()
    except Exception as e:
        print(f"  Errore {ticker}: {e}")
        return None

def ema(s, n):   return s.ewm(span=n, adjust=False).mean()

def rsi(s, n=14):
    d = s.diff()
    g = d.clip(lower=0).ewm(span=n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(span=n, adjust=False).mean()
    return 100 - 100/(1 + g/l.replace(0, np.nan))

def atr_calc(df, n=14):
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([(h-l),(h-c.shift()).abs(),(l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()

def bollinger(s, n=20, std=2.2):
    mid = s.rolling(n).mean()
    sig = s.rolling(n).std()
    return mid, mid+std*sig, mid-std*sig

def supertrend(df, n=10, mult=3.0):
    a   = atr_calc(df, n)
    hl2 = (df["High"]+df["Low"])/2
    up  = (hl2 + mult*a).copy()
    dn  = (hl2 - mult*a).copy()
    trend = pd.Series(1, index=df.index)
    for i in range(1, len(df)):
        dn.iloc[i] = dn.iloc[i] if (dn.iloc[i]>dn.iloc[i-1] or df["Close"].iloc[i-1]<dn.iloc[i-1]) else dn.iloc[i-1]
        up.iloc[i] = up.iloc[i] if (up.iloc[i]<up.iloc[i-1] or df["Close"].iloc[i-1]>up.iloc[i-1]) else up.iloc[i-1]
        if   df["Close"].iloc[i] > up.iloc[i-1]: trend.iloc[i] = 1
        elif df["Close"].iloc[i] < dn.iloc[i-1]: trend.iloc[i] = -1
        else:                                     trend.iloc[i] = trend.iloc[i-1]
    st = pd.Series(np.where(trend==1, dn, up), index=df.index)
    return st, trend

def calc_vwap(df):
    typ = (df["High"]+df["Low"]+df["Close"])/3
    df  = df.copy()
    df["_tp"] = typ * df["Volume"]
    df["_d"]  = df.index.date
    parts = []
    for d, g in df.groupby("_d"):
        parts.append(g["_tp"].cumsum()/g["Volume"].cumsum())
    return pd.concat(parts).reindex(df.index)

def resample_4h(df):
    return df.resample("4h").agg({"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}).dropna()


# ── Simulatore ────────────────────────────────────────────────────────────────
def simulate(signals_df, cost_eur, label):
    capital = CAPITAL
    trades  = []
    for _, row in signals_df.iterrows():
        entry, sl, tp, d = row["entry"], row["sl"], row["tp"], row["direction"]
        dist_sl = abs(entry - sl)
        if dist_sl == 0: continue
        risk_eur   = capital * RISK_PCT
        next_close = row.get("next_close", entry)
        if d == 1:
            hit_tp = next_close >= tp
            hit_sl = next_close <= sl
        else:
            hit_tp = next_close <= tp
            hit_sl = next_close >= sl
        if hit_tp:
            pnl_pts = abs(tp - entry);   outcome = "WIN"
        elif hit_sl:
            pnl_pts = -abs(entry - sl);  outcome = "LOSS"
        else:
            pnl_pts = (next_close - entry)*d; outcome = "OPEN"
        size    = risk_eur / dist_sl
        pnl_eur = pnl_pts * size - cost_eur
        capital += pnl_eur
        trades.append({"dir":"LONG" if d==1 else "SHORT","outcome":outcome,
                       "pnl_eur":pnl_eur,"capital":capital})
    if not trades: return None
    df_t    = pd.DataFrame(trades)
    wins    = df_t[df_t["outcome"]=="WIN"]
    losses  = df_t[df_t["outcome"]=="LOSS"]
    win_rate= len(wins)/len(df_t)*100
    gross_p = wins["pnl_eur"].sum()   if len(wins)>0  else 0
    gross_l = abs(losses["pnl_eur"].sum()) if len(losses)>0 else 0.01
    pf      = gross_p/gross_l
    peak    = df_t["capital"].cummax()
    max_dd  = ((df_t["capital"]-peak)/peak*100).min()
    ret     = (capital-CAPITAL)/CAPITAL*100
    return {"label":label,"trades":len(df_t),"win_rate":win_rate,
            "pf":pf,"max_dd":max_dd,"return":ret,"final_cap":capital}


# ── Strategie ─────────────────────────────────────────────────────────────────
def backtest_surfista():
    print("⏳ Backtest SURFISTA (S&P500 1H)...")
    df = get_data("^GSPC", "2y", "1h")
    if df is None: return None
    df["ema9"]=ema(df["Close"],9); df["ema21"]=ema(df["Close"],21)
    df["rsi"]=rsi(df["Close"],14); df["atr"]=atr_calc(df,14)
    df.dropna(inplace=True)
    signals=[]
    for i in range(1,len(df)-1):
        row,prev,nxt = df.iloc[i],df.iloc[i-1],df.iloc[i+1]
        h = row.name.tz_convert(ROME_TZ).hour
        if not(15<=h<=21): continue
        cu = prev["ema9"]<=prev["ema21"] and row["ema9"]>row["ema21"]
        cd = prev["ema9"]>=prev["ema21"] and row["ema9"]<row["ema21"]
        if cu and row["rsi"]>50:
            signals.append({"entry":row["Close"],"sl":row["Close"]-1.5*row["atr"],
                            "tp":row["Close"]+3.0*row["atr"],"direction":1,"next_close":nxt["Close"]})
        elif cd and row["rsi"]<50:
            signals.append({"entry":row["Close"],"sl":row["Close"]+1.5*row["atr"],
                            "tp":row["Close"]-3.0*row["atr"],"direction":-1,"next_close":nxt["Close"]})
    if not signals: return None
    return simulate(pd.DataFrame(signals), COSTS["SP500"], "🟢 SURFISTA (S&P500 1H)")


def backtest_pendolo():
    print("⏳ Backtest IL PENDOLO (Oro 1H)...")
    df = get_data("GC=F", "2y", "1h")
    if df is None: return None
    df["rsi"]=rsi(df["Close"],14); df["atr"]=atr_calc(df,14)
    df["bb_mid"],df["bb_up"],df["bb_low"]=bollinger(df["Close"],20,2.2)
    try:    df["vwap"]=calc_vwap(df)
    except: df["vwap"]=df["Close"].rolling(20).mean()
    df.dropna(inplace=True)
    signals=[]
    for i in range(len(df)-1):
        row,nxt = df.iloc[i],df.iloc[i+1]
        h = row.name.tz_convert(ROME_TZ).hour
        if not(8<=h<=18): continue
        if row["Close"]<row["bb_low"] and row["rsi"]<25 and row["Close"]<row["vwap"]:
            signals.append({"entry":row["Close"],"sl":row["Close"]-1.3*row["atr"],
                            "tp":row["bb_mid"],"direction":1,"next_close":nxt["Close"]})
        elif row["Close"]>row["bb_up"] and row["rsi"]>75 and row["Close"]>row["vwap"]:
            signals.append({"entry":row["Close"],"sl":row["Close"]+1.3*row["atr"],
                            "tp":row["bb_mid"],"direction":-1,"next_close":nxt["Close"]})
    if not signals: return None
    return simulate(pd.DataFrame(signals), COSTS["GOLD"], "🟡 IL PENDOLO (Oro 1H)")


def backtest_rompighiaccio():
    print("⏳ Backtest ROMPIGHIACCIO (Nasdaq 15min)...")
    df = get_data("^NDX", "1y", "15m")
    if df is None: return None
    if df.index.tz is None: df.index=df.index.tz_localize("UTC")
    df.index=df.index.tz_convert(ET_TZ)
    df["ema21"]=ema(df["Close"],21); df["ema50"]=ema(df["Close"],50)
    df["atr"]=atr_calc(df,14)
    try:    df["vwap"]=calc_vwap(df)
    except: df["vwap"]=df["Close"].rolling(20).mean()
    df.dropna(inplace=True)
    signals=[]
    for d in sorted(set(df.index.date)):
        day_df=df[df.index.date==d]
        sess=day_df[day_df.index.time>=time(9,30)]
        if len(sess)<4: continue
        rh=sess.iloc[:2]["High"].max(); rl=sess.iloc[:2]["Low"].min()
        for i in range(2,len(sess)-1):
            row,nxt=sess.iloc[i],sess.iloc[i+1]
            if not(time(9,30)<=row.name.time()<=time(11,30)): continue
            a=row["atr"]; buf=0.3*a
            if row["Close"]>rh+buf and row["Close"]>row["vwap"] and row["ema21"]>row["ema50"]:
                signals.append({"entry":row["Close"],"sl":row["Close"]-1.5*a,
                                "tp":row["Close"]+3.0*a,"direction":1,"next_close":nxt["Close"]}); break
            elif row["Close"]<rl-buf and row["Close"]<row["vwap"] and row["ema21"]<row["ema50"]:
                signals.append({"entry":row["Close"],"sl":row["Close"]+1.5*a,
                                "tp":row["Close"]-3.0*a,"direction":-1,"next_close":nxt["Close"]}); break
    if not signals: return None
    return simulate(pd.DataFrame(signals), COSTS["NASDAQ"], "🔵 ROMPIGHIACCIO (Nasdaq 15min)")


def backtest_barile_caldo():
    print("⏳ Backtest BARILE CALDO (WTI 4H)...")
    df_1h=get_data("CL=F","2y","1h")
    if df_1h is None: return None
    df=resample_4h(df_1h)
    if len(df)<50: return None
    df["ema200"]=ema(df["Close"],200); df["atr"]=atr_calc(df,14)
    df["st"],df["st_dir"]=supertrend(df,10,3.0)
    df.dropna(inplace=True)
    signals=[]
    for i in range(1,len(df)-1):
        prev,row,nxt=df.iloc[i-1],df.iloc[i],df.iloc[i+1]
        tb=prev["st_dir"]==-1 and row["st_dir"]==1
        ts=prev["st_dir"]==1  and row["st_dir"]==-1
        if tb and row["Close"]>row["ema200"]:
            sl=row["st"]; risk=row["Close"]-sl
            if risk<=0: continue
            signals.append({"entry":row["Close"],"sl":sl,"tp":row["Close"]+2.0*risk,
                            "direction":1,"next_close":nxt["Close"]})
        elif ts and row["Close"]<row["ema200"]:
            sl=row["st"]; risk=sl-row["Close"]
            if risk<=0: continue
            signals.append({"entry":row["Close"],"sl":sl,"tp":row["Close"]-2.0*risk,
                            "direction":-1,"next_close":nxt["Close"]})
    if not signals: return None
    return simulate(pd.DataFrame(signals), COSTS["WTI"], "🛢️ BARILE CALDO (WTI 4H)")


# ── Output ────────────────────────────────────────────────────────────────────
def print_results(results):
    print("\n"+"═"*65)
    print(f"  RISULTATI BACKTEST — Capitale iniziale: €{CAPITAL:.0f}")
    print("═"*65)
    print(f"{'Strategia':<28} {'Trade':>6} {'Win%':>6} {'PF':>6} {'MaxDD':>7} {'Rend%':>7} {'Cap.€':>8}")
    print("─"*65)
    for r in results:
        if r is None: continue
        print(f"{r['label']:<28} {r['trades']:>6} {r['win_rate']:>5.1f}% "
              f"{r['pf']:>6.2f} {r['max_dd']:>6.1f}% {r['return']:>6.1f}% "
              f"{r['final_cap']:>8.0f}€")
    print("─"*65)
    print("\nLegenda:")
    print("  PF    = Profit Factor (>1.3 ok, >1.5 buono)")
    print("  MaxDD = Drawdown massimo % (meglio sopra -25%)")
    print("  Rend% = Rendimento totale sul periodo testato")
    print("\n⚠️  Spread+slippage Revolut inclusi nei calcoli.")
    print("⚠️  Fai sempre paper trading prima del denaro reale.\n")


if __name__ == "__main__":
    print("🔍 Avvio backtest su dati storici reali...")
    print("   (può richiedere 2-5 minuti)\n")
    results = [backtest_surfista(), backtest_pendolo(),
               backtest_rompighiaccio(), backtest_barile_caldo()]
    print_results([r for r in results if r is not None])
