import time, random, os
class BaseAdapter:
    name="base"
    def list_symbols(self): return []
    async def get_tick(self, symbol): raise NotImplementedError
    async def get_ohlc(self, symbol, tf="M1", limit=200): raise NotImplementedError
class MockAdapter(BaseAdapter):
    name="mock"
    def __init__(self): self.prices={"EURUSD":1.10,"BTCUSD":65000.0,"XAUUSD":2050.0}
    def list_symbols(self): return list(self.prices.keys())
    async def get_tick(self, symbol):
        p=self.prices.get(symbol,1.0); d=(random.random()-0.5)*(0.0008 if p<10 else 5.0 if p<2000 else 6.0)
        p=max(0.0001,p+d); self.prices[symbol]=p
        return {"t":int(time.time()*1000),"symbol":symbol,"bid":p,"ask":p+(0.00005 if p<10 else 1.0 if p<2000 else 0.8)}
    async def get_ohlc(self, symbol, tf="M1", limit=200):
        base=self.prices.get(symbol,1.0); step=60; t0=int(time.time()//step*step)-step*(limit-1)
        out=[]; last=base
        for i in range(limit):
            d=(random.random()-0.5)*(0.001 if base<10 else 15.0 if base<2000 else 6.0)
            o=last; c=o+d; h=max(o,c)+abs(d)*random.random(); l=min(o,c)-abs(d)*random.random()
            out.append({"t":(t0+i*step)*1000,"o":float(o),"h":float(h),"l":float(l),"c":float(c),"v":1.0}); last=c
        return out
class CCXTAdapter(BaseAdapter):
    name="ccxt"
    def __init__(self, exchange="binance", symbol_map=None):
        import ccxt; self.ex=getattr(ccxt, exchange)(); self.symbol_map=symbol_map or {"BTCUSD":"BTC/USDT","EURUSD":"EUR/USDT"}
    def list_symbols(self): return list(self.symbol_map.keys())
    def _x(self,s): return self.symbol_map.get(s,s)
    async def get_tick(self, symbol):
        import time
        t=self.ex.fetch_ticker(self._x(symbol)); bid=t.get("bid") or t.get("last"); ask=t.get("ask") or (bid and bid*1.0002)
        return {"t":int((t.get("timestamp") or time.time()*1000)),"symbol":symbol,"bid":float(bid),"ask":float(ask)}
    async def get_ohlc(self, symbol, tf="M1", limit=200):
        tf_map={"M1":"1m","M5":"5m","M15":"15m","H1":"1h","D1":"1d"}
        bars=self.ex.fetch_ohlcv(self._x(symbol), timeframe=tf_map.get(tf,"1m"), limit=limit)
        return [{"t":int(b[0]),"o":float(b[1]),"h":float(b[2]),"l":float(b[3]),"c":float(b[4])} for b in bars]
class MT5Adapter(BaseAdapter):
    name="mt5"
    def __init__(self, zmq_url=None):
        import zmq, time as _t
        self.zmq=zmq; self._t=_t; self.url=zmq_url or os.getenv("MT5_ZMQ_URL","tcp://127.0.0.1:5555")
        self.ctx=zmq.Context.instance(); self.sock=self.ctx.socket(zmq.REQ); self.sock.setsockopt(zmq.RCVTIMEO,1000); self.sock.connect(self.url)
        self._symbols=["EURUSD","BTCUSD","XAUUSD"]
    def list_symbols(self): return self._symbols
    def _req(self,payload):
        import json; self.sock.send_string(json.dumps(payload)); return json.loads(self.sock.recv_string())
    async def get_tick(self, symbol):
        rep=self._req({"op":"tick","symbol":symbol}); return {"t":rep.get("t") or int(self._t.time()*1000),"symbol":symbol,"bid":float(rep["bid"]),"ask":float(rep["ask"])}
    async def get_ohlc(self, symbol, tf="M1", limit=200):
        rep=self._req({"op":"ohlc","symbol":symbol,"tf":tf,"limit":limit}); return rep.get("candles", [])
