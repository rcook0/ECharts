# Windows quickstart

1) **Install Docker Desktop** (WSL2 backend) — run:
```powershell
.\deploy\win\install-docker.ps1
```
You may be prompted to reboot after enabling WSL/VM Platform.

2) **Bring stack up**:
```powershell
.\deploy\win\deploy.ps1 -ProjectDir .
```

3) **Optional post-config**:
```powershell
.\deploy\win\postconfigure.ps1 -Endpoint http://localhost:8080/api -Adapter ccxt -Exchange binance
```
