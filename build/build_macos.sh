#!/usr/bin/env bash
# Build the macOS app bundle and a .dmg for Apple Silicon.
#
#   ./build/build_macos.sh            # -> ~/Desktop/DNA-Cloning-Assistant_v<ver>_apple-silicon.dmg
#   OUTPUT_DIR=. ./build/build_macos.sh
#
# Run it from the repository root on an Apple Silicon Mac with Python 3.10+
# that has tkinter (python.org installer, or `brew install python-tk`).
# PyInstaller is installed into build/.venv by this script; nothing else is
# needed, and no browser engine is involved.
#
# After the dmg is written the app is also installed into /Applications,
# replacing the previous version. INSTALL=0 skips that.

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
OUTPUT_DIR="${OUTPUT_DIR:-$HOME/Desktop}"
VENV="$ROOT/build/.venv"
APP_NAME="DNA Cloning Assistant"
SLUG="DNA-Cloning-Assistant"

[[ "$(uname -s)" == "Darwin" ]] || { echo "macOS 전용 스크립트입니다."; exit 1; }
ARCH="$(uname -m)"
if [[ "$ARCH" != "arm64" ]]; then
  echo "경고: Apple Silicon(arm64)이 아닌 ${ARCH}에서 빌드하고 있습니다." >&2
fi

PYTHON="${PYTHON:-python3}"
# Read the version from the package itself rather than scraping the file, so a
# docstring quote cannot be picked up instead (that produced a dmg named _v"_).
VERSION="$("$PYTHON" -c 'import sys; sys.path.insert(0, "."); from app.version import __version__; print(__version__)')"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "버전을 읽지 못했습니다: '$VERSION'"; exit 1; }
echo "==> ${APP_NAME} ${VERSION} (${ARCH})"

if [[ ! -d "$VENV" ]]; then
  echo "==> 빌드용 가상환경을 만듭니다"
  "$PYTHON" -m venv "$VENV"
fi
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet "pyinstaller>=6.6"

# The interface is tkinter, so the interpreter being bundled must have it.
"$VENV/bin/python" -c "import tkinter" 2>/dev/null || {
  echo "이 파이썬에는 tkinter가 없습니다. python.org 설치본을 쓰거나 'brew install python-tk' 후"
  echo "PYTHON=/opt/homebrew/bin/python3.12 ./build/build_macos.sh 처럼 다시 실행하세요."
  exit 1
}

echo "==> 테스트"
"$PYTHON" -m unittest discover -s tests -q

echo "==> 앱 번들 빌드"
rm -rf "$ROOT/build/dist" "$ROOT/build/work"
"$VENV/bin/pyinstaller" --noconfirm \
  --distpath "$ROOT/build/dist" --workpath "$ROOT/build/work" \
  "$ROOT/build/dna_cloning_assistant.spec"

APP="$ROOT/build/dist/${APP_NAME}.app"
[[ -d "$APP" ]] || { echo "앱 번들이 만들어지지 않았습니다: $APP"; exit 1; }

# An ad-hoc signature keeps Gatekeeper from killing the unsigned bundle on the
# machine that built it. Distributing it further needs a Developer ID.
echo "==> ad-hoc 코드 서명"
codesign --force --deep --sign - "$APP"

DMG="${OUTPUT_DIR}/${SLUG}_v${VERSION}_apple-silicon.dmg"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"

echo "==> dmg 만들기"
mkdir -p "$OUTPUT_DIR"
rm -f "$DMG"
hdiutil create -volname "${APP_NAME} ${VERSION}" -srcfolder "$STAGE" \
  -ov -format UDZO "$DMG" >/dev/null

echo "==> 완료: $DMG"
ls -lh "$DMG"

if [[ "${INSTALL:-1}" == "1" ]]; then
  echo "==> /Applications 에 설치"
  rm -rf "/Applications/${APP_NAME}.app"
  ditto "$APP" "/Applications/${APP_NAME}.app"
  echo "설치 완료: /Applications/${APP_NAME}.app"
fi
