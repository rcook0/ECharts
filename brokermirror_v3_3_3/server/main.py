from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import time, uuid, hashlib, secrets, asyncio, json, os, tempfile, zipfile, math
from pathlib import Path
import socketio
from sqlalchemy.orm import Session
from sqlalchemy import select
from db import get_db
from models import User, Wallet, Transaction, KycUpload, Audit as AuditModel, PaperTrade, PaperAccount, PaperLedger
from auth import make_token, current_user, require_admin, verify_password
from utils_sign import sign_event, verify_event
from adapters import MockAdapter, CCXTAdapter, MT5Adapter

DATA_DIR=Path(__file__).parent/"data"; (DATA_DIR/"kyc").mkdir(parents=True, exist_ok=True)
def _now_ms(): return int(time.time()*1000)
def _id(p): return f"{p}_{uuid.uuid4().hex[:10]}"
def audit(db: Session, evt: str, data: dict): db.add(AuditModel(ts=_now_ms(), evt=evt, data=json.dumps(data))); db.commit()

CONFIG={"adapter":{"type":"mock","params":{}}, "trusted_mode": False}
RISK={"max_dd_pct":0.30,"max_trade_notional_pct":0.10,"lev_fx":30.0,"lev_crypto":5.0,"lev_metals":20.0}
RISK_PRESET="medium"
PRESETS={
  "low":    {"max_dd_pct":0.15,"max_trade_notional_pct":0.05,"lev_fx":50.0,"lev_crypto":10.0,"lev_metals":25.0},
  "medium": {"max_dd_pct":0.30,"max_trade_notional_pct":0.10,"lev_fx":30.0,"lev_crypto":5.0,"lev_metals":20.0},
  "high":   {"max_dd_pct":0.50,"max_trade_notional_pct":0.20,"lev_fx":20.0,"lev_crypto":3.0,"lev_metals":15.0},
}

ADAPTER=MockAdapter()
HEALTH={"adapter":{"type":"mock","ok":True,"errors":0,"last_tick_ms":None}, "trusted_mode": CONFIG["trusted_mode"]}

def set_adapter(cfg):
    global ADAPTER, CONFIG
    t=(cfg.get("type") or "mock").lower(); p=cfg.get("params") or {}
    if t=="mock": ADAPTER=MockAdapter()
    elif t=="ccxt": ADAPTER=CCXTAdapter(exchange=p.get("exchange","binance"), symbol_map=p.get("symbol_map"))
    elif t=="mt5": ADAPTER=MT5Adapter(zmq_url=p.get("zmq_url"))
    else: raise HTTPException(400,"unknown adapter")
    CONFIG["adapter"]={"type":t,"params":p}; HEALTH["adapter"]|={"type":t,"errors":0,"ok":True}

def set_trust(flag: bool):
    CONFIG["trusted_mode"]=bool(flag); HEALTH["trusted_mode"]=CONFIG["trusted_mode"]

def symbol_leverage(symbol: str)->float:
    s=symbol.upper()
    if "BTC" in s or "ETH" in s: return RISK["lev_crypto"]
    if s.startswith("XAU") or s.startswith("XAG"): return RISK["lev_metals"]
    return RISK["lev_fx"]

async def mark(symbol: str)->float:
    t=await ADAPTER.get_tick(symbol); b=float(t.get("bid") or 0.0); a=float(t.get("ask") or b); return (a+b)/2.0 if (a and b) else (a or b)

api=FastAPI(title="BrokerMirror v3.3.3"); api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
sio=socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*"); app=socketio.ASGIApp(sio, other_asgi_app=api)
SUBS={}; STREAM_RUNNING=False

async def stream_loop():
    global STREAM_RUNNING
    if STREAM_RUNNING: return
    STREAM_RUNNING=True
    try:
        while True:
            syms=set(SUBS.values())
            for sym in syms:
                try:
                    tick=await ADAPTER.get_tick(sym); HEALTH["adapter"]["ok"]=True; HEALTH["adapter"]["last_tick_ms"]=tick.get("t") or int(time.time()*1000); await sio.emit("tick", tick)
                except Exception as e:
                    HEALTH["adapter"]["errors"]+=1; HEALTH["adapter"]["ok"]=False; await sio.emit("tick_error", {"symbol":sym, "error":str(e)})
            await asyncio.sleep(1.0)
    finally: STREAM_RUNNING=False

@sio.event
async def connect(sid, environ, auth): await sio.emit("hello", {"sid":sid})
@sio.event
async def subscribe(sid, data):
    sym=(data or {}).get("symbol","EURUSD").upper(); SUBS[sid]=sym; await sio.emit("subscribed", {"sid":sid, "symbol":sym})
    if not STREAM_RUNNING: asyncio.create_task(stream_loop())
