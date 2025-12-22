# ZeroMQ MT5 stub for local dev
import sys, time, json, random
import zmq
port = int(sys.argv[1] if len(sys.argv)>1 else 5555)
ctx = zmq.Context.instance()
sock = ctx.socket(zmq.REP); sock.bind(f"tcp://127.0.0.1:{port}")
prices = {"EURUSD":1.1010,"BTCUSD":65050.0,"XAUUSD":2048.0}
print(f"[stub] listening on tcp://127.0.0.1:{port}")
while True:
    req = json.loads(sock.recv_string()); op=req.get("op"); sym=(req.get("symbol") or "EURUSD").upper(); now=int(time.time()*1000)
    if op=="tick":
        p=prices.get(sym,1.0); p=max(0.0001, p+(random.random()-0.5)*(0.0008 if p<10 else 5.0 if p<2000 else 6.0)); prices[sym]=p
        sock.send_string(json.dumps({"t":now,"symbol":sym,"bid":p,"ask":p+(0.00005 if p<10 else 1.0 if p<2000 else 0.8)})); continue
    if op=="ohlc":
        step=60; t0=int(time.time()//step*step)-step*199; out=[]; last=prices.get(sym,1.0)
        for i in range(200):
            d=(random.random()-0.5)*(0.001 if last<10 else 15.0 if last<2000 else 6.0)
            o=last; c=o+d; h=max(o,c)+abs(d)*random.random(); l=min(o,c)-abs(d)*random.random()
            out.append({"t":(t0+i*step)*1000,"o":float(o),"h":float(h),"l":float(l),"c":float(c)}); last=c
        sock.send_string(json.dumps({"candles":out})); continue
    sock.send_string(json.dumps({"error":"unknown op"}))
