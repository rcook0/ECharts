from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import time, uuid, hashlib, secrets, asyncio, json, os, tempfile, zipfile
from pathlib import Path
import socketio
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from adapters import MockAdapter, CCXTAdapter, MT5Adapter
from db import get_db
from models import User, Wallet, Transaction, KycUpload, Audit as AuditModel, PaperTrade, PaperAccount, PaperLedger
from auth import make_token, current_user, require_admin, verify_password
from utils_sign import sign_event, verify_event

DATA_DIR=Path(__file__).parent/"data"; (DATA_DIR/"kyc").mkdir(parents=True, exist_ok=True)
def _now_ms(): return int(time.time()*1000)
def _id(p): return f"{p}_{uuid.uuid4().hex[:10]}"
def audit(db: Session, evt: str, data: dict): db.add(AuditModel(ts=_now_ms(), evt=evt, data=json.dumps(data))); db.commit()

CONFIG={"adapter":{"type":"mock","params":{}}, "trusted_mode": False}
RISK={"max_dd_pct":0.30,"max_trade_notional_pct":0.10,"lev_fx":30.0,"lev_crypto":5.0,"lev_metals":20.0}
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
    CONFIG["trusted_mode"]=bool(flag); HEALTH["trusted_mode"]=CONFIG["trusted_mode"]}

def symbol_leverage(symbol: str)->float:
    s=symbol.upper()
    if "BTC" in s or "ETH" in s: return RISK["lev_crypto"]
    if s.startswith("XAU") or s.startswith("XAG"): return RISK["lev_metals"]
    return RISK["lev_fx"]

async def mark(symbol: str)->float:
    t=await ADAPTER.get_tick(symbol); b=float(t.get("bid") or 0.0); a=float(t.get("ask") or b); return (a+b)/2.0 if (a and b) else (a or b)

api=FastAPI(title="WL Trader (RE) v3.3.0"); api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
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

# ---------- Helpers for account calc ----------
def ensure_paper_account(db: Session, uid: int)->PaperAccount:
    pa=db.scalar(select(PaperAccount).where(PaperAccount.user_id==uid))
    if not pa:
        now=int(time.time()*1000)
        pa=PaperAccount(user_id=uid, cash_usd=100000.0, peak_equity=100000.0, created_at=now)
        db.add(pa); db.commit()
    return pa

def fifo_reconstruct(trades):
    from collections import deque
    lots=deque(); realized=0.0
    for t in trades:
        side=t.side; qty=float(t.qty); price=float(t.price)
        if not lots or (lots and lots[0][0]==side and sum(q for s,q,p in lots if s==side)>=0):
            lots.append([side, qty, price]); continue
        while qty>0 and lots:
            opp_side, opp_qty, opp_price = lots[0]
            if opp_side==side: break
            match=min(qty, opp_qty)
            if side=="SELL" and opp_side=="BUY": realized += (price - opp_price)*match
            elif side=="BUY" and opp_side=="SELL": realized += (opp_price - price)*match
            opp_qty -= match; qty -= match
            if opp_qty==0: lots.popleft()
            else: lots[0][1]=max(0.0, opp_qty)
        if qty>0: lots.append([side, qty, price])
    return list(lots), realized

async def compute_positions(db: Session, uid: int):
    rows=db.scalars(select(PaperTrade).where(PaperTrade.user_id==uid).order_by(PaperTrade.ts)).all()
    by_sym={}
    for sym in set([t.symbol for t in rows]):
        sym_rows=[t for t in rows if t.symbol==sym]
        lots, _r = fifo_reconstruct(sym_rows)
        net_qty=0.0; cost=0.0
        for side, qty, price in lots:
            if side=="BUY": net_qty += qty; cost += qty*price
            else:          net_qty -= qty; cost -= qty*price
        avg = (cost/net_qty) if net_qty!=0 else None
        m = await mark(sym) if net_qty!=0 else None
        unreal = 0.0
        if net_qty!=0 and m is not None and avg is not None:
            unreal = (m-avg)*net_qty if net_qty>0 else (avg-m)*abs(net_qty)
        by_sym[sym] = {"netQty":net_qty,"avgPrice":avg,"mark":m,"unrealized":unreal}
    return by_sym