@sio.event
async def unsubscribe(sid, data): SUBS.pop(sid, None); await sio.emit("unsubscribed", {"sid":sid})
@sio.event
async def disconnect(sid): SUBS.pop(sid, None)

# ========= Indicator math =========
def ema(src, n):
    if not src: return []
    k=2/(n+1); out=[]; p=None
    for x in src:
        p = x if p is None else p + k*(x-p)
        out.append(p)
    return out
def sma(src, n):
    out=[]; s=0.0
    for i,x in enumerate(src):
        s+=x
        if i>=n: s-=src[i-n]
        out.append(s/n if i>=n-1 else None)
    return out
def rsi(src, n=14):
    out=[None]; g=0.0; l=0.0
    for i in range(1,len(src)):
        ch=src[i]-src[i-1]
        g=(g*(n-1)+max(ch,0))/n
        l=(l*(n-1)+max(-ch,0))/n
        rs = (g/l) if l!=0 else 100.0
        out.append(100-(100/(1+rs)))
    return out
def macd(src, fast=12, slow=26, signal=9):
    efast=ema(src,fast); eslow=ema(src,slow)
    mac=[(efast[i]-eslow[i]) if (efast[i] is not None and eslow[i] is not None) else None for i in range(len(src))]
    sig=ema([x if x is not None else 0.0 for x in mac], signal)
    hist=[(mac[i]-sig[i]) if (mac[i] is not None and sig[i] is not None) else None for i in range(len(src))]
    return mac, sig, hist
def cci(o,h,l,c, period=20):
    tp=[(h[i]+l[i]+c[i])/3.0 for i in range(len(c))]
    sma_tp=sma(tp, period)
    out=[]
    for i in range(len(tp)):
        if i<period-1: out.append(None); continue
        mean_dev=sum(abs(tp[j]-sma_tp[i]) for j in range(i-period+1, i+1))/period
        denom=0.015*mean_dev if mean_dev!=0 else 1e-9
        out.append((tp[i]-sma_tp[i])/denom)
    return out

async def fetch_ohlc(symbol, tf, limit):
    bars=await ADAPTER.get_ohlc(symbol, tf, limit)
    o=[b.get("o") for b in bars]; h=[b.get("h") for b in bars]; l=[b.get("l") for b in bars]; c=[b.get("c") for b in bars]; t=[b.get("t") for b in bars]
    return t,o,h,l,c

@api.get("/indicators")
async def indicators(symbol: str="EURUSD", tf: str="M15", limit: int=200,
                     ema_fast: int=20, ema_slow: int=50, rsi_len: int=14,
                     macd_fast: int=12, macd_slow: int=26, macd_signal: int=9,
                     cci_len: int=20):
    symbol=symbol.upper(); tf=tf.upper()
    t,o,h,l,c = await fetch_ohlc(symbol, tf, limit)
    ema_f=ema(c, ema_fast); ema_s=ema(c, ema_slow); r=rsi(c, rsi_len); m, s, hist = macd(c, macd_fast, macd_slow, macd_signal); ci=cci(o,h,l,c, cci_len)
    return {"symbol":symbol,"tf":tf,"t":t,"ind":{"ema_fast":ema_f,"ema_slow":ema_s,"rsi":r,"macd":m,"signal":s,"hist":hist,"cci":ci}}

@api.get("/signals/matrix")
async def signal_matrix(symbols: str|None=None, tf: str="M15", limit: int=200,
                        rsi_hi: float=60.0, rsi_lo: float=40.0, macd_eps: float=0.0, cci_hi: float=100.0, cci_lo: float=-100.0):
    tf=tf.upper(); syms=[s.strip().upper() for s in (symbols.split(",") if symbols else ADAPTER.list_symbols()) if s.strip()]
    cols=["EMA","RSI","MACD","CCI"]; data=[]; details={}
    for si,sym in enumerate(syms):
        try:
            _t,o,h,l,c = await fetch_ohlc(sym, tf, limit)
            ema20=ema(c,20); ema50=ema(c,50); r=rsi(c,14); m,sg,hist=macd(c,12,26,9); ci=cci(o,h,l,c,20)
            v_ema = 1 if (ema20[-1] is not None and ema50[-1] is not None and ema20[-1]>ema50[-1]) else (-1 if (ema20[-1] is not None and ema50[-1] is not None and ema20[-1]<ema50[-1]) else 0)
            v_rsi = 1 if (r[-1] is not None and r[-1] >= rsi_hi) else (-1 if (r[-1] is not None and r[-1] <= rsi_lo) else 0)
            hh = hist[-1] if hist and hist[-1] is not None else 0.0
            v_macd = 1 if hh>macd_eps else (-1 if hh<-macd_eps else 0)
            cc = ci[-1] if ci and ci[-1] is not None else 0.0
            v_cci = 1 if cc>=cci_hi else (-1 if cc<=cci_lo else 0)
            vals=[v_ema, v_rsi, v_macd, v_cci]
            for xi,v in enumerate(vals): data.append([xi, si, v])
            details[sym]={"EMA":{"ema20":ema20[-1],"ema50":ema50[-1],"signal":v_ema},
                          "RSI":{"value":r[-1],"hi":rsi_hi,"lo":rsi_lo,"signal":v_rsi},
                          "MACD":{"hist":hh,"eps":macd_eps,"signal":v_macd},
                          "CCI":{"value":cc,"hi":cci_hi,"lo":cci_lo,"signal":v_cci}}
        except Exception as e:
            for xi in range(len(cols)): data.append([xi, si, 0])
            details[sym]={"error":str(e)}
    return {"x":cols,"y":syms,"data":data,"details":details,"tf":tf,"limit":limit}

