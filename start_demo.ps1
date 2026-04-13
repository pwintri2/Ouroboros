#Requires -Version 5.1
<#
.SYNOPSIS
    Wintrip Ambient Sentinel — Windows Demo Starter (PowerShell)

.DESCRIPTION
    Maakt een Python venv aan, installeert dependencies, start de FastAPI backend
    en opent het dashboard automatisch in de standaardbrowser.

.USAGE
    Rechtsklik → "Uitvoeren met PowerShell"
    Of in een PowerShell-venster:
        Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
        .\start_demo.ps1
#>

$ErrorActionPreference = "Stop"

# ── Kleuren helper ───────────────────────────────────────────────────────────
function Write-Step  { param($msg) Write-Host "  [>] $msg"  -ForegroundColor Cyan    }
function Write-Ok    { param($msg) Write-Host "  [v] $msg"  -ForegroundColor Green   }
function Write-Warn  { param($msg) Write-Host "  [!] $msg"  -ForegroundColor Yellow  }
function Write-Fail  { param($msg) Write-Host "  [X] $msg"  -ForegroundColor Red     }

# ── Banner ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Wintrip Ambient Sentinel - NTSSM Demo" -ForegroundColor Cyan
Write-Host "  ──────────────────────────────────────" -ForegroundColor DarkCyan
Write-Host ""

# ── Paden ────────────────────────────────────────────────────────────────────
$Root   = Split-Path -Parent $MyInvocation.MyCommand.Path
$Ctrl   = Join-Path $Root "controller"
$Venv   = Join-Path $Root ".venv"
$Html   = Join-Path $Root "dashboard\index.html"
$Reqs   = Join-Path $Ctrl "requirements.txt"

# ── Python aanwezig? ─────────────────────────────────────────────────────────
Write-Step "Python controleren..."
try {
    $pyVersion = & python --version 2>&1
    Write-Ok "$pyVersion"
} catch {
    Write-Fail "Python niet gevonden. Download Python 3.10+ van https://python.org"
    Read-Host "Druk op Enter om af te sluiten"
    exit 1
}

# ── Virtuele omgeving ────────────────────────────────────────────────────────
$venvActivate = Join-Path $Venv "Scripts\Activate.ps1"
if (-not (Test-Path $venvActivate)) {
    Write-Step "Virtuele omgeving aanmaken in .venv..."
    python -m venv $Venv
    Write-Ok "Virtuele omgeving aangemaakt."
} else {
    Write-Ok "Bestaande virtuele omgeving gevonden."
}

Write-Step "Virtuele omgeving activeren..."
& $venvActivate
Write-Ok "Virtuele omgeving actief."

# ── Dependencies ─────────────────────────────────────────────────────────────
Write-Step "Dependencies installeren / controleren..."
& pip install -q -r $Reqs
if ($LASTEXITCODE -ne 0) {
    Write-Fail "pip install mislukt. Controleer je internetverbinding en requirements.txt."
    Read-Host "Druk op Enter om af te sluiten"
    exit 1
}
Write-Ok "Dependencies gereed."

# ── Backend starten in nieuw venster ─────────────────────────────────────────
Write-Step "FastAPI backend starten op http://127.0.0.1:8000..."
$backendCmd = "& '$venvActivate'; `$env:PYTHONPATH='$Root'; cd '$Ctrl'; python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000"
Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $backendCmd `
              -WindowStyle Normal

# ── Wacht op backend ─────────────────────────────────────────────────────────
Write-Step "Wachten op backend (max. 15 sec)..."
$ready = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 1
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($resp.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
    Write-Host "." -NoNewline
}
Write-Host ""

if ($ready) {
    Write-Ok "Backend is online."
} else {
    Write-Warn "Backend reageert nog niet — dashboard toch openen (offline-modus werkt ook)."
}

# ── Dashboard openen ─────────────────────────────────────────────────────────
if (Test-Path $Html) {
    Write-Step "Dashboard openen in browser..."
    Start-Process $Html
    Write-Ok "Dashboard geopend."
} else {
    Write-Warn "dashboard\index.html niet gevonden op: $Html"
}

Write-Host ""
Write-Host "  Demo gestart!" -ForegroundColor Green
Write-Host "  Backend : http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "  Frontend: $Html" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Sluit het PowerShell backend-venster om de server te stoppen." -ForegroundColor DarkGray
Write-Host ""
Read-Host "Druk op Enter om dit venster te sluiten"