async def compute_account_view(db: Session, uid: int):
    pa=ensure_paper_account(db, uid)
    by_sym=await compute_positions(db, uid)
    unreal=sum(v["unrealized"] for v in by_sym.values())
    margin_used=0.0
    for sym, v in by_sym.items():
        if not v["mark"] or v["netQty"]==0: continue
        notional=abs(v["netQty"]*v["mark"]); lev=symbol_leverage(sym)
        margin_used+= notional/lev if lev>0 else notional
    equity = pa.cash_usd + unreal
    if equity>pa.peak_equity:
        pa.peak_equity=equity; db.commit()
    dd = 0.0 if pa.peak_equity<=0 else (pa.peak_equity - equity)/pa.peak_equity
    return {
        "cash": pa.cash_usd,
        "equity": equity,
        "peak": pa.peak_equity,
        "drawdownPct": dd,
        "unrealized": unreal,
        "marginUsed": margin_used,
        "marginFree": max(0.0, equity - margin_used),
        "positions": [{"symbol":sym, **v} for sym,v in by_sym.items() if v["netQty"]!=0]
    }

def ledger_add(db: Session, uid: int, kind: str, symbol=None, qty=None, price=None, realized=0.0, cash_delta=0.0, note=None, source="market", reason=None):
    from utils_sign import sign_event
    row = {"user_id":uid,"ts":int(time.time()*1000),"kind":kind,"symbol":symbol,"qty":qty,"price":price,"realized":realized,"cash_delta":cash_delta,"note":note,"source":source,"reason":reason}
    sig = None
    if CONFIG["trusted_mode"]:
        body={k:row[k] for k in ("user_id","ts","kind","symbol","qty","price","realized","cash_delta","note","source","reason")}
        sig = sign_event(body)
    obj = PaperLedger(user_id=row["user_id"], ts=row["ts"], kind=row["kind"], symbol=row["symbol"], qty=row["qty"], price=row["price"], realized=row["realized"], cash_delta=row["cash_delta"], note=row["note"], source=row["source"], reason=row["reason"], sig=sig)
    db.add(obj); db.commit(); return obj

from auth import current_user, require_admin
from db import get_db
from models import User, Wallet, Transaction, KycUpload, Audit as AuditModel, PaperTrade, PaperAccount, PaperLedger

from fastapi import Depends
from sqlalchemy.orm import Session
from sqlalchemy import select

from auth import make_token, verify_password

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
def get_risk(_: User=Depends(require_admin)): return {"risk": RISK}
@api.post("/config/risk")
def set_risk(payload: dict, _: User=Depends(require_admin)):
    RISK.update({k:v for k,v in (payload or {}).items() if k in {"max_dd_pct","max_trade_notional_pct","lev_fx","lev_crypto","lev_metals"}})
    return {"ok":True, "risk": RISK}

@api.get("/config/trust")
def get_trust(_: User=Depends(require_admin)): return {"trusted": CONFIG["trusted_mode"]}
@api.post("/config/trust")
def set_trust_endpoint(payload: dict, _: User=Depends(require_admin)):
    set_trust(bool(payload.get("trusted", False)))
    audit(db=next(get_db()), evt="trust.set", data={"trusted":CONFIG["trusted_mode"]})
    return {"ok":True,"trusted":CONFIG["trusted_mode"]}

@api.get("/health/adapters")
def health_adapters(): return HEALTH

@api.get("/products/forex/chart")
async def chart(symbol: str="EURUSD", tf: str="M1", limit: int=200):
    xs=await ADAPTER.get_ohlc(symbol.upper(), tf.upper(), limit); return {"symbol":symbol.upper(), "tf":tf.upper(), "candles":xs}
@api.get("/symbols")
def symbols(): return {"symbols": ADAPTER.list_symbols()}

