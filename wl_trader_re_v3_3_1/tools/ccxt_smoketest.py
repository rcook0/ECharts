import sys, json
import ccxt
ex = getattr(ccxt, (sys.argv[1] if len(sys.argv)>1 else "binance"))()
symbol = sys.argv[2] if len(sys.argv)>2 else "BTC/USDT"
print(json.dumps(ex.fetch_ticker(symbol), indent=2)[:2000])
