# Quick CCXT sanity check
# Usage: python tools/ccxt_smoketest.py binance BTC/USDT
import sys, json
import ccxt
ex = getattr(ccxt, (sys.argv[1] if len(sys.argv)>1 else "binance"))()
symbol = sys.argv[2] if len(sys.argv)>2 else "BTC/USDT"
t = ex.fetch_ticker(symbol)
print(json.dumps({k:t.get(k) for k in ("symbol","last","bid","ask","timestamp")}, indent=2))
