Param(
  [string]$Endpoint = "http://localhost:8080/api",
  [ValidateSet("mock","ccxt","mt5")][string]$Adapter = "ccxt",
  [string]$Exchange = "binance"
)
$admin = @{ email="admin@local"; password="admin123" }
$tok = (Invoke-RestMethod -Method POST -Uri "$Endpoint/auth/login?email=$($admin.email)&password=$($admin.password)").token
$hdr = @{ Authorization="Bearer $tok"; "Content-Type"="application/json" }
Invoke-RestMethod -Method POST -Uri "$Endpoint/config/trust" -Headers $hdr -Body (@{trusted=$true}|ConvertTo-Json) | Out-Null
$payload = @{ type=$Adapter; params=@{ exchange=$Exchange; symbol_map=@{ BTCUSD="BTC/USDT"; EURUSD="EUR/USDT"; XAUUSD="XAU/USDT" } } } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method POST -Uri "$Endpoint/config/adapter" -Headers $hdr -Body $payload | Out-Null
Write-Host "[ok] Trust=ON, Adapter=$Adapter/$Exchange" -ForegroundColor Green