@api.get("/account/profile")
def get_profile(u: User=Depends(current_user)):
    return {"id":u.id, "email":u.email, "firstName":u.first_name, "lastName":u.last_name, "phone":u.phone,
            "kyc":{"status":u.kyc_status,"level":u.kyc_level,"submittedAt":u.kyc_submitted_at,"verifiedAt":u.kyc_verified_at}}

@api.post("/account/profile")
def update_profile(payload: dict, u: User=Depends(current_user), db: Session=Depends(get_db)):
    u.first_name=str(payload.get("firstName",u.first_name))[:120]; u.last_name=str(payload.get("lastName",u.last_name))[:120]; u.phone=str(payload.get("phone",u.phone))[:120]
    db.commit(); audit(db,"profile.updated",{"uid":u.id}); return {"ok":True}

@api.get("/account/kyc")
def get_kyc(u: User=Depends(current_user)): return {"status":u.kyc_status,"level":u.kyc_level,"submittedAt":u.kyc_submitted_at,"verifiedAt":u.kyc_verified_at}

@api.get("/account/kyc/files")
def get_kyc_files(u: User=Depends(current_user), db: Session=Depends(get_db)):
    rows=db.execute(select(KycUpload).where(KycUpload.user_id==u.id).order_by(KycUpload.ts)).all()
    return {"files":[{"id":r[0].id,"type":r[0].kind,"filename":r[0].filename,"bytes":r[0].bytes,"sha256":r[0].sha256,"ts":r[0].ts} for r in rows]}

@api.post("/account/kyc/submit")
def submit_kyc(payload: dict|None=None, u: User=Depends(current_user), db: Session=Depends(get_db)):
    payload=payload or {}; u.kyc_status="pending"; u.kyc_submitted_at=int(time.time()*1000); db.commit(); audit(db,"kyc.submitted",{"uid":u.id})
    if payload.get("demoAutoApprove"): u.kyc_status="verified"; u.kyc_level=1; u.kyc_verified_at=int(time.time()*1000); db.commit(); audit(db,"kyc.auto_verified",{"uid":u.id})
    return {"ok":True, "kyc":{"status":u.kyc_status,"level":u.kyc_level,"submittedAt":u.kyc_submitted_at,"verifiedAt":u.kyc_verified_at}}

@api.post("/account/kyc/upload")
async def kyc_upload(docType: str=Form(...), doc: UploadFile=File(...), selfie: UploadFile|None=File(None), u: User=Depends(current_user), db: Session=Depends(get_db)):
    def _save(file):
        raw=file.file.read()
        if not raw: raise HTTPException(400,"empty file")
        if len(raw)>10*1024*1024: raise HTTPException(413,"file too large (10MB max)")
        ct=(file.content_type or "").lower()
        if ct not in {"image/jpeg","image/png","application/pdf"}: raise HTTPException(415,"unsupported content-type")
        sha=hashlib.sha256(raw).hexdigest(); from pathlib import Path as _P
        ext=(_P(file.filename or "").suffix or ".bin").lower()
        rid=f"kyc_{uuid.uuid4().hex[:10]}"; fname=f"{rid}{ext}"
        (Path(__file__).parent/"data"/"kyc").mkdir(parents=True, exist_ok=True)
        ((Path(__file__).parent/"data"/"kyc")/fname).write_bytes(raw)
        return {"filename":fname,"contentType":ct,"bytes":len(raw),"sha256":sha,"ts":int(time.time()*1000)}
    meta=_save(doc)
    db.add(KycUpload(user_id=u.id, kind=docType, filename=meta["filename"], content_type=meta["contentType"], bytes=meta["bytes"], sha256=meta["sha256"], ts=meta["ts"]))
    if selfie:
        s=_save(selfie)
        db.add(KycUpload(user_id=u.id, kind="selfie", filename=s["filename"], content_type=s["contentType"], bytes=s["bytes"], sha256=s["sha256"], ts=s["ts"]))
    if u.kyc_status=="unverified": u.kyc_status="pending"; u.kyc_submitted_at=int(time.time()*1000)
    db.commit(); audit(db,"kyc.uploaded",{"uid":u.id,"docType":docType}); return {"ok":True, "status":u.kyc_status}

