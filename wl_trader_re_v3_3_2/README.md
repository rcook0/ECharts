# WL Trader (RE) v3.3.2

This bundle merges the **full ECharts UI** with the v3.3.1 wiring:
- TRUSTED/LEGACY modes, HMAC signatures on ledger events
- Admin Adjust Balance / Phantom Fill
- KYC/Profile, Deposits/Withdrawals
- ECharts front‑end + socket.io live ticks
- Adapter switch (mock/ccxt/mt5) + health endpoint
- CCXT smoketest, MT5 ZMQ stub
- Pytest (signatures + risk)
- **Windows PowerShell**: Docker install + one‑shot deploy

> For analysis/education only. Not a real broker.

## Quickstart (any OS)
```bash
docker compose up --build
# open http://localhost:8080
# Admin: admin@local / admin123
# User : demo@user.local / demo123
```

## Windows one‑liner
```powershell
# PowerShell in this folder
.\deploy\win\install-docker.ps1   # installs Docker Desktop (winget), enables WSL2 (reboot may be required)
.\deploy\win\deploy.ps1 -ProjectDir .
# optional: .\deploy\win\postconfigure.ps1 -Adapter ccxt -Exchange binance
```
