import os, requests, sys, json
env = os.getenv("OANDA_ENV","practice").lower()
tok = os.getenv("OANDA_TOKEN","").strip()
host = "https://api-fxpractice.oanda.com" if env=="practice" else "https://api-fxtrade.oanda.com"
if not tok: sys.exit("Missing OANDA_TOKEN")
r = requests.get(f"{host}/v3/accounts", headers={"Authorization": f"Bearer {tok}"}, timeout=15)
print("HTTP", r.status_code)
print(r.text)
if r.status_code == 200:
    data = r.json()
    ids = [a["id"] for a in data.get("accounts", [])]
    print("Account IDs:", ids)