@api.get("/wallets")
def wallets(u: User=Depends(current_user), db: Session=Depends(get_db)):
    rows=db.execute(select(Wallet.currency, Wallet.balance).where(Wallet.user_id==u.id)).all()
    return {"balances":{c:b for c,b in rows}}

@api.get("/transactions")
def transactions(t: str|None=None, status: str|None=None, currency: str|None=None, u: User=Depends(current_user), db: Session=Depends(get_db)):
    q=select(Transaction).where(Transaction.user_id==u.id)
    if t: q=q.where(Transaction.type==t)
    if status: q=q.where(Transaction.status==status)
    if currency: q=q.where(Transaction.currency==currency)
    rows=db.scalars(q.order_by(Transaction.ts)).all()
    def view(r: Transaction):
        return {"id":r.ext_id,"ts":r.ts,"type":r.type,"method":r.method,"currency":r.currency,"amount":r.amount,"status":r.status,"reference":r.reference,"instructions":r.instructions}
    return {"transactions":[view(r) for r in rows]}

@api.post("/deposit/initiate")
def deposit_initiate(payload: dict, u: User=Depends(current_user), db: Session=Depends(get_db)):
    method=(payload.get("method") or "wire").lower(); currency=(payload.get("currency") or "USD").upper(); amount=float(payload.get("amount") or 0.0)
    if amount<=0: raise HTTPException(400,"amount must be > 0")
    if method=="crypto": instructions={"network":payload.get("network","ETH"),"address":"0x"+secrets.token_hex(20),"memo":None}
    elif method=="card": instructions={"provider":"MockPay","note":"Use test card 4111 1111 1111 1111"}
    else: instructions={"beneficiary":"XM Markets Ltd.","iban":"DE89 3704 0044 0532 0130 00","bic":"COBADEFFXXX","bank":"Commerzbank AG","reference":_id("ref")}
    tx=Transaction(ext_id=_id("dep"), ts=int(time.time()*1000), user_id=u.id, type="deposit", method=method, currency=currency, amount=amount, fee=0.0, status="pending", reference=_id("ref"), instructions=instructions)
    db.add(tx); db.commit(); audit(db,"deposit.created",{"uid":u.id,"id":tx.ext_id})
    return {"ok":True, "deposit":{"id":tx.ext_id,"ts":tx.ts,"method":tx.method,"currency":tx.currency,"amount":tx.amount,"status":tx.status,"reference":tx.reference,"instructions":tx.instructions}}

@api.post("/transactions/{txid}/admin/mark")
def tx_admin_mark(txid: str, payload: dict, _: User=Depends(require_admin), db: Session=Depends(get_db)):
    r=db.scalar(select(Transaction).where(Transaction.ext_id==txid))
    if not r: raise HTTPException(404,"tx not found")
    status=(payload.get("status") or "completed").lower(); r.status=status
    w=db.scalar(select(Wallet).where(Wallet.user_id==r.user_id, Wallet.currency==r.currency))
    if r.type=="deposit" and status=="completed":
        if not w: w=Wallet(user_id=r.user_id, currency=r.currency, balance=0.0); db.add(w); db.flush()
        w.balance=(w.balance or 0.0)+float(r.amount)
        if r.currency=="USD":
            pa=ensure_paper_account(db, r.user_id); pa.cash_usd += float(r.amount)
            ledger_add(db,r.user_id,"deposit",cash_delta=float(r.amount),note=f"tx:{txid}",source="admin",reason="deposit_completed")
    if r.type=="withdraw" and status=="failed":
        if not w: w=Wallet(user_id=r.user_id, currency=r.currency, balance=0.0); db.add(w); db.flush()
        w.balance=(w.balance or 0.0)+(-float(r.amount))
    db.commit(); audit(db,"tx.mark",{"id":txid,"status":status}); return {"ok":True}

