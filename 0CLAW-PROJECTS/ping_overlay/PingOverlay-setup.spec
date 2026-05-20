# -*- mode: python ; coding: utf-8 -*-
# PingOverlay — onedir build for the installable (Setup) edition.
#
# Installed directory layout:
#   %ProgramFiles%\PingOverlay\
#   ├── PingOverlay.exe
#   └── _internal\
#       ├── [Python runtime: python3xx.dll, *.pyd, *.dll]   ← flat, PyInstaller-managed
#       ├── assets\
#       │   ├── icons\     icon.png  wwm-logo.png
#       │   ├── images\    donate-pp.png  join-dc.png  en-vi.png
#       │   ├── tabs\      (tab icons)
#       │   ├── bar\       (bar icons)
#       │   ├── buttons\   btn-on.png  btn-off.png
#       │   ├── cursors\   arrow.cur
#       │   └── audio\     UI_Click.wav  UI_Alert.wav
#       ├── bin\
#       │   └── PresentMon.exe
#       ├── data\
#       │   ├── config.json
#       │   ├── internal_config.json
#       │   ├── events.json
#       │   └── wwm_wandering_tales.json
#       ├── wwm_quest\data\wwm_quest_full.json
#       └── wwm_encounter\data\wwm_encounters.json

from pathlib import Path
from PyInstaller.utils.hooks import collect_all

datas    = []
binaries = []
hiddenimports = [
    'config', 'hotkey', 'autostart', 'metrics', 'events', 'resources',
    'app_version',
    'net_utils', 'overlay', 'window_utils', 'fps', 'system_tweaks',
    'wwm_tales', 'wwm_tales.overlay', 'wwm_tales.hotkeys',
    'wwm_tales.ocr', 'wwm_tales.library', 'wwm_tales.window_capture',
    'wwm_tales.scraper', 'wwm_tales.html_extract',
    'wwm_quest', 'wwm_quest.scraper', 'wwm_quest.library',
    'wwm_encounter', 'wwm_encounter.scraper', 'wwm_encounter.library',
    'license_lib', 'license_check', 'license_admin', 'release_gateway',
    'ui_runtime', 'account_sync',
]

# ── External executable ───────────────────────────────────────────────────────
datas += [('bin\\PresentMon.exe', 'bin')]

# ── Icons ─────────────────────────────────────────────────────────────────────
datas += [
    ('icon.png',      'assets\\icons'),
    ('wwm-logo.png',  'assets\\icons'),
]

# ── Images ────────────────────────────────────────────────────────────────────
datas += [
    ('donate-pp.png', 'assets\\images'),
    ('join-dc.png',   'assets\\images'),
    ('en-vi.png',     'assets\\images'),
]

# ── Tab icons ─────────────────────────────────────────────────────────────────
datas += [
    ('tab-ico\\icon.png',  'assets\\tabs'),
    ('tab-ico\\tweak.png', 'assets\\tabs'),
]

# ── Bar icons ─────────────────────────────────────────────────────────────────
datas += [
    ('bar-ico\\envi-swap.png', 'assets\\bar'),
    ('bar-ico\\about.png',     'assets\\bar'),
    ('bar-ico\\setting.png',   'assets\\bar'),
    ('bar-ico\\help-ico.png',  'assets\\bar'),
    ('bar-ico\\minimize.png',  'assets\\bar'),
    ('bar-ico\\close.png',     'assets\\bar'),
    ('bar-ico\\userico.png',   'assets\\bar'),
]

# ── GUI buttons ───────────────────────────────────────────────────────────────
datas += [
    ('gui-btn\\btn-on.png',  'assets\\buttons'),
    ('gui-btn\\btn-off.png', 'assets\\buttons'),
]

# ── Cursors ───────────────────────────────────────────────────────────────────
datas += [('gui-cursors\\arrow.cur', 'assets\\cursors')]

# ── Audio ─────────────────────────────────────────────────────────────────────
datas += [
    ('ui-audio\\UI_Click.wav', 'assets\\audio'),
    ('ui-audio\\UI_Alert.wav', 'assets\\audio'),
]

# ── Bundled data files ────────────────────────────────────────────────────────
datas += [
    ('events.json',         'data'),
    ('config.json',         'data'),
    ('internal_config.json','data'),
]
datas += [('data\\wwm_wandering_tales.json', 'data')]
datas += [('wwm_quest\\data\\wwm_quest_full.json',      'wwm_quest\\data')]
datas += [('wwm_encounter\\data\\wwm_encounters.json',  'wwm_encounter\\data')]

# ── Third-party package assets ───────────────────────────────────────────────
tmp_ret = collect_all('pystray')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('PIL')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# ── Unused PIL format plugin modules (Python-level) ──────────────────────────
# Binary .pyd extensions (AVIF / WebP / CMS) are deleted post-build in
# build_setup.ps1 before manifest generation — PyInstaller's PIL hook
# bundles them regardless of the excludes list here.
# Match the binary strip above and remove other obscure format plugins.
# Kept: PNG, ICO, JPEG, BMP, GIF, TIFF, PPM, TGA, WebP stub — standard formats
# that Windows users may encounter; everything else is removed.
_PIL_MODULE_STRIP = {
    'PIL.AvifImagePlugin',
    'PIL.WebPImagePlugin',
    'PIL.ImageCms',
    'PIL.BufrStubImagePlugin',    # meteorological
    'PIL.GribStubImagePlugin',    # meteorological
    'PIL.Hdf5StubImagePlugin',    # scientific HDF5
    'PIL.FtexImagePlugin',        # Valve 3-D texture
    'PIL.GdImageFile',            # GD library
    'PIL.MicImagePlugin',         # MS Image Composer
    'PIL.DcxImagePlugin',         # multi-page PCX
    'PIL.SgiImagePlugin',         # SGI
    'PIL.PcdImagePlugin',         # Kodak PhotoCD
    'PIL.FpxImagePlugin',         # FlashPix
    'PIL.WalImageFile',           # Quake WAL texture
    'PIL.ImtImagePlugin',         # IMIT
    'PIL.McIdasImagePlugin',      # McIDAS area
    'PIL.MpegImagePlugin',        # MPEG (stub)
    'PIL.XbmImagePlugin',         # X11 bitmap
    'PIL.report',                 # diagnostic only
}
hiddenimports = [h for h in hiddenimports if h not in _PIL_MODULE_STRIP]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=list(_PIL_MODULE_STRIP),
    noarchive=False,
    optimize=1,   # strip docstrings → smaller .pyc, slightly faster imports
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,          # onedir: binaries go to COLLECT
    name='PingOverlay',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon='wwm-logo.ico',
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='PingOverlay',
)
