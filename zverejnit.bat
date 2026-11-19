@echo off
setlocal
cd /d "%~dp0"
set "PY="
for %%C in ("python" "py" "%USERPROFILE%\miniconda3\python.exe" "%USERPROFILE%\anaconda3\python.exe" "%USERPROFILE%\miniforge3\python.exe" "%LOCALAPPDATA%\miniconda3\python.exe" "%ProgramData%\miniconda3\python.exe" "%ProgramData%\anaconda3\python.exe") do (
  if not defined PY (
    "%%~C" -c "import PIL" >nul 2>nul && set "PY=%%~C"
  )
)
if not defined PY (
  echo Nenasel jsem Python s knihovnou Pillow.
  echo Otevri PowerShell v teto slozce a spust:  python build.py
  echo Pokud chybi Pillow:  pip install pillow
  pause
  exit /b 1
)
"%PY%" build.py
if errorlevel 1 (
  pause
  exit /b 1
)
git add -A
git commit -m "Aktualizace webu"
git push
echo.
echo Hotovo. Zmeny se na webu objevi behem nekolika minut.
pause