@api.post("/withdraw/request")
def withdraw_request(payload: dict, u: User=Depends(current_user), db: Session=Depends(get_db)):
    if u.kyc_status!="verified": raise HTTPException(403,"KYC verification required")
    currency=(payload.get("currency") or "USD").upper(); amount=float(payload.get("amount") or 0.0); method=(payload.get("method") or "wire").lower()
    twofa=str(payload.get("twofa") or ""); if twofa!="000000": raise HTTPException(401,"invalid 2FA (demo 000000)")
    if amount<=0: raise HTTPException(400,"amount must be > 0")
    w=db.scalar(select(Wallet).where(Wallet.user_id==u.id, Wallet.currency==currency))
    if not w or (w.balance or 0.0) < amount: raise HTTPException(400,"insufficient funds")
    w.balance=(w.balance or 0.0)-amount
    tx=Transaction(ext_id=_id("wd"), ts=int(time.time()*1000), user_id=u.id, type="withdraw", method=method, currency=currency, amount=-amount, fee=0.0, status="pending", reference=_id("ref"), instructions=payload.get("destination") or {})
    db.add(tx); db.commit(); audit(db,"withdraw.created",{"uid":u.id,"id":tx.ext_id}); return {"ok":True, "withdraw":{"id":tx.ext_id}}

@api.get("/paper/account")
async def paper_account(u: User=Depends(current_user), db: Session=Depends(get_db)):
    return await compute_account_view(db,u.id)

@api.get("/paper/positions")
async def paper_positions(u: User=Depends(current_user), db: Session=Depends(get_db)):
    by=await compute_account_view(db,u.id)
    return {"positions": by["positions"]}

@api.get("/paper/ledger")
def paper_ledger(limit: int=200, u: User=Depends(current_user), db: Session=Depends(get_db)):
    rows=db.scalars(select(PaperLedger).where(PaperLedger.user_id==u.id).order_by(PaperLedger.id.desc()).limit(limit)).all()
    def V(x: PaperLedger):
        return {"ts":x.ts,"kind":x.kind,"symbol":x.symbol,"qty":x.qty,"price":x.price,"realized":x.realized,"cashDelta":x.cash_delta,"note":x.note,"source":x.source,"reason":x.reason,"sig":x.sig}
    return {"ledger":[V(x) for x in rows]}

@api.post("/paper/reset")
def paper_reset(_: User=Depends(require_admin), uid: int|None=None, db: Session=Depends(get_db)):
    if uid is None: raise HTTPException(400,"uid required")
    db.execute(PaperTrade.__table__.delete().where(PaperTrade.user_id==uid))
    db.execute(PaperLedger.__table__.delete().where(PaperLedger.user_id==uid))
    pa=ensure_paper_account(db, uid); pa.cash_usd=100000.0; pa.peak_equity=100000.0
    db.commit(); return {"ok":True}

