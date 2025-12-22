Param(
  [string]$ProjectDir = ".",
  [string]$JwtSecret = "",
  [string]$SignSecret = ""
)
$ErrorActionPreference = "Stop"
function New-Hex([int]$bytes=32){ -join ((1..$bytes) | ForEach-Object { "{0:x2}" -f (Get-Random -Max 256) }) }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker Desktop required." }
if (-not $JwtSecret -or $JwtSecret.Length -lt 16) { $JwtSecret = (New-Hex 32) }
if (-not $SignSecret -or $SignSecret.Length -lt 16) { $SignSecret = (New-Hex 32) }
$envPath = Join-Path $ProjectDir ".env"
@"
WL_DB_URL=sqlite:///./data/db.sqlite3
WL_JWT_SECRET=$JwtSecret
WL_SIGN_SECRET=$SignSecret
"@ | Set-Content -NoNewline -Encoding UTF8 $envPath
Push-Location $ProjectDir
docker compose up --build -d
Pop-Location
# Post-config: TRUSTED + CCXT(binance)
$tok = (Invoke-RestMethod -Method POST -Uri "http://localhost:8080/api/auth/login?email=admin@local&password=admin123").token
$h = @{ Authorization = "Bearer $tok"; "Content-Type"="application/json" }
Invoke-RestMethod -Method POST -Uri "http://localhost:8080/api/config/trust" -Headers $h -Body (@{trusted=$true} | ConvertTo-Json) | Out-Null
$cfg = @{ type="ccxt"; params=@{ exchange="binance"; symbol_map=@{ BTCUSD="BTC/USDT"; EURUSD="EUR/USDT"; XAUUSD="XAU/USDT" } } } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method POST -Uri "http://localhost:8080/api/config/adapter" -Headers $h -Body $cfg | Out-Null
Write-Host "[ok] Stack up. TRUSTED on. Adapter=ccxt/binance." -ForegroundColor Green
