import os
import time
import requests
import pandas as pd

# === ENV VARIABLES ===
OANDA_ENV = os.getenv("OANDA_ENV", "practice")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
OANDA_TOKEN = os.getenv("OANDA_TOKEN")
INSTRUMENTS = os.getenv("INSTRUMENTS", "EUR_USD,GBP_USD,USD_JPY").split(",")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === API URL ===
OANDA_API_URL = (
    "https://api-fxpractice.oanda.com/v3"
    if OANDA_ENV == "practice"
    else "https://api-fxtrade.oanda.com/v3"
)
HEADERS = {"Authorization": f"Bearer {OANDA_TOKEN}"}

# === Utils ===
def log(msg):
    print(msg, flush=True)

def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})
        log(f"Telegram send status: {r.status_code}")
    except Exception as e:
        log(f"Telegram error: {e}")

def get_candles(pair, granularity="M5", count=20):
    url = f"{OANDA_API_URL}/instruments/{pair}/candles"
    params = {"granularity": granularity, "count": count, "price": "M"}
    r = requests.get(url, headers=HEADERS, params=params)
    if r.status_code != 200:
        log(f"[{pair}] HTTP {r.status_code}: {r.text}")
        return None
    data = r.json()
    if "candles" not in data:
        return None
    return pd.DataFrame([
        {
            "time": c["time"],
            "open": float(c["mid"]["o"]),
            "high": float(c["mid"]["h"]),
            "low":  float(c["mid"]["l"]),
            "close":float(c["mid"]["c"]),
        }
        for c in data["candles"] if c.get("complete")
    ])

# === ICT Confluence Checks ===
def liquidity_sweep(df):
    return df.iloc[-1]["high"] > max(df.iloc[-5:-1]["high"]) or \
           df.iloc[-1]["low"] < min(df.iloc[-5:-1]["low"])

def fair_value_gap(df):
    return abs(df.iloc[-2]["high"] - df.iloc[-4]["low"]) > 2 * (df.iloc[-2]["high"] - df.iloc[-2]["low"])

def smt_divergence(df1, df2):
    return (df1.iloc[-1]["high"] > df1.iloc[-2]["high"] and df2.iloc[-1]["high"] < df2.iloc[-2]["high"]) or \
           (df1.iloc[-1]["low"] < df1.iloc[-2]["low"] and df2.iloc[-1]["low"] > df2.iloc[-2]["low"])

def confluence_score(pair):
    df_m5  = get_candles(pair, "M5", 20)
    df_m15 = get_candles(pair, "M15", 20)
    df_h1  = get_candles(pair, "H1", 20)
    df_h4  = get_candles(pair, "H4", 20)
    if None in (df_m5, df_m15, df_h1, df_h4):
        return 0, "Data missing"
    score = 0
    notes = []
    if liquidity_sweep(df_m5):
        score += 1; notes.append("Liquidity Sweep (M5)")
    if fair_value_gap(df_m15):
        score += 1; notes.append("FVG (M15)")
    if liquidity_sweep(df_h1):
        score += 1; notes.append("Liquidity Sweep (H1)")
    if fair_value_gap(df_h4):
        score += 1; notes.append("FVG (H4)")
    # For SMT, compare EURUSD & GBPUSD if both in instruments
    if "EUR_USD" in INSTRUMENTS and "GBP_USD" in INSTRUMENTS and pair == "EUR_USD":
        df2 = get_candles("GBP_USD", "M15", 20)
        if df2 is not None and smt_divergence(df_m15, df2):
            score += 1; notes.append("SMT Divergence vs GBPUSD")
    return score, ", ".join(notes)

# === SL/TP Calculation ===
def suggest_sl_tp(df, risk_reward=2.0, direction="long"):
    if direction == "long":
        sl = min(df["low"].tail(5))
        tp = df.iloc[-1]["close"] + (df.iloc[-1]["close"] - sl) * risk_reward
    else:
        sl = max(df["high"].tail(5))
        tp = df.iloc[-1]["close"] - (sl - df.iloc[-1]["close"]) * risk_reward
    return sl, tp

# === STARTUP ===
log("🚀 Bot starting…")
send_telegram("🚀 ICT Bot started — scanning multi-timeframes.")

# === MAIN LOOP ===
while True:
    for pair in INSTRUMENTS:
        log(f"Scanning {pair}...")
        score, reasons = confluence_score(pair)
        log(f"[{pair}] Score={score} — {reasons}")
        if score >= 3 or (score == 2 and "strong" in reasons.lower()):
            df_m5 = get_candles(pair, "M5", 20)
            direction = "long" if "FVG" in reasons or "Liquidity Sweep" in reasons else "short"
            sl, tp = suggest_sl_tp(df_m5, 2.0, direction)
            alert = f"📊 ICT Setup on {pair}\nScore: {score}\nReasons: {reasons}\nSL: {sl}\nTP: {tp}"
            send_telegram(alert)
    time.sleep(60)  # run every minute
