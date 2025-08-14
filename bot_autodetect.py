import os, json, time, requests, aiohttp, asyncio, pytz
from datetime import datetime, timezone
from notifier import send as notify
from strategy_pro import Candle, decide

# ---- ENV ----
ENV  = os.getenv("OANDA_ENV","practice").lower()               # practice | live
AID  = os.getenv("OANDA_ACCOUNT_ID","").strip()
TOK  = os.getenv("OANDA_TOKEN","").strip()
INST_LIST = [s.strip() for s in os.getenv("INSTRUMENTS","SPX500_USD,US500USD").split(",")]
TZ   = pytz.timezone(os.getenv("TIMEZONE","Australia/Sydney"))
HOST = "https://api-fxpractice.oanda.com" if ENV=="practice" else "https://api-fxtrade.oanda.com"
STREAM_HOST = "https://stream-fxpractice.oanda.com" if ENV=="practice" else "https://stream-fxtrade.oanda.com"

def must_env(k):
    v = os.getenv(k,"").strip()
    if not v: raise SystemExit(f"Missing required env var: {k}")
    return v

AID = must_env("OANDA_ACCOUNT_ID")
TOK = must_env("OANDA_TOKEN")

# ---- Helpers ----
def list_instruments():
    r = requests.get(f"{HOST}/v3/accounts/{AID}/instruments",
                     headers={"Authorization": f"Bearer {TOK}"}, timeout=15)
    if r.status_code != 200:
        raise SystemExit(f"Instrument list HTTP {r.status_code}: {r.text[:300]}")
    return [it["name"] for it in r.json().get("instruments", [])]

def first_supported_symbol():
    names = list_instruments()
    # If user provided candidates, choose first that exists
    for want in INST_LIST:
        if want in names:
            return want
    # Otherwise find a likely SPX/US500 variant
    for n in names:
        u = n.upper()
        if any(tag in u for tag in ["SPX", "SPX500", "US500", "US 500"]):
            return n
    return None

def polling_price(inst):
    r = requests.get(f"{HOST}/v3/accounts/{AID}/pricing",
                     params={"instruments": inst},
                     headers={"Authorization": f"Bearer {TOK}"}, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"Pricing HTTP {r.status_code}: {r.text[:200]}")
    data = r.json().get("prices", [])
    if not data: return None, None
    p = data[0]; bids=p.get("bids",[]); asks=p.get("asks",[])
    if not bids or not asks: return None, None
    mid = (float(bids[0]["price"]) + float(asks[0]["price"])) / 2.0
    tstr = p.get("time","")[:19]
    ts = int(datetime.fromisoformat(tstr.replace("Z","+00:00")).timestamp()) if tstr else int(time.time())
    return mid, ts

class Series:
    def __init__(self):
        self.m1=[]; self.m5=[]; self.m15=[]; self.h1=[]
        self._cur_minute=None
        self._o=self._h=self._l=self._c=None
    def on_tick(self, price: float, ts: int):
        m = ts - (ts % 60)
        if self._cur_minute is None:
            self._cur_minute=m; self._o=self._h=self._l=self._c=price; return False
        if m==self._cur_minute:
            self._h=max(self._h,price); self._l=min(self._l,price); self._c=price; return False
        # close candle
        self.m1.append(Candle(self._cur_minute,self._o,self._h,self._l,self._c,0.0))
        self._cur_minute=m; self._o=self._h=self._l=self._c=price
        self._rebuild_htf(); return True
    def _rebuild_htf(self):
        def build(src, mins):
            out=[]; step=mins*60
            for x in src:
                bts = x.ts - (x.ts % step)
                if not out or out[-1].ts!=bts:
                    out.append(Candle(bts,x.o,x.h,x.l,x.c,0.0))
                else:
                    b=out[-1]; b.h=max(b.h,x.h); b.l=min(b.l,x.l); b.c=x.c
            return out
        self.m5=build(self.m1,5); self.m15=build(self.m1,15); self.h1=build(self.m1,60)

