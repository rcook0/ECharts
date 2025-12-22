# WL Trader (RE) v3.3.0

**What’s new**
- Dual-mode: `trusted_mode` (HMAC-signed mutations) vs. `legacy_mode` (faithful to white-label behavior, fabricated lines clearly flagged).
- Admin “scam controls” for **balance adjustments** and **phantom fills** (source=`fabricated` with reason codes).
- Admin endpoints wired: users, transactions, audit, trust mode toggle.
- Forensic export: truth curve vs fabricated curve, SHA256 manifest, watermark.

> This is a *local* analysis tool. It has **no real payments** and marks any fabricated data with `source:"fabricated"`. Do not connect to real customer flows.

## Quickstart
```bash
docker compose up --build
# open http://localhost:8080
# Admin: admin@local / admin123
# User : demo@user.local / demo123
```
