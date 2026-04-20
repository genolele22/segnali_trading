# 🤖 Trading Bot — Revolut CFD Signal System

Bot di segnali semi-automatizzato per CFD Revolut.
Gira H24 su Railway (cloud gratuito). Tu ricevi gli alert su Telegram ed esegui manualmente su Revolut.

---

## ⚙️ Strategie incluse

| # | Nome | Asset | Timeframe | Logica | Orario CET |
|---|------|-------|-----------|--------|-----------|
| 1 | Surfista | S&P500 | 1H | Trend Following EMA | 15:30–21:00 |
| 2 | Il Pendolo | Oro | 1H | Mean Reversion BB+VWAP | 08:00–18:00 |
| 3 | Rompighiaccio | Nasdaq | 15min | Breakout apertura USA | 15:30–17:30 |
| 4 | Barile Caldo | WTI | 4H | Momentum Supertrend | Sempre |

---

## 🚀 Deploy su Railway — Istruzioni passo passo

### STEP 1 — Carica il codice su GitHub

1. Vai su [github.com](https://github.com) → **New repository**
2. Nome: `trading-bot` → **Create repository**
3. Carica tutti i file di questa cartella:
   - Clicca **"uploading an existing file"**
   - Trascina tutti i file (main.py, strategies.py, notifier.py, news_filter.py, requirements.txt, Procfile)
   - Clicca **"Commit changes"**

### STEP 2 — Crea account Railway

1. Vai su [railway.app](https://railway.app)
2. Clicca **"Start a New Project"**
3. Accedi con il tuo account **GitHub**

### STEP 3 — Crea il progetto su Railway

1. Clicca **"Deploy from GitHub repo"**
2. Seleziona il repository `trading-bot`
3. Railway inizia automaticamente il deploy

### STEP 4 — Aggiungi le variabili d'ambiente

1. Clicca sul tuo progetto → tab **"Variables"**
2. Aggiungi:
   - `TELEGRAM_TOKEN` = il token che ti ha dato BotFather
   - `CHAT_ID` = il tuo ID numerico (es. `412866123`)
3. Railway riavvia automaticamente il bot

### STEP 5 — Verifica che funzioni

1. Vai su tab **"Deployments"** → controlla che lo status sia verde
2. Dopo 30 secondi dovresti ricevere su Telegram il messaggio di avvio:
   > 🤖 Trading Bot — Avviato

Se non arriva, vai su **"Logs"** e dimmi cosa vedi.

---

## 💬 Formato dei segnali Telegram

Quando arriva un segnale, ricevi un messaggio così:

```
🟢 SURFISTA — LONG
━━━━━━━━━━━━━━━━━━
📊 Asset: S&P 500
⏱ Timeframe: 1H
🎯 Entry:       5120.50
🛑 Stop Loss:   5095.30
✅ Take Profit: 5170.90
📐 R:R: 1:2
━━━━━━━━━━━━━━━━━━
📝 EMA9 incrocia al rialzo EMA21 | RSI > 50

⚠️ Rischia max 1% del capitale
🕐 20/04/2026 16:05
```

---

## 📊 Come eseguire su Revolut

1. Ricevi notifica Telegram
2. Apri Revolut → Trading → cerca l'asset
3. Imposta:
   - **Direzione:** Long o Short
   - **Stop Loss:** il valore indicato
   - **Take Profit:** il valore indicato
   - **Size:** in base alla regola 1% (vedi sotto)
4. Conferma il trade

### Calcolo della size (regola 1%)

```
Rischio € = Capitale × 1%
Size = Rischio € / (Entry - Stop Loss)
```

**Esempio:** Capitale €1.000, Entry 5120, SL 5095 → Rischio €10 → Size = 10/25 = 0.4 contratti

---

## ⚠️ Regole fondamentali

- Mai rischiare più dell'1% del capitale per trade
- Dopo 3 stop loss consecutivi: stop per la giornata
- Controlla sempre [forexfactory.com](https://forexfactory.com) la mattina (notizie rosse)
- WTI: verifica la scadenza del future ogni mese (terzo venerdì)
- S&P500 e Nasdaq sono correlati — non aprire entrambi nella stessa direzione

---

## 🔧 Manutenzione

- Il bot gira in automatico H24 su Railway
- Railway free tier: 500 ore/mese (sufficiente per un bot worker)
- Se il bot si ferma: vai su Railway → "Restart"
- Per aggiornare il codice: modifica i file su GitHub → Railway si aggiorna automaticamente

---

*Non costituisce consulenza finanziaria. Il trading con leva comporta rischio di perdita del capitale.*
