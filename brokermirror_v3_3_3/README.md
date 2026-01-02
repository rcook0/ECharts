# BrokerMirror v3.3.3

Adds **SignalMatrix** heatmap (EMA/RSI/MACD/CCI) + **server indicators** + **risk presets**.

- Heatmap `/signals/matrix` (symbols × indicators → -1/0/+1), click to focus chart
- `/indicators` compute endpoint with params (ema, rsi, macd, cci)
- Risk presets low/medium/high via `/config/risk/preset`
- ECharts UI updated: matrix panel + risk selector

Quickstart:
```bash
docker compose up --build
# http://localhost:8080
# Admin: admin@local / admin123
# User : demo@user.local / demo123
```
