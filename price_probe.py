import os, requests
aid = os.environ["OANDA_ACCOUNT_ID"]
tok = os.environ["OANDA_TOKEN"]
env = os.environ.get("OANDA_ENV","practice").lower()
inst = os.environ.get("INSTRUMENTS","SPX500_USD").split(",")[0].strip()
host = "https://api-fxpractice.oanda.com" if env=="practice" else "https://api-fxtrade.oanda.com"
r = requests.get(f"{host}/v3/accounts/{aid}/pricing",
                 params={"instruments": inst},
                 headers={"Authorization": f"Bearer {tok}"},
                 timeout=15)
print("HTTP", r.status_code)
print(r.text[:800])
