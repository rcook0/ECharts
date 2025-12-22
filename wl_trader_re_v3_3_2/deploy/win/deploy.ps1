Param(
  [string]$ProjectDir = ".",
  [string]$JwtSecret = "",
  [string]$SignSecret = ""
)
$ErrorActionPreference = "Stop"
Write-Host "== WL Trader (RE) v3.3.2 :: Windows bootstrap ==" -ForegroundColor Cyan
function New-Hex([int]$bytes=32){ -join ((1..$bytes) | ForEach-Object { "{0:x2}" -f (Get-Random -Max 256) }) }

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker Desktop is required (docker CLI not found)." }
docker version | Out-Null

if (-not $JwtSecret -or $JwtSecret.Length -lt 16) { $JwtSecret = (New-Hex 32) }
if (-not $SignSecret -or $SignSecret.Length -lt 16) { $SignSecret = (New-Hex 32) }

$envPath = Join-Path $ProjectDir ".env"
@"
WL_DB_URL=sqlite:///./data/db.sqlite3
WL_JWT_SECRET=$JwtSecret
WL_SIGN_SECRET=$SignSecret
"@ | Set-Content -NoNewline -Encoding UTF8 $envPath
Write-Host "[ok] .env written" -ForegroundColor Green

Push-Location $ProjectDir
try {
  docker compose up --build -d
  Write-Host "[ok] stack is up (http://localhost:8080)" -ForegroundColor Green
} finally {
  Pop-Location
}

# Post-config
$AdminEmail = "admin@local"
$AdminPass = "admin123"
$token = (Invoke-RestMethod -Method POST -Uri "http://localhost:8080/api/auth/login?email=$($AdminEmail)&password=$($AdminPass)").token
if (-not $token) { Write-Warning "Admin login failed; skip post-config."; exit 0 }
$headers = @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" }

Invoke-RestMethod -Method POST -Uri "http://localhost:8080/api/config/trust" -Headers $headers -Body (@{trusted=$true} | ConvertTo-Json) | Out-Null
$cfg = @{ type="ccxt"; params=@{ exchange="binance"; symbol_map=@{ BTCUSD="BTC/USDT"; EURUSD="EUR/USDT"; XAUUSD="XAU/USDT" } } } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method POST -Uri "http://localhost:8080/api/config/adapter" -Headers $headers -Body $cfg | Out-Null
Write-Host "[ok] TRUSTED mode enabled + CCXT(binance) configured" -ForegroundColor Green
