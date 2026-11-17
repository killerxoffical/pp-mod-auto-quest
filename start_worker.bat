@echo off
title PlayQuest Worker (Google Auto-Login Engine)
color 0A
if exist "%~dp0vps_worker.py" (
    cd /d "%~dp0"
) else (
    cd /d "%~dp0achievement_unlocker"
)

echo ========================================================
echo       PlayQuest Background Login Worker
echo ========================================================
echo Connecting to Render API via Cloudflare Bridge...
python vps_worker.py
pause
