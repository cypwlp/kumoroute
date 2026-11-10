@echo off
setlocal
cd /d %~dp0

python -m pip install -r requirements.txt || goto :err
python tools\make_icon.py || goto :err
if not exist core\mihomo.exe python tools\fetch_core.py || goto :err

python -m PyInstaller --noconfirm --clean --windowed --name MyClash ^
  --icon assets\icon.ico ^
  --add-data "ui;ui" ^
  --add-data "assets;assets" ^
  --hidden-import pystray._win32 ^
  --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module PySide2 --exclude-module PySide6 ^
  --exclude-module numpy --exclude-module matplotlib --exclude-module scipy --exclude-module pandas ^
  --exclude-module tkinter ^
  --distpath ..\dist --workpath ..\build app.py || goto :err

if not exist ..\dist\MyClash\core mkdir ..\dist\MyClash\core
copy /y core\mihomo.exe ..\dist\MyClash\core\ >nul
copy /y core\LICENSE-GPL3.txt ..\dist\MyClash\core\ >nul
echo.
echo Build OK: ..\dist\MyClash\MyClash.exe
exit /b 0

:err
echo Build FAILED
exit /b 1
