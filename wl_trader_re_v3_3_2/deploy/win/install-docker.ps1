Param(
  [switch]$SkipWSL
)
$ErrorActionPreference = "Stop"
Write-Host "== Docker Desktop installer (Win11) ==" -ForegroundColor Cyan

function Test-Admin {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  $p = New-Object Security.Principal.WindowsPrincipal($id)
  return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
if (-not (Test-Admin)) {
  Write-Warning "Re-run PowerShell as Administrator."
  exit 1
}

if (-not $SkipWSL) {
  Write-Host "[1/4] Enabling WSL + VM Platform..." -ForegroundColor Yellow
  Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux -NoRestart | Out-Null
  Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -NoRestart | Out-Null
  Write-Host "   -> You may need to reboot after this step." -ForegroundColor DarkYellow
}

Write-Host "[2/4] Installing Docker Desktop via winget..." -ForegroundColor Yellow
try {
  winget install -e --id Docker.DockerDesktop --source winget --accept-package-agreements --accept-source-agreements
} catch {
  Write-Warning "winget install failed. Trying Chocolatey..."
  if (Get-Command choco -ErrorAction SilentlyContinue) {
    choco install docker-desktop -y
  } else {
    Write-Error "No winget or chocolatey. Install Docker Desktop manually: https://www.docker.com/products/docker-desktop/"
    exit 1
  }
}

Write-Host "[3/4] Starting Docker Desktop..." -ForegroundColor Yellow
$dockerExe = "$Env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
if (Test-Path $dockerExe) { Start-Process -FilePath $dockerExe }

Write-Host "[4/4] Verifying docker CLI..." -ForegroundColor Yellow
$ok=$false
for ($i=0; $i -lt 30; $i++) {
  try { docker version | Out-Null; $ok=$true; break } catch { Start-Sleep -Seconds 2 }
}
if ($ok) { Write-Host "[ok] Docker CLI responding." -ForegroundColor Green } else { Write-Warning "Docker not ready yet; open Docker Desktop and ensure WSL2 backend is enabled." }
