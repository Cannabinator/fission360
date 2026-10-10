#!/usr/bin/env bash
# Run Fission360 headless and expose it to a remote machine (e.g. Windows 11)
# through a web browser (noVNC) or any VNC client. Lightweight, for testing.
#
#   ./scripts/remote.sh                 # browser on http://localhost:6080 (via SSH tunnel)
#   ./scripts/remote.sh --public        # listen on all interfaces, password protected
#   ./scripts/remote.sh --size 1920x1080 --port 6080
#
# Windows 11 (PowerShell):  ssh -L 6080:localhost:6080 user@linux-host
#   then open http://localhost:6080/vnc.html?autoconnect=1&resize=scale
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
SIZE=1600x900
PORT=6080
VNC_PORT=5900
DISPLAY_NUM=99
PUBLIC=0
APPARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --size) SIZE="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --display) DISPLAY_NUM="$2"; shift 2 ;;
    --public) PUBLIC=1; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    -*) echo "unknown option $1"; exit 1 ;;
    *) APPARGS+=("$1"); shift ;;
  esac
done

need=""
for b in Xvfb x11vnc websockify; do command -v "$b" >/dev/null || need=1; done
[ -d /usr/share/novnc ] || need=1
if [ -n "$need" ]; then
  echo "Installing xvfb, x11vnc, novnc ..."
  SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO=sudo
  $SUDO apt-get update && $SUDO apt-get install -y xvfb x11vnc novnc websockify libgl1-mesa-dri
fi

# Python to run the app: installed launcher, dev venv, or system python
if command -v fission360 >/dev/null; then APP=(fission360)
elif [ -x "$HERE/.venv/bin/python" ]; then APP=("$HERE/.venv/bin/python" -m fission360)
else APP=(python3 -m fission360); fi

STATE="${XDG_RUNTIME_DIR:-/tmp}/fission360-remote"
mkdir -p "$STATE"
PIDS=()
cleanup() { for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT INT TERM

export DISPLAY=":$DISPLAY_NUM"
Xvfb "$DISPLAY" -screen 0 "${SIZE}x24" -nolisten tcp >"$STATE/xvfb.log" 2>&1 &
PIDS+=($!)
for _ in $(seq 50); do [ -e "/tmp/.X11-unix/X$DISPLAY_NUM" ] && break; sleep 0.1; done

if [ "$PUBLIC" = 1 ]; then
  BIND=0.0.0.0
  PASSFILE="$STATE/vncpass"
  if [ ! -f "$PASSFILE" ]; then
    PW="$(head -c 12 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 8)"
    x11vnc -storepasswd "$PW" "$PASSFILE" >/dev/null 2>&1
    echo "$PW" > "$STATE/vncpass.txt"; chmod 600 "$STATE/vncpass.txt"
  fi
  VNC_AUTH=(-rfbauth "$PASSFILE")
  VNC_LISTEN=()   # x11vnc reachable from LAN as well (VNC clients)
else
  BIND=127.0.0.1
  VNC_AUTH=(-nopw)
  VNC_LISTEN=(-localhost)
fi
x11vnc -display "$DISPLAY" -rfbport "$VNC_PORT" -forever -shared -quiet -noxdamage \
  "${VNC_AUTH[@]}" "${VNC_LISTEN[@]}" >"$STATE/x11vnc.log" 2>&1 &
PIDS+=($!)
websockify --web /usr/share/novnc "$BIND:$PORT" "localhost:$VNC_PORT" >"$STATE/websockify.log" 2>&1 &
PIDS+=($!)

HOST="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "------------------------------------------------------------------"
echo " Fission360 remote session on display $DISPLAY ($SIZE)"
if [ "$PUBLIC" = 1 ]; then
  echo " Browser:    http://$HOST:$PORT/vnc.html?autoconnect=1&resize=scale"
  echo " VNC client: $HOST:$VNC_PORT"
  echo " Password:   $(cat "$STATE/vncpass.txt")   (unencrypted - trusted LAN only)"
else
  echo " On Windows (PowerShell):"
  echo "   ssh -L $PORT:localhost:$PORT -L $VNC_PORT:localhost:$VNC_PORT $(whoami)@${HOST:-<this-host>}"
  echo " then open  http://localhost:$PORT/vnc.html?autoconnect=1&resize=scale"
  echo " (or point a VNC client such as TightVNC/RealVNC at localhost:$VNC_PORT)"
fi
echo " Ctrl+C here stops everything. Closing the app restarts it."
echo "------------------------------------------------------------------"

# Keep the app running; restart it if it is closed
while true; do
  "${APP[@]}" --fullscreen "${APPARGS[@]}" || true
  sleep 1
done
