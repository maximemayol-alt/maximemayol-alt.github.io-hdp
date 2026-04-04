@echo off
title Installation Bot Basketball O/U
color 0B

echo ========================================
echo   Installation du Bot Basketball O/U
echo ========================================
echo.

cd /d "%~dp0"

:: 1) Verifier Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe.
    echo Telecharge-le sur https://www.python.org/downloads/
    echo Coche "Add Python to PATH" pendant l'installation.
    pause
    exit /b 1
)
echo [OK] Python detecte.

:: 2) Installer les dependances
echo.
echo Installation des dependances...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERREUR] Installation des dependances echouee.
    pause
    exit /b 1
)
echo [OK] Dependances installees.

:: 3) Verifier le .env
if not exist .env (
    echo.
    echo [!] Fichier .env manquant. Creation...
    copy .env.example .env >nul
    echo [!] Edite le fichier .env avec tes tokens avant de lancer le bot.
    notepad .env
    pause
)
echo [OK] Fichier .env present.

:: 4) Empecher la mise en veille
echo.
echo Configuration anti-veille...
powershell -Command "powercfg /change standby-timeout-ac 0" >nul 2>&1
powershell -Command "powercfg /change standby-timeout-dc 0" >nul 2>&1
powershell -Command "powercfg /change hibernate-timeout-ac 0" >nul 2>&1
echo [OK] Mise en veille desactivee.

:: 5) Creer la tache planifiee (Task Scheduler)
echo.
echo Creation de la tache planifiee...
set SCRIPT_PATH=%~dp0keep_alive.bat

schtasks /create /tn "BettingBot" ^
    /tr "\"%SCRIPT_PATH%\"" ^
    /sc ONLOGON ^
    /rl HIGHEST ^
    /f >nul 2>&1

if errorlevel 1 (
    echo [!] Impossible de creer la tache auto. Lance keep_alive.bat manuellement.
) else (
    echo [OK] Tache "BettingBot" creee - le bot demarre a chaque connexion Windows.
)

echo.
echo ========================================
echo   Installation terminee !
echo.
echo   Pour lancer maintenant : keep_alive.bat
echo   Le bot demarrera aussi automatiquement
echo   a chaque demarrage de Windows.
echo ========================================
echo.
pause
