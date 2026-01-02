import time, random
class MockAdapter:
    def list_symbols(self):
        return ["EURUSD","GBPUSD","USDJPY","BTCUSD","XAUUSD"]
    async def get_tick(self, symbol):
        t=int(time.time()*1000); px=1.05+random.random()*0.1
        if "BTC" in symbol: px=42000+random.random()*1000
        if "XAU" in symbol: px=1900+random.random()*15
        return {"symbol":symbol,"bid":px*0.999,"ask":px*1.001,"t":t}
    async def get_ohlc(self, symbol, tf, limit):
        now=int(time.time()*1000); step=60000 if tf=="M1" else (5*60000 if tf=="M5" else 15*60000 if tf=="M15" else 3600000)
        base=1.05
        if "BTC" in symbol: base=42000
        if "XAU" in symbol: base=1900
        out=[]
        v=base
        for i in range(limit):
            ts=now-(limit-i)*step
            drift=(random.random()-0.5)*(0.002 if base<100 else base*0.0005)
            v=max(0.0001, v+drift)
            h=v*(1+random.random()*0.001); l=v*(1-random.random()*0.001); o=v*(1+random.random()*0.0005); c=v
            out.append({"t":ts,"o":o,"h":h,"l":l,"c":c,"v":random.random()*10})
        return out

class CCXTAdapter(MockAdapter):
    def __init__(self, exchange="binance", symbol_map=None): self.exchange=exchange; self.symbol_map=symbol_map or {}
class MT5Adapter(MockAdapter):
    def __init__(self, zmq_url=None): self.zmq_url=zmq_url