@api.post("/auth/register")
def auth_register(email: str, password: str, db: Session=Depends(get_db)):
    from passlib.hash import bcrypt
    if db.scalar(select(User).where(User.email==email)): raise HTTPException(400,"email exists")
    u=User(email=email, role="user", password_hash=bcrypt.hash(password)); db.add(u); db.flush()
    db.add(PaperAccount(user_id=u.id, cash_usd=100000.0, peak_equity=100000.0, created_at=int(time.time()*1000)))
    db.commit(); audit(db,"auth.register",{"uid":u.id}); return {"ok":True}

@api.post("/auth/login")
def auth_login(email: str, password: str, db: Session=Depends(get_db)):
    u=db.scalar(select(User).where(User.email==email))
    if not u or not verify_password(password, u.password_hash): raise HTTPException(401,"bad credentials")
    audit(db,"auth.login",{"uid":u.id}); return {"token":make_token(u), "role":u.role, "userId":u.id}

@api.get("/config/adapter")
def get_adapter(): return {"adapter": CONFIG["adapter"]}
@api.post("/config/adapter")
def post_adapter(cfg: dict|None=None, _: User=Depends(require_admin)):
    set_adapter(cfg or {"type":"mock"}); audit(db=next(get_db()), evt="adapter.set", data=CONFIG["adapter"]); return {"ok":True, "adapter":CONFIG["adapter"]}

@api.get("/config/risk")
def get_risk(_: User=Depends(require_admin)): return {"risk": RISK, "preset": RISK_PRESET}
@api.post("/config/risk")
def set_risk(payload: dict, _: User=Depends(require_admin)):
    RISK.update({k:v for k,v in (payload or {}).items() if k in {"max_dd_pct","max_trade_notional_pct","lev_fx","lev_crypto","lev_metals"}})
    return {"ok":True, "risk": RISK}

@api.get("/config/risk/preset")
def get_preset(_: User=Depends(require_admin)): return {"preset": RISK_PRESET, "values": RISK, "presets": PRESETS}
@api.post("/config/risk/preset")
def set_preset(payload: dict, _: User=Depends(require_admin)):
    global RISK_PRESET
    name=str((payload or {}).get("preset","")).lower()
    if name not in PRESETS: raise HTTPException(400,"unknown preset")
    RISK.update(PRESETS[name]); RISK_PRESET=name
    return {"ok":True, "preset": RISK_PRESET, "values": RISK}

@api.get("/health/adapters")
def health_adapters(): return HEALTH

@api.get("/products/forex/chart")
async def chart(symbol: str="EURUSD", tf: str="M1", limit: int=200):
    xs=await ADAPTER.get_ohlc(symbol.upper(), tf.upper(), limit); return {"symbol":symbol.upper(), "tf":tf.upper(), "candles":xs}
@api.get("/symbols")
def symbols(): return {"symbols": ADAPTER.list_symbols()}

def ensure_paper_account(db: Session, uid: int)->PaperAccount:
    pa=db.scalar(select(PaperAccount).where(PaperAccount.user_id==uid))
    if not pa:
        now=int(time.time()*1000)
        pa=PaperAccount(user_id=uid, cash_usd=100000.0, peak_equity=100000.0, created_at=now)
        db.add(pa); db.commit()
    return pa
async def compute_account_view(db: Session, uid: int):
    pa=ensure_paper_account(db, uid)
    unreal=0.0; margin_used=0.0
    equity = pa.cash_usd + unreal
    if equity>pa.peak_equity:
        pa.peak_equity=equity; db.commit()
    dd = 0.0 if pa.peak_equity<=0 else (pa.peak_equity - equity)/pa.peak_equity
    return {"cash": pa.cash_usd, "equity": equity, "peak": pa.peak_equity, "drawdownPct": dd, "unrealized": unreal, "marginUsed": margin_used, "marginFree": equity, "positions": []}

from passlib.hash import bcrypt  # used in verify_password

