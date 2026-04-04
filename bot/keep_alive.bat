@echo off
title Basketball O/U Bot - Keep Alive
color 0A

echo ========================================
echo   Basketball O/U Betting Bot
echo   Redemarrage automatique si crash
echo ========================================
echo.

cd /d "%~dp0"

:: Lancer l'anti-veille en arriere-plan
start /min powershell -ExecutionPolicy Bypass -File "%~dp0no_sleep.ps1"

:loop
echo [%date% %time%] Demarrage du bot...
python main.py
echo.
echo [%date% %time%] Le bot s'est arrete. Redemarrage dans 10 secondes...
timeout /t 10 /nobreak >nul
goto loop
