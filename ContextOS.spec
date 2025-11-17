# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Context OS macOS app.

Usage:
    pyinstaller ContextOS.spec
"""

import sys
import os
from pathlib import Path

# Import version from central version file
sys.path.insert(0, os.path.abspath(SPECPATH))
from version import __version__, APP_BUNDLE_ID

block_cipher = None

# Project root directory
project_root = os.path.abspath(SPECPATH)

# Collect data files
datas = [
    # Configuration files (will be copied to user directory on first run)
    (os.path.join(project_root, 'config', '*.yaml'), 'config'),

    # Prompt templates (read-only resources)
    (os.path.join(project_root, 'prompts', '*.txt'), 'prompts'),

    # App logos (for system tray icon and notifications)
    (os.path.join(project_root, 'docs', 'logo.png'), 'docs'),
    (os.path.join(project_root, 'docs', 'logo_menubar.png'), 'docs'),
    (os.path.join(project_root, 'docs', 'logo_icon.png'), 'docs'),
]

# Hidden imports for dynamically loaded modules
hiddenimports = [
    # Dynamically loaded adapters
    'adapters.events.clipboard',
    'adapters.stream.screenshot',
    'adapters.base',

    # Dynamically loaded tools
    'integrations.tools.builtin.llm_query',
    'integrations.tools.builtin.translator',
    'integrations.tools.builtin.calculator',

    # Interface modules
    'interfaces.macos_tray',

    # PyQt5 modules
    'PyQt5.QtSvg',
    'PyQt5.QtWidgets',
    'PyQt5.QtCore',
    'PyQt5.QtGui',

    # macOS native frameworks (pyobjc)
    'AppKit',
    'Foundation',
    'objc',

    # Core dependencies
    'yaml',
    'openai',
    'mistune',
    'sympy',

    # Image processing and screenshot
    'mss',
    'mss.darwin',
    'mss.base',
    'PIL',
    'PIL.Image',
    'imagehash',

    # Standard library modules sometimes missed
    'queue',
    'threading',
    'signal',
    'json',
    'datetime',
    'uuid',
    'base64',
    'io',
]

# Exclude unused PyQt5 modules to reduce app size
excludes = [
    'PyQt5.QtWebEngine',
    'PyQt5.QtWebEngineWidgets',
    'PyQt5.QtWebEngineCore',
    'PyQt5.QtMultimedia',
    'PyQt5.QtMultimediaWidgets',
    'PyQt5.QtBluetooth',
    'PyQt5.QtNfc',
    'PyQt5.QtPositioning',
    'PyQt5.QtLocation',
    'PyQt5.Qt3D',
    'PyQt5.Qt3DCore',
    'PyQt5.Qt3DExtras',
    'PyQt5.Qt3DInput',
    'PyQt5.Qt3DLogic',
    'PyQt5.Qt3DRender',
    'PyQt5.QtQuick',
    'PyQt5.QtQuickWidgets',
    'PyQt5.QtQml',
    'PyQt5.QtDesigner',
    'PyQt5.QtHelp',
    'PyQt5.QtSql',
    'PyQt5.QtTest',
    'PyQt5.QtXml',
    'PyQt5.QtXmlPatterns',
    # Other unnecessary modules
    'matplotlib',
    'numpy',
    'pandas',
    'scipy',
    'tkinter',
    'unittest',
    'test',
]

a = Analysis(
    [os.path.join(project_root, 'main.py')],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ContextOS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=os.path.join(project_root, 'build', 'entitlements.plist'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ContextOS',
)

# macOS app bundle
app = BUNDLE(
    coll,
    name='ContextOS.app',
    icon=os.path.join(project_root, 'build', 'icon.icns'),
    bundle_identifier=APP_BUNDLE_ID,
    version=__version__,
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': 'True',
        'CFBundleName': 'ContextOS',
        'CFBundleDisplayName': 'ContextOS',
        'CFBundleShortVersionString': __version__,
        'CFBundleVersion': __version__,
        'CFBundleIdentifier': APP_BUNDLE_ID,
        'CFBundlePackageType': 'APPL',
        'CFBundleSignature': '????',

        # macOS permissions descriptions
        'NSAppleEventsUsageDescription': 'ContextOS needs to monitor clipboard changes to provide intelligent assistance.',

        # Show in Dock (set to 1 for menu bar only app)
        'LSUIElement': '0',

        # Application category
        'LSApplicationCategoryType': 'public.app-category.productivity',

        # Minimum macOS version
        'LSMinimumSystemVersion': '10.14',
    },
)
