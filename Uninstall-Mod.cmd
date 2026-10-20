@echo off
if "%~1"=="" goto usage
python "%~dp0score.py" uninstall --game-dir "%~1"
exit /b %errorlevel%
:usage
echo Drag your Arx game-data folder onto this file, or pass its path as an argument.
pause
exit /b 1
