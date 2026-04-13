@echo off
REM ============================================================
REM  Wintrip Ambient Sentinel — Windows Demo Starter
REM  Gebruik: dubbelklik op start_demo.bat
REM ============================================================

setlocal EnableDelayedExpansion
title Wintrip Ambient Sentinel Demo

echo.
echo  ██╗    ██╗██╗███╗   ██╗████████╗██████╗ ██╗██████╗
echo  ██║    ██║██║████╗  ██║╚══██╔══╝██╔══██╗██║██╔══██╗
echo  ██║ █╗ ██║██║██╔██╗ ██║   ██║   ██████╔╝██║██████╔╝
echo  ██║███╗██║██║██║╚██╗██║   ██║   ██╔══██╗██║██╔═══╝
echo  ╚███╔███╔╝██║██║ ╚████║   ██║   ██║  ██║██║██║
echo   ╚══╝╚══╝ ╚═╝╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝
echo  Ambient Sentinel — NTSSM Demo
echo.

REM ── Controleer of Python beschikbaar is ─────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [FOUT] Python niet gevonden. Download Python 3.10+ van https://python.org
    pause
    exit /b 1
)
echo [OK] Python gevonden.

REM ── Bepaal de root-map (map waar dit script staat) ──────────
set "ROOT=%~dp0"
set "CTRL=%ROOT%controller"
set "VENV=%ROOT%.venv"
set "HTML=%ROOT%dashboard\index.html"

REM ── Maak virtuele omgeving aan als die er nog niet is ────────
if not exist "%VENV%\Scripts\activate.bat" (
    echo [INFO] Virtuele omgeving aanmaken in .venv...
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo [FOUT] Kon virtuele omgeving niet aanmaken.
        pause
        exit /b 1
    )
    echo [OK] Virtuele omgeving aangemaakt.
)

REM ── Activeer de virtuele omgeving ───────────────────────────
call "%VENV%\Scripts\activate.bat"
echo [OK] Virtuele omgeving actief.

REM ── Installeer / update afhankelijkheden ────────────────────
echo [INFO] Dependencies controleren / installeren...
pip install -q -r "%CTRL%\requirements.txt"
if errorlevel 1 (
    echo [FOUT] pip install mislukt. Controleer je internetverbinding.
    pause
    exit /b 1
)
echo [OK] Dependencies gereed.

REM ── Stel PYTHONPATH in ──────────────────────────────────────
set "PYTHONPATH=%ROOT%"

REM ── Start de FastAPI backend in een apart venster ───────────
echo [INFO] Backend starten op http://127.0.0.1:8000 ...
start "Wintrip Backend" cmd /k "cd /d "%CTRL%" && call "%VENV%\Scripts\activate.bat" && set PYTHONPATH=%ROOT% && python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000"

REM ── Wacht even zodat de server kan opstarten ────────────────
echo [INFO] Wachten op backend (3 seconden)...
timeout /t 3 /nobreak >nul

REM ── Open het dashboard in de standaardbrowser ───────────────
if exist "%HTML%" (
    echo [INFO] Dashboard openen in browser...
    start "" "%HTML%"
    echo [OK] Dashboard geopend: %HTML%
) else (
    echo [WAARSCHUWING] dashboard\index.html niet gevonden op: %HTML%
)

echo.
echo  ✅ Demo gestart!
echo     Backend : http://127.0.0.1:8000
echo     Frontend: %HTML%
echo.
echo  Sluit het "Wintrip Backend" venster om de server te stoppen.
echo  Druk op een toets om dit venster te sluiten.
pause >nul
