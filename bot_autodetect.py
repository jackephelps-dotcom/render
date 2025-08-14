# bot_autodetect.py
import requests
import pandas as pd
import time
from datetime import datetime
from ict_strategy import ICTStrategy

# ====== CONFIG ======
OANDA_ENV = "practice"
OANDA_ACCOUNT_ID = "YOUR_OANDA_ACCOUNT_ID"
OANDA_TOKEN = "YOUR_OANDA_API_TOKEN"
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"

OANDA_API_URL = f"https://api-fxpractice.oanda.com/v3"
HEADERS = {"Authorization": f"Bearer {OANDA_TOKEN}"}

PAIRS = [
    "EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF", "AUD_USD", "NZD_USD"
]

CORRELATIONS = {
    "EUR_USD": "GBP_USD",
    "GBP_USD": "EUR_USD",
    "USD_JPY": "USD_CHF",
    "USD_CHF": "USD_JPY",
    "AUD_USD": "NZD_USD",
    "NZD_USD": "AUD_USD"
}

TIMEZONE_OFFSET = 10  # Sydney is UTC+10 (or +11 in DST)
CHECK_INTERVAL = 60  # seconds

# ====== FUNCTIONS ======
def get_candles(pair, granularity, count=50):
    url = f"{OANDA_API_URL}/instruments/{pair}/candles"
    params = {
        "granularity": granularity,
        "count": count,
        "price": "M"
    }
    r = requests.get(url, headers=HEADERS, params=params)
    data = r.json()
    if "candles" not in data:
        return None
    df = pd.DataFrame([{
        "time": c["time"],
        "open": float(c["mid"]["o"]),
        "high": float(c["mid"]["h"]),
        "low": float(c["mid"]["l"]),
        "close": float(c["mid"]["c"])
    } for c in data["candles"] if c["complete"]])
    return df

def send_telegram_message(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    requests.post(url, json=payload)

def in_session():
    now = datetime.utcnow().hour + TIMEZONE_OFFSET
    now = now % 24
    # London session: 17–2 Sydney, New York: 22–7 Sydney
    return (17 <= now <= 23) or (0 <= now <= 7)

# ====== MAIN LOOP ======
def main():
    strategy = ICTStrategy()
    send_telegram_message("✅ ICT Forex Scanner is LIVE and monitoring markets...")

    while True:
        if in_session():
            for pair in PAIRS:
                try:
                    h4 = get_candles(pair, "H4")
                    h1 = get_candles(pair, "H1")
                    m15 = get_candles(pair, "M15")
                    m5 = get_candles(pair, "M5")

                    if None in (h4, h1, m15, m5):
                        continue

                    correlated_df = get_candles(CORRELATIONS[pair], "M5")

                    result = strategy.analyze(pair, h4, h1, m15, m5, correlated_df)
                    if result:
                        msg = f"""
{result['strength']} ICT Setup
Pair: {result['pair']}
Bias: {result['bias']}
Score: {result['score']}
Confluences:
 - {'\n - '.join(result['confluences'])}
Stop Loss: {result['sl']:.5f}
Take Profit: {result['tp']:.5f}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                        """
                        send_telegram_message(msg.strip())

                except Exception as e:
                    send_telegram_message(f"❌ Error scanning {pair}: {str(e)}")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
