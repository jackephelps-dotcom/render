class Candle:
    __slots__=("ts","o","h","l","c","v")
    def __init__(self, ts,o,h,l,c,v): self.ts, self.o, self.h, self.l, self.c, self.v = ts,o,h,l,c,v

def atr14(c):
    if len(c)<15: return None
    tr=[]
    for i in range(1,len(c)):
        p=c[i-1]; x=c[i]
        tr.append(max(x.h-p.c, p.c-x.l, x.h-x.l))
    return sum(tr[-14:])/14

def displacement(c, k=0.8):
    a=atr14(c)
    if a is None: return False, False
    body = c[-1].c - c[-1].o
    return body >  k*a, -body > k*a

def bos(c, lookback=40):
    if len(c)<lookback+5: return False, False
    highs=[x.h for x in c[-lookback:]]
    lows =[x.l for x in c[-lookback:]]
    return c[-1].c > max(highs), c[-1].c < min(lows)

def swings(c, L=2, R=2):
    sh=sl=None
    n=len(c)
    for i in range(L, n-R):
        hi = max(x.h for x in c[i-L:i+R+1])
        lo = min(x.l for x in c[i-L:i+R+1])
        if c[i].h==hi: sh=c[i].h
        if c[i].l==lo: sl=c[i].l
    return sh, sl

def equal_levels(c, tol=0.0005, window=60):
    highs=[c[i].h for i in range(max(0,len(c)-window), len(c))]
    lows =[c[i].l for i in range(max(0,len(c)-window), len(c))]
    eqh = any(abs(highs[i]-highs[j])/max(highs[i],1) < tol for i in range(len(highs)) for j in range(i+1,len(highs)))
    eql = any(abs(lows[i]-lows[j])/max(lows[i],1)  < tol for i in range(len(lows))  for j in range(i+1,len(lows)))
    return eqh, eql

def liquidity_sweep(c, sh, sl):
    z=c[-1]
    sweep_hi = (sh is not None and z.h > sh and z.c < sh)
    sweep_lo = (sl is not None and z.l < sl and z.c > sl)
    return sweep_hi, sweep_lo

def fvg_latest(c):
    bull=None; bear=None
    for i in range(2,len(c)):
        c2,c1,c0 = c[i-2], c[i-1], c[i]
        if c1.l > c2.h: bull=((c1.l, c2.h), i)
        if c1.h < c2.l: bear=((c2.l, c1.h), i)
    return bull, bear

def retraced_into_fvg(c, fvg, side):
    if not fvg: return False
    (top,bottom), idx = fvg
    z = c[-1]
    if side=="long":
        return (z.l <= top and z.l >= bottom) or (z.c >= bottom)
    else:
        return (z.h >= bottom and z.h <= top) or (z.c <= top)

def premium_discount(c, lookback=100):
    rng = c[-lookback:] if len(c)>=lookback else c[:]
    return (max(x.h for x in rng)+min(x.l for x in rng))/2

def impulse_leg(c, bias_up: bool):
    if len(c)<20: return None
    for i in range(len(c)-1, max(18,len(c)-60), -1):
        window = c[:i+1]
        du, dd = displacement(window, 0.8)
        if bias_up and du:
            o = c[i].o; x = c[i].h
            return (o, x)
        if (not bias_up) and dd:
            o = c[i].o; x = c[i].l
            return (o, x)
    return None

def in_ote(px, leg, bias_up: bool, lo=0.62, hi=0.79):
    if not leg: return False
    a,b = leg
    if bias_up:
        fib62 = b - (b-a)*hi
        fib79 = b - (b-a)*lo
        return fib62 <= px <= fib79
    else:
        fib62 = a + (b-a)*lo
        fib79 = a + (b-a)*hi
        return fib62 <= px <= fib79

def decide(series, series5, series15, series60, cfg):
    c = series
    if len(c)<150 or len(series5)<60 or len(series15)<30 or len(series60)<30:
        return {"action":"FLAT","reason":"warmup"}

    b15u,b15d = bos(series15, cfg["bos_lookback"]); d15u,d15d = displacement(series15, cfg["atr_mult_displacement"])
    b60u,b60d = bos(series60, cfg["bos_lookback"]); d60u,d60d = displacement(series60, cfg["atr_mult_displacement"])
    bias_up   = (b15u or d15u) and (b60u or d60u)
    bias_down = (b15d or d15d) and (b60d or d60d)

    du, dd = displacement(c, cfg["atr_mult_displacement"])
    sh, sl = swings(c, cfg["swing_left"], cfg["swing_right"])
    sw_hi, sw_lo = liquidity_sweep(c, sh, sl)
    bull_fvg, bear_fvg = fvg_latest(c)
    eq = premium_discount(c, 100)
    px = c[-1].c

    leg_up   = impulse_leg(c, True)
    leg_down = impulse_leg(c, False)

    long_ok  = bias_up
    eqh, eql = equal_levels(c, window=60)
    if cfg["require_sweep"]:
        long_ok &= (sw_lo or eql)
    if cfg["require_disp_on_trigger"]:
        long_ok &= du
    if cfg["require_fvg_retrace"]:
        long_ok &= retraced_into_fvg(c, bull_fvg, "long")
    if cfg["require_discount_for_longs"]:
        long_ok &= (px < eq)
    if cfg.get("use_ote", True):
        long_ok &= in_ote(px, leg_up, True, cfg["ote_min"], cfg["ote_max"])

    short_ok = bias_down
    if cfg["require_sweep"]:
        short_ok &= (sw_hi or eqh)
    if cfg["require_disp_on_trigger"]:
        short_ok &= dd
    if cfg["require_fvg_retrace"]:
        short_ok &= retraced_into_fvg(c, bear_fvg, "short")
    if cfg["require_premium_for_shorts"]:
        short_ok &= (px > eq)
    if cfg.get("use_ote", True):
        short_ok &= in_ote(px, leg_down, False, cfg["ote_min"], cfg["ote_max"])

    if long_ok:
        stop = min(sl or px, min(x.l for x in c[-5:]))
        tp   = px + cfg.get("rr",2.0)*(px - stop)
        return {"action":"BUY","price":px,"sl":stop,"tp":tp,
                "reason":"HTF up (15m/1h) + sweep + displacement + fresh FVG + OTE pullback in discount"}

    if short_ok:
        stop = max(sh or px, max(x.h for x in c[-5:]))
        tp   = px - cfg.get("rr",2.0)*(stop - px)
        return {"action":"SELL","price":px,"sl":stop,"tp":tp,
                "reason":"HTF down (15m/1h) + sweep + displacement + fresh FVG + OTE pullback in premium"}

    return {"action":"FLAT","reason":"no setup"}
