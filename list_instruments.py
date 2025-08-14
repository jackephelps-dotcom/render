import os, requests

env = os.getenv("OANDA_ENV","practice").lower()
token = os.getenv("OANDA_TOKEN","").strip()
account = os.getenv("OANDA_ACCOUNT_ID","").strip()

host = "https://api-fxpractice.oanda.com" if env=="practice" else "https://api-fxtrade.oanda.com"

url = f"{host}/v3/accounts/{account}/instruments"
r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
print("HTTP", r.status_code)
print(r.text[:1000])
