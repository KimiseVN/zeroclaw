# -*- mode: python ; coding: utf-8 -*-
# OptizNW — onefile build for the network optimizer companion app.
#
# Output: dist\OptizNW.exe
# Bundled into the PingOverlay installer alongside PingOverlay.exe.
#
# Build:
#   python -m PyInstaller --noconfirm --clean OptizNW.spec

from pathlib import Path

datas = [
    # App icon shown in title bar
    ('optiz-nw.png', '.'),
]

a = Analysis(
    ['optiz_nw.py'],
    pathex=[str(Path('.').resolve())],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unused large packages
        'numpy', 'pandas', 'matplotlib', 'scipy', 'sklearn',
        'IPython', 'jupyter', 'notebook',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='OptizNW',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,            # GUI app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Use the main app ico for the exe icon
    icon='wwm-logo.ico',
    version=None,
    uac_admin=True,           # Request UAC elevation (needed for TCP/IP tweaks)
)
