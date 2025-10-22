
# Mock Endpoints for `/products/*`

Purpose: run the WL front-end offline or against safe fixtures. Implements:
- `/products/account/login` (JSONP)
- `/products/account/partner`
- `/products/forex/update`
- `/products/forex/chart`

## Quickstart
```bash
python -m venv .venv && . .venv/bin/activate  # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt
uvicorn main:app --port 8080 --reload
```

## Pointing the UI at this mock
Options (pick one):
1. **DevTools overrides**: Rewrite requests from `https://whitelabelrobot.com/products/...` to `http://127.0.0.1:8080/products/...` with a rewrite plugin/proxy.
2. **Runtime stubs** (see `../patches/hook.js`): block sockets and partner redirects.
3. **Hosts file** (heavy-handed): map `whitelabelrobot.com` → `127.0.0.1` only if you fully control/test the impact.

## Endpoints
- `GET /products/account/login?email=...&password=...&callback=cb` → JSONP `cb({ ...user })`
- `GET /products/account/partner` → current partner/broker fixture
- `GET /products/forex/update?symbols=EURUSD,GBPUSD` → quotes + trading times
- `GET /products/forex/chart?symbol=EURUSD&tf=M1&limit=200` → OHLC sample

Fixtures live under `./data`. Tweak as needed.
