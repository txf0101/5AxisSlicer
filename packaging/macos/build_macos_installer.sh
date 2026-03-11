#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_EXE="${1:-python3}"
BUILD_SUPPORT="${REPO_ROOT}/packaging/build_support.py"
SPEC_PATH="${REPO_ROOT}/packaging/pyinstaller/5AxisSlicer.spec"
DIST_ROOT="${REPO_ROOT}/dist"
WORK_ROOT="${REPO_ROOT}/build/pyinstaller-macos"
INSTALLERS_DIR="${DIST_ROOT}/installers"
VERSION="$(${PYTHON_EXE} "${BUILD_SUPPORT}" --version)"
ARCH="$(uname -m)"
APP_DIST_DIR="${DIST_ROOT}/5AxisSlicer"
APP_BUNDLE="${APP_DIST_DIR}/5AxisSlicer.app"
DMG_ROOT="${REPO_ROOT}/build/macos/dmg-root"
PKG_ROOT="${REPO_ROOT}/build/macos/pkg-root"
DMG_PATH="${INSTALLERS_DIR}/5AxisSlicer-${VERSION}-macos-${ARCH}.dmg"
PKG_PATH="${INSTALLERS_DIR}/5AxisSlicer-${VERSION}-macos-${ARCH}.pkg"

mkdir -p "${INSTALLERS_DIR}"
"${PYTHON_EXE}" -m PyInstaller --noconfirm --clean --distpath "${DIST_ROOT}" --workpath "${WORK_ROOT}" "${SPEC_PATH}"

if [[ ! -d "${APP_BUNDLE}" ]]; then
    echo "App bundle not found: ${APP_BUNDLE}" >&2
    exit 1
fi

if [[ -n "${CODESIGN_IDENTITY:-}" ]]; then
    codesign --deep --force --options runtime --sign "${CODESIGN_IDENTITY}" "${APP_BUNDLE}"
fi

rm -rf "${DMG_ROOT}" "${PKG_ROOT}"
mkdir -p "${DMG_ROOT}" "${PKG_ROOT}"
cp -R "${APP_BUNDLE}" "${DMG_ROOT}/5AxisSlicer.app"
cp -R "${APP_BUNDLE}" "${PKG_ROOT}/5AxisSlicer.app"

rm -f "${DMG_PATH}" "${PKG_PATH}"
hdiutil create -volname "5AxisSlicer" -srcfolder "${DMG_ROOT}" -ov -format UDZO "${DMG_PATH}"
pkgbuild --root "${PKG_ROOT}" --install-location "/Applications" "${PKG_PATH}"

echo "macOS DMG created: ${DMG_PATH}"
echo "macOS PKG created: ${PKG_PATH}"
