@echo off
setlocal
cd /d %~dp0

python -m pip install -r requirements.txt || goto :err
python tools\make_icon.py || goto :err
if not exist core\mihomo.exe python tools\fetch_core.py || goto :err

python -m PyInstaller --noconfirm --clean --windowed --name KumoRoute ^
  --icon assets\icon.ico ^
  --add-data "ui;ui" ^
  --add-data "assets;assets" ^
  --hidden-import pystray._win32 ^
  --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module PySide2 --exclude-module PySide6 ^
  --exclude-module numpy --exclude-module matplotlib --exclude-module scipy --exclude-module pandas ^
  --exclude-module tkinter ^
  --distpath ..\dist --workpath ..\build app.py || goto :err

if not exist ..\dist\KumoRoute\core mkdir ..\dist\KumoRoute\core
copy /y core\mihomo.exe ..\dist\KumoRoute\core\ >nul
copy /y core\geoip.metadb ..\dist\KumoRoute\core\ >nul
copy /y core\geosite.dat ..\dist\KumoRoute\core\ >nul
copy /y core\LICENSE-GPL3.txt ..\dist\KumoRoute\core\ >nul
echo.
echo Build OK: ..\dist\KumoRoute\KumoRoute.exe
exit /b 0

:err
echo Build FAILED
exit /b 1
