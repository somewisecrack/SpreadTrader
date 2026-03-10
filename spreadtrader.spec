# -*- mode: python ; coding: utf-8 -*-
#
# spreadtrader.spec — macOS Build Spec for SpreadTrader
#
# Run from the project directory:
#     pyinstaller spreadtrader.spec
#
# Output: dist/SpreadTrader.app
# Then copy to Desktop:
#     cp -R dist/SpreadTrader.app ~/Desktop/

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('app_icon.icns', '.'),
        ('app_icon.png',  '.'),
    ],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
        'NorenRestApiPy',
        'NorenRestApiPy.NorenApi',
        'websocket',
        'websocket._app',
        'websocket._core',
        'pyotp',
        'certifi',
        'dotenv',
        'pytz',
        'sqlite3',
        'logging.handlers',
        'requests',
        'csv',
        'json',
    ],

    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'IPython', 'jupyter'],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SpreadTrader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # no terminal window
    icon='app_icon.icns',
)

# macOS .app bundle
app = BUNDLE(
    exe,

    name='SpreadTrader.app',
    icon='app_icon.icns',
    bundle_identifier='com.spreadtrader.app',
    info_plist={
        'CFBundleName':             'SpreadTrader',
        'CFBundleDisplayName':      'SpreadTrader',
        'CFBundleVersion':          '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable':  True,
        'NSRequiresAquaSystemAppearance': False,  # supports Dark Mode
        'LSMinimumSystemVersion':   '11.0',       # macOS Big Sur+
        'NSHumanReadableCopyright': '© 2025 SpreadTrader',
    },
)
