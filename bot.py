import os, json, asyncio, aiohttp, pytz
from datetime import datetime, timezone
from notifier import send as notify
from strategy_pro import Candle, decide

ENV        = os.getenv("OANDA_ENV","practice").lower()      # practice | live
ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID","")
TOKEN      = os.getenv("OANDA_TOKEN","")
INSTRUMENTS= [s.strip() for s in os.getenv("INSTRUMENTS","SPX500_USD,US500USD").split(",")]
TZ         = pytz.timezone(os.getenv("TIMEZONE","Australia/Sydney"))

STREAM_HOST = "https://stream-fxpractice.oanda.com" if ENV=="practice" else "https://stream-fxtrade.oanda.com"

with open("config.json","r") as f:
    CFG = json.load(f)

class Series:
    def __init__(self):
        self.m1=[]; self.m5=[]; self.m15=[]; self.h1=[]
        self._cur_minute=None
        self._cur_o=self._cur_h=self._cur_l=self._cur_c=None
        self._cur_v=0.0

    def on_tick(self, price: float, ts: int):
        minute = ts - (ts % 60)
        if self._cur_minute is None:
            self._cur_minute = minute
            self._cur_o = self._cur_h = self._cur_l = self._cur_c = price
            self._cur_v = 0.0
            return False
        if minute == self._cur_minute:
            self._cur_h = max(self._cur_h, price)
            self._cur_l = min(self._cur_l, price)
            self._cur_c = price
            return False
        else:
            self.m1.append(Candle(self._cur_minute, self._cur_o, self._cur_h, self._cur_l, self._cur_c, self._cur_v))
            self._cur_minute = minute
            self._cur_o = self._cur_h = self._cur_l = self._cur_c = price
            self._cur_v = 0.0
            self._rebuild_htf()
            return True

    def _rebuild_htf(self):
        def build(src, minutes):
            out=[]
            step = minutes*60
            for x in src:
                bts = x.ts - (x.ts % step)
                if not out or out[-1].ts != bts:
                    out.append(Candle(bts, x.o, x.h, x.l, x.c, x.v))
                else:
                    b = out[-1]
                    b.h = max(b.h, x.h); b.l = min(b.l, x.l); b.c = x.c; b.v += x.v
            return out
        self.m5  = build(self.m1, 5)
        self.m15 = build(self.m1, 15)
        self.h1  = build(self.m1, 60)

async def stream_prices(session, instrument):
    url = f"{STREAM_HOST}/v3/accounts/{ACCOUNT_ID}/pricing/stream"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    params = {"instruments": instrument}
    async with session.get(url, headers=headers, params=params, timeout=None) as resp:
        async for line in resp.content:
            if not line: continue
            try:
                obj = json.loads(line.decode("utf-8").strip())
            except Exception:
                continue
            if "heartbeat" in obj.get("type","").lower():
                continue
            if obj.get("type") == "PRICE":
                bids = obj.get("bids", []); asks = obj.get("asks", [])
                if not bids or not asks: continue
                px = (float(bids[0]["price"]) + float(asks[0]["price"])) / 2.0
                tstr = obj.get("time","")[:19]  # ISO up to seconds
                if not tstr: continue
                ts = int(datetime.fromisoformat(tstr.replace("Z","+00:00")).timestamp())
                yield px, ts

def session_ok(ts, sessions):
    if not sessions.get("use_sessions", True): return True
    hhmm = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M")
    def in_range(start, end): return start <= hhmm <= end
    lon = sessions.get("london", ["07:00","10:00"])
    ny  = sessions.get("newyork",["13:30","16:00"])
    return in_range(lon[0], lon[1]) or in_range(ny[0], ny[1])

async def run():
    if not ACCOUNT_ID or not TOKEN:
        raise SystemExit("Set OANDA_ACCOUNT_ID and OANDA_TOKEN as environment variables")

    async with aiohttp.ClientSession() as s:
        chosen = None
        for inst in INSTRUMENTS:
            try:
                async for px, ts in stream_prices(s, inst):
                    chosen = inst
                    break
                if chosen: break
            except Exception:
                continue
        if not chosen:
            raise SystemExit("No instrument streamed. Try SPX500_USD or US500USD.")

        notify(f"OANDA ICT S&P bot online — instrument `{chosen}` — env `{ENV}`")

        series = Series()
        async for px, ts in stream_prices(s, chosen):
            if not session_ok(ts, CFG["sessions"]): continue
            closed = series.on_tick(px, ts)
            if closed and len(series.m1) > 150:
                sig = decide(series.m1, series.m5, series.m15, series.h1, CFG["confirmations"])
                if sig["action"] in ("BUY","SELL"):
                    stamp = datetime.now(timezone.utc).astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
                    mgmt = "Mgmt: 50% @1R → SL to BE → run to 2R" if CFG["risk"]["partials_at_1r"] else ""
                    notify(f"*{chosen}* [1m] — *{sig['action']}*\\nEntry `{sig['price']}`  SL `{sig['sl']}`  TP `{sig['tp']}`\\n_{sig['reason']}_\\n{mgmt}\\n{stamp}")

if __name__=="__main__":
    asyncio.run(run())
