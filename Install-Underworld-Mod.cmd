@echo off
if "%~1"=="" goto usage
if "%~2"=="" goto defaultassets
python "%~dp0score.py" setup --game-dir "%~1" --mode underworld --assets "%~2"
exit /b %errorlevel%
:defaultassets
python "%~dp0score.py" setup --game-dir "%~1" --mode underworld --assets "%~dp0assets"
exit /b %errorlevel%
:usage
echo Usage: Install-Underworld-Mod.cmd "Arx game-data folder" ["imported music folder"]
echo Import your music first; see docs/IMPORT.md.
pause
exit /b 1
