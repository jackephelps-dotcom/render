import os
import requests
import time

# ENV vars
env = os.getenv("OANDA_ENV", "practice").lower()
token = os.getenv("OANDA_TOKEN", "").strip()
account_id = os.getenv("OANDA_ACCOUNT_ID", "").strip()
telegram_token = os.getenv("TELEGRAM_TOKEN", "").strip()
telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Host
host = "https://api-fxpractice.oanda.com" if env == "practice" else "https://api-fxtrade.oanda.com"
headers = {"Authorization": f"Bearer {token}"}

# ===== Helper Functions =====
def send_telegram(message):
    if not telegram_token or not telegram_chat_id:
        return
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    requests.post(url, json={"chat_id": telegram_chat_id, "text": message})

def get_available_fx_pairs():
    """Fetch tradable instruments and return liquid FX pairs."""
    url = f"{host}/v3/accounts/{account_id}/instruments"
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        print(f"Instrument list HTTP {r.status_code}: {r.text}")
        return []
    instruments = r.json().get("instruments", [])
    fx_pairs = [inst["name"] for inst in instruments if inst.get("type") == "CURRENCY"]
    # Choose most common majors
    majors = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD", "USD_CHF", "NZD_USD"]
    tradable_pairs = [p for p in majors if p in fx_pairs]
    return tradable_pairs

def ict_setup_detected(pair):
    """
    Placeholder for ICT strategy logic:
    - Liquidity sweep
    - FVG retrace
    - Break of structure
    Returns True if conditions met.
    """
    # TODO: Replace with full ICT logic
    return False

# ===== Main Bot =====
def main():
    pairs = get_available_fx_pairs()
    if not pairs:
        print("No tradable FX pairs found.")
        return

    send_telegram(f"Bot started — scanning {len(pairs)} pairs: {', '.join(pairs)}")

    while True:
        for pair in pairs:
            url = f"{host}/v3/accounts/{account_id}/pricing?instruments={pair}"
            r = requests.get(url, headers=headers)
            if r.status_code != 200:
                print(f"Pricing HTTP {r.status_code} for {pair}: {r.text}")
                continue

            prices = r.json().get("prices", [])
            if not prices:
                continue

            bid = prices[0].get("bids", [{}])[0].get("price")
            ask = prices[0].get("asks", [{}])[0].get("price")
            print(f"{pair} | Bid: {bid} | Ask: {ask}")

            # ICT strategy check
            if ict_setup_detected(pair):
                msg = f"ICT setup found on {pair} — potential trade"
                print(msg)
                send_telegram(msg)

        time.sleep(10)  # Check every 10 seconds

if __name__ == "__main__":
    main()
