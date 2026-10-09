#!/bin/sh
set -eu

: "${PIXIV_AUTH_BROWSER_TOKEN:?Set a random shared sidecar token in .env}"
: "${PIXIV_AUTH_BROWSER_VNC_PASSWORD:?Set a random VNC password in .env}"
umask 077
x11vnc -storepasswd "$PIXIV_AUTH_BROWSER_VNC_PASSWORD" /tmp/vnc-password >/dev/null

export DISPLAY="${DISPLAY:-:99}"

Xvfb "$DISPLAY" -screen 0 1280x900x24 -nolisten tcp &
fluxbox >/tmp/fluxbox.log 2>&1 &
x11vnc -display "$DISPLAY" -forever -shared -rfbport 5900 -localhost -rfbauth /tmp/vnc-password >/tmp/x11vnc.log 2>&1 &
websockify --web=/usr/share/novnc/ 6080 localhost:5900 >/tmp/novnc.log 2>&1 &

exec npm start
