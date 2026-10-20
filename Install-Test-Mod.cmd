@echo off
if "%~1"=="" goto usage
python "%~dp0score.py" setup --game-dir "%~1" --mode test
exit /b %errorlevel%
:usage
echo Drag your Arx game-data folder onto this file, or pass its path as an argument.
echo Requires Python 3.10+ and Arx Libertatis arxunpak in that folder.
pause
exit /b 1
