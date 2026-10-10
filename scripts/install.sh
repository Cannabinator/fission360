#!/usr/bin/env bash
# Install Fission360 for the current user on Ubuntu/Debian (no root needed for
# the app itself; system GL/X libraries are installed with sudo if missing).
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
PREFIX="${PREFIX:-$HOME/.local}"
VENV="$PREFIX/share/fission360/venv"

if command -v apt-get >/dev/null 2>&1 && [ "${SKIP_APT:-0}" != "1" ]; then
  PKGS="python3-venv python3-pip libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 \
libxcb-keysyms1 libxcb-image0 libxcb-render-util0 libxcb-xinerama0 libxcb-shape0 libfontconfig1 fontconfig fonts-dejavu-core"
  MISSING=$(for p in $PKGS; do dpkg -s "$p" >/dev/null 2>&1 || echo "$p"; done)
  if [ -n "$MISSING" ]; then
    echo "Installing system packages: $MISSING"
    sudo apt-get update && sudo apt-get install -y $MISSING
  fi
fi

python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install "$HERE"

mkdir -p "$PREFIX/bin" "$PREFIX/share/applications" "$PREFIX/share/icons/hicolor/scalable/apps" "$PREFIX/share/mime/packages"
ln -sf "$VENV/bin/fission360" "$PREFIX/bin/fission360"
install -m644 "$HERE/packaging/fission360.desktop" "$PREFIX/share/applications/fission360.desktop"
install -m644 "$HERE/packaging/fission360.svg" "$PREFIX/share/icons/hicolor/scalable/apps/fission360.svg"
install -m644 "$HERE/packaging/fission360-mime.xml" "$PREFIX/share/mime/packages/fission360.xml"
command -v update-mime-database >/dev/null && update-mime-database "$PREFIX/share/mime" || true
command -v update-desktop-database >/dev/null && update-desktop-database "$PREFIX/share/applications" || true

echo
echo "Fission360 installed. Run 'fission360' (make sure $PREFIX/bin is on your PATH) or launch it from the app menu."
