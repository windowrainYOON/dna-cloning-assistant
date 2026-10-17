#!/usr/bin/env bash
# Build the macOS app bundle and a .dmg for Apple Silicon.
#
#   ./build/build_macos.sh            # -> ~/Desktop/DNA-Cloning-Assistant_v<ver>_apple-silicon.dmg
#   OUTPUT_DIR=. ./build/build_macos.sh
#
# Run it from the repository root on an Apple Silicon Mac with Python 3.10+
# whose tkinter is backed by Tk 8.6 or newer. macOS's own /usr/bin/python3
# carries Apple's Tk 8.5.9, which refuses to open a window on recent macOS
# ("macOS 15 (1507) or later required") and produces an app that quits the
# moment it starts, so the interpreter is checked before anything is bundled.
# A uv-managed python or a Homebrew python with python-tk both work:
#
#   PYTHON="$(uv python find 3.12)" ./build/build_macos.sh
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

# The interface is tkinter, and tkinter cannot be installed with pip: the Tk it
# binds to is whatever the interpreter itself was built against. Check that it
# is new enough to open a window before spending a build on it.
TK_INFO="$("$PYTHON" - <<'PYTK' 2>/dev/null || true
import sys
try:
    import tkinter
except Exception:
    print("%d.%d none" % sys.version_info[:2])
else:
    print("%d.%d %s" % (*sys.version_info[:2], tkinter.TkVersion))
PYTK
)"
PY_VER="${TK_INFO%% *}"
TK_VER="${TK_INFO##* }"
py_ok=0; tk_ok=0
case "$PY_VER" in 3.1[0-9]|3.[2-9][0-9]|[4-9].*) py_ok=1 ;; esac
case "$TK_VER" in 8.6|8.7|9.*|1[0-9].*) tk_ok=1 ;; esac
if [[ "$py_ok" != 1 || "$tk_ok" != 1 ]]; then
  echo "이 파이썬으로는 빌드할 수 없습니다: $PYTHON (Python ${PY_VER}, Tk ${TK_VER})"
  echo "Python 3.10 이상, Tk 8.6 이상이 필요합니다."
  echo "macOS 기본 /usr/bin/python3는 Tk 8.5.9라서 앱이 실행 직후 종료됩니다."
  echo "예: PYTHON=\"\$(uv python find 3.12)\" ./build/build_macos.sh"
  echo "또는 brew install python-tk 후 PYTHON=/opt/homebrew/bin/python3.12 ./build/build_macos.sh"
  exit 1
fi
echo "==> 빌드 파이썬: $PYTHON (Python ${PY_VER}, Tk ${TK_VER})"

# A venv left behind by a different interpreter would quietly bundle that one.
BASE="$("$PYTHON" -c 'import sys; print(sys.base_prefix)')"
if [[ -d "$VENV" ]] && [[ "$("$VENV/bin/python" -c 'import sys; print(sys.base_prefix)' 2>/dev/null)" != "$BASE" ]]; then
  echo "==> 다른 파이썬으로 만든 가상환경을 다시 만듭니다"
  rm -rf "$VENV"
fi
if [[ ! -d "$VENV" ]]; then
  echo "==> 빌드용 가상환경을 만듭니다"
  "$PYTHON" -m venv "$VENV"
fi
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet "pyinstaller>=6.6"

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