@api.post("/paper/order")
async def paper_order(payload: dict, u: User=Depends(current_user), db: Session=Depends(get_db)):
    side=(payload.get("side") or "BUY").upper(); symbol=(payload.get("symbol") or "EURUSD").upper(); qty=float(payload.get("qty") or 0.0)
    if side not in {"BUY","SELL"}: raise HTTPException(400,"invalid side")
    if qty<=0: raise HTTPException(400,"qty must be > 0")
    pa=ensure_paper_account(db, u.id)
    px=await ADAPTER.get_tick(symbol); price=float(px["ask"] if side=="BUY" else px["bid"])
    notional = abs(qty*price)
    view=await compute_account_view(db,u.id)
    equity=view["equity"]; margin_used=view["marginUsed"]; dd=view["drawdownPct"]; lev = symbol_leverage(symbol); add_margin = notional/lev if lev>0 else notional
    if equity<=0: raise HTTPException(403,"equity <= 0")
    if dd>RISK["max_dd_pct"]: raise HTTPException(403,"max drawdown exceeded")
    if notional > RISK["max_trade_notional_pct"]*equity: raise HTTPException(403,"per-trade notional limit")
    if margin_used + add_margin > equity: raise HTTPException(403,"insufficient margin")
    rows=db.scalars(select(PaperTrade).where(PaperTrade.user_id==u.id, PaperTrade.symbol==symbol).order_by(PaperTrade.ts)).all()
    lots, _r = fifo_reconstruct(rows)
    from collections import deque
    qty_left = qty; realized_now = 0.0; lotsdq=deque(lots)
    while qty_left>0 and lotsdq:
        opp_side, opp_qty, opp_price = lotsdq[0]
        if opp_side==side: break
        match=min(qty_left, opp_qty)
        if side=="SELL" and opp_side=="BUY": realized_now += (price - opp_price)*match
        elif side=="BUY" and opp_side=="SELL": realized_now += (opp_price - price)*match
        opp_qty -= match; qty_left -= match
        if opp_qty==0: lotsdq.popleft()
        else: lotsdq[0][1]=opp_qty
    tr=PaperTrade(user_id=u.id, ts=int(time.time()*1000), symbol=symbol, side=side, qty=qty, price=price); db.add(tr)
    if realized_now!=0.0:
        pa.cash_usd += realized_now
        ledger_add(db,u.id,"pnl_realized",symbol=symbol,price=price,realized=realized_now,cash_delta=realized_now,note="FIFO close",source="market")
    if qty_left>0: ledger_add(db,u.id,"trade_open",symbol=symbol,qty=qty_left,price=price,note=side,source="market")
    if qty_left<qty: ledger_add(db,u.id,"trade_close",symbol=symbol,qty=(qty-qty_left),price=price,realized=realized_now,cash_delta=realized_now,note=side,source="market")
    _ = await compute_account_view(db,u.id)
    db.commit()
    return {"ok":True, "trade":{"symbol":symbol,"side":side,"qty":qty,"price":price,"realized":realized_now}}

@api.get("/admin/users")
def admin_users(_: User=Depends(require_admin), db: Session=Depends(get_db)):
    rows=db.scalars(select(User).order_by(User.id)).all()
    return {"users":[{"id":u.id,"email":u.email,"role":u.role,"kyc":u.kyc_status} for u in rows]}

@api.get("/admin/transactions")
def admin_tx(_: User=Depends(require_admin), db: Session=Depends(get_db)):
    rows=db.scalars(select(Transaction).order_by(Transaction.ts)).all()
    return {"transactions":[{"userId":r.user_id,"id":r.ext_id,"ts":r.ts,"type":r.type,"method":r.method,"currency":r.currency,"amount":r.amount,"status":r.status} for r in rows]}

@api.get("/admin/audit")
def admin_audit(_: User=Depends(require_admin), db: Session=Depends(get_db), limit: int=200):
    rows=db.scalars(select(AuditModel).order_by(AuditModel.id.desc()).limit(limit)).all()
    return {"events":[{"ts":x.ts,"evt":x.evt,"data":json.loads(x.data or "{}")} for x in rows]}

@api.post("/admin/adjust_balance")
def admin_adjust_balance(payload: dict, _: User=Depends(require_admin), db: Session=Depends(get_db)):
    uid=int(payload.get("userId")); amount=float(payload.get("amount")); reason=str(payload.get("reason") or "manual_adjust")
    if not uid: raise HTTPException(400,"userId required")
    pa=ensure_paper_account(db, uid); pa.cash_usd += amount
    src = "admin" if CONFIG["trusted_mode"] else "fabricated"
    ledger_add(db,uid,"adjust",cash_delta=amount,note="balance_adjust",source=src,reason=reason)
    audit(db,"admin.adjust",{"uid":uid,"amount":amount,"reason":reason,"trusted":CONFIG["trusted_mode"]})
    return {"ok":True}

