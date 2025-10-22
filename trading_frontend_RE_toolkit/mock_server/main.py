
from fastapi import FastAPI, Query
from fastapi.responses import PlainTextResponse
from pathlib import Path
import json, time

app = FastAPI(title="Mock Products API")

DATA = Path(__file__).parent / "data"
USER = json.loads((DATA / "user.json").read_text(encoding="utf-8"))
PARTNER = json.loads((DATA / "partner.json").read_text(encoding="utf-8"))
TIMES = json.loads((DATA / "trading_times.json").read_text(encoding="utf-8"))
CHARTS = json.loads((DATA / "charts.json").read_text(encoding="utf-8"))

@app.get("/health")
def health():
    return {"ok": True, "ts": int(time.time())}

# JSONP login: /products/account/login?email=...&password=...&callback=cb
@app.get("/products/account/login", response_class=PlainTextResponse)
def login(email: str = "", password: str = "", callback: str = "callback"):
    payload = json.dumps({"status":"ok","user":USER})
    body = f"{callback}({payload});"
    return body

@app.get("/products/account/partner")
def partner():
    return PARTNER

# Quotes + trading times: /products/forex/update?symbols=EURUSD,GBPUSD
@app.get("/products/forex/update")
def forex_update(symbols: str = Query(default="EURUSD")):
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    quotes = {}
    now = int(time.time()*1000)
    for s in syms:
        quotes[s] = {
            "symbol": s,
            "bid": 1.12345, "ask": 1.12365, "ts": now,
            "trading_times": TIMES.get(s, {"open":"00:00","close":"23:59","trading": True})
        }
    return {"quotes": quotes}

# OHLC: /products/forex/chart?symbol=EURUSD&tf=M1&limit=200
@app.get("/products/forex/chart")
def forex_chart(symbol: str = "EURUSD", tf: str = "M1", limit: int = 200):
    symbol = symbol.upper()
    tf = tf.upper()
    series = CHARTS.get(symbol, {}).get(tf, [])
    if limit > 0:
        series = series[-limit:]
    return {"symbol": symbol, "tf": tf, "candles": series}
