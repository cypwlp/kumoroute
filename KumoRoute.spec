# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['client/app.py'],
    pathex=[],
    binaries=[],
    datas=[('client/ui', 'ui'), ('client/assets', 'assets'), ('client/update_helper.ps1', '.')],
    hiddenimports=['pystray._win32', 'backup_support'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'numpy', 'matplotlib', 'scipy', 'pandas', 'tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KumoRoute',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['client/assets/icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='KumoRoute',
)
