import os, requests
TG_TOKEN = os.getenv("TELEGRAM_TOKEN","")
TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID","")
def send(msg: str):
    if not TG_TOKEN or not TG_CHAT:
        print(msg); return
    try:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      data={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"}, timeout=5)
    except Exception as e:
        print("Telegram error:", e)