def session_ok(ts, sessions):
    if not sessions.get("use_sessions", True): return True
    hhmm = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M")
    def in_range(a,b): return a<=hhmm<=b
    lon = CFG["sessions"].get("london",["07:00","10:00"])
    ny  = CFG["sessions"].get("newyork",["13:30","16:00"])
    return in_range(lon[0],lon[1]) or in_range(ny[0],ny[1])

async def stream_prices(inst):
    url = f"{STREAM_HOST}/v3/accounts/{AID}/pricing/stream"
    headers={"Authorization": f"Bearer {TOK}"}; params={"instruments": inst}
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers, params=params, timeout=None) as resp:
            async for line in resp.content:
                if not line: continue
                try:
                    obj = json.loads(line.decode("utf-8").strip())
                except Exception: continue
                if obj.get("type")=="PRICE":
                    bids=obj.get("bids",[]); asks=obj.get("asks",[])
                    if not bids or not asks: continue
                    mid=(float(bids[0]["price"])+float(asks[0]["price"]))/2.0
                    tstr = obj.get("time","")[:19]
                    ts = int(datetime.fromisoformat(tstr.replace("Z","+00:00")).timestamp()) if tstr else int(time.time())
                    yield mid, ts

def run_polling(inst, CFG):
    notify(f"OANDA ICT S&P bot online — instrument `{inst}` — env `{ENV}` (REST polling)")
    series=Series()
    while True:
        try:
            px, ts = polling_price(inst)
            if px is None: time.sleep(1); continue
            if session_ok(ts, CFG["sessions"]):
                closed = series.on_tick(px, ts)
                if closed and len(series.m1)>150:
                    sig = decide(series.m1, series.m5, series.m15, series.h1, CFG["confirmations"])
                    if sig["action"] in ("BUY","SELL"):
                        stamp = datetime.now(timezone.utc).astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
                        mgmt = "Mgmt: 50% @1R → SL to BE → run to 2R" if CFG["risk"]["partials_at_1r"] else ""
                        notify(f"*{inst}* [1m] — *{sig['action']}*\nEntry `{sig['price']}`  SL `{sig['sl']}`  TP `{sig['tp']}`\n_{sig['reason']}_\n{mgmt}\n{stamp}")
            time.sleep(1)
        except Exception as e:
            notify(f"Bot error (recovering): {e}")
            time.sleep(3)

async def run_stream(inst, CFG):
    notify(f"OANDA ICT S&P bot online — instrument `{inst}` — env `{ENV}` (stream)")
    series=Series()
    # if stream is flaky, fall back to polling after 30s
    fallback_at = time.time()+30
    async for px, ts in stream_prices(inst):
        if time.time()>fallback_at: break
        if session_ok(ts, CFG["sessions"]):
            closed = series.on_tick(px, ts)
            if closed and len(series.m1)>150:
                sig = decide(series.m1, series.m5, series.m15, series.h1, CFG["confirmations"])
                if sig["action"] in ("BUY","SELL"):
                    stamp = datetime.now(timezone.utc).astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
                    mgmt = "Mgmt: 50% @1R → SL to BE → run to 2R" if CFG["risk"]["partials_at_1r"] else ""
                    notify(f"*{inst}* [1m] — *{sig['action']}*\nEntry `{sig['price']}`  SL `{sig['sl']}`  TP `{sig['tp']}`\n_{sig['reason']}_\n{mgmt}\n{stamp}")

if __name__ == "__main__":
    # load config
    with open("config.json","r") as f:
        CFG = json.load(f)

    # 1) Find a supported instrument for THIS account
    inst = first_supported_symbol()
    if not inst:
        raise SystemExit("Could not find an S&P instrument in your account. Add the exact name to INSTRUMENTS or enable CFDs in OANDA.")

    # 2) Try stream briefly; if nothing comes, fall back to REST polling (reliable)
    try:
        asyncio.run(run_stream(inst, CFG))
    except Exception as e:
        notify(f"Stream failed, falling back to REST: {e}")
    # 3) Polling loop
    run_polling(inst, CFG)
