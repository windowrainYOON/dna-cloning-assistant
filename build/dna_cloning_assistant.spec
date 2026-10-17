# PyInstaller spec for the macOS app bundle (Apple Silicon).
#
#   pyinstaller --noconfirm build/dna_cloning_assistant.spec
#
# Run it from the repository root; build/build_macos.sh does that for you.

import os
import sys

sys.path.insert(0, os.path.abspath("."))
from app.version import APP_NAME, __version__  # noqa: E402

block_cipher = None

a = Analysis(
    ["../desktop_app.py"],
    pathex=[os.path.abspath(".")],
    binaries=[],
    datas=[("../app/static", "app/static")],
    hiddenimports=["objc", "Foundation", "AppKit", "WebKit"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc_data"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

ICON = os.path.abspath("assets/AppIcon.icns")

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="DNACloningAssistant",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    target_arch="arm64",
    icon=ICON,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, name="DNACloningAssistant",
)
app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon=ICON,
    bundle_identifier="com.windowrainyoon.dnacloningassistant",
    version=__version__,
    info_plist={
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        "LSUIElement": False,
    },
)