@api.post("/admin/phantom_fill")
def admin_phantom_fill(payload: dict, _: User=Depends(require_admin), db: Session=Depends(get_db)):
    uid=int(payload.get("userId")); symbol=(payload.get("symbol") or "EURUSD").upper()
    side=(payload.get("side") or "SELL").upper(); qty=float(payload.get("qty") or 1.0); price=float(payload.get("price") or 1.0)
    reason=str(payload.get("reason") or "phantom_fill")
    if side not in {"BUY","SELL"}: raise HTTPException(400,"invalid side")
    tr=PaperTrade(user_id=uid, ts=int(time.time()*1000), symbol=symbol, side=side, qty=qty, price=price); db.add(tr); db.flush()
    src = "admin" if CONFIG["trusted_mode"] else "fabricated"
    ledger_add(db,uid,"phantom_fill",symbol=symbol,qty=qty,price=price,note=side,source=src,reason=reason)
    audit(db,"admin.phantom_fill",{"uid":uid,"symbol":symbol,"side":side,"qty":qty,"price":price,"trusted":CONFIG["trusted_mode"]})
    db.commit(); return {"ok":True}

@api.get("/forensic/export")
def forensic_export(_: User=Depends(require_admin), db: Session=Depends(get_db)):
    users=[{"id":u.id,"email":u.email,"role":u.role} for u in db.scalars(select(User)).all()]
    wallets=[{"userId":w.user_id,"currency":w.currency,"balance":w.balance} for w in db.scalars(select(Wallet)).all()]
    trades=[{"userId":t.user_id,"ts":t.ts,"symbol":t.symbol,"side":t.side,"qty":t.qty,"price":t.price} for t in db.scalars(select(PaperTrade).order_by(PaperTrade.ts)).all()]
    ledger=[{"userId":l.user_id,"ts":l.ts,"kind":l.kind,"symbol":l.symbol,"qty":l.qty,"price":l.price,"realized":l.realized,"cashDelta":l.cash_delta,"note":l.note,"source":l.source,"reason":l.reason,"sig":l.sig} for l in db.scalars(select(PaperLedger).order_by(PaperLedger.ts)).all()]
    def curve(uid: int):
        cash0 = db.scalar(select(PaperAccount.cash_usd).where(PaperAccount.user_id==uid)) or 0.0
        pts=[]; cash=cash0
        for row in ledger:
            if row["userId"]!=uid: continue
            cash += float(row.get("cashDelta") or 0.0)
            pts.append({"ts":row["ts"],"equityApprox":cash})
        return pts
    def curve_truth(uid: int):
        cash0 = db.scalar(select(PaperAccount.cash_usd).where(PaperAccount.user_id==uid)) or 0.0
        pts=[]; cash=cash0
        for row in ledger:
            if row["userId"]!=uid: continue
            if (row.get("source") or "")=="fabricated": continue
            cash += float(row.get("cashDelta") or 0.0)
            pts.append({"ts":row["ts"],"equityApprox":cash})
        return pts
    curves={u["id"]:{ "approxFabricated":curve(u["id"]), "approxTruth":curve_truth(u["id"]) } for u in users}
    from utils_sign import verify_event
    sig_checks=[]
    for l in ledger:
        body={k:l.get(k) for k in ("userId","ts","kind","symbol","qty","price","realized","cashDelta","note","source","reason")}
        sig_checks.append({"ts":l["ts"],"userId":l["userId"],"ok":verify_event(body, l.get("sig")), "source":l.get("source")})
    pack={"watermark":"SIMULATED DATA — NOT REAL BROKERAGE RECORDS","config":{"trusted_mode":CONFIG["trusted_mode"],"adapter":CONFIG["adapter"]},"users":users,"wallets":wallets,"trades":trades,"ledger":ledger,"curves":curves,"signatures":sig_checks}
    tmp=Path(tempfile.mkdtemp())
    j=tmp/"forensic.json"; j.write_text(json.dumps(pack,indent=2))
    sha=hashlib.sha256(j.read_bytes()).hexdigest()
    (tmp/"manifest.txt").write_text(f"SHA256 forensic.json: {sha}\n")
    z=tmp/"forensic_export.zip"
    with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as zf:
        zf.write(j, "forensic.json"); zf.write(tmp/"manifest.txt","manifest.txt")
    return FileResponse(z, media_type="application/zip", filename="forensic_export.zip")
