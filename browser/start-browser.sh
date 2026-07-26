#!/bin/bash
# LeLinc Browser Start Script
# Launches: Xvfb -> fluxbox -> Chrome -> x11vnc -> noVNC websockify

set -e

DISPLAY_NUM=99
export DISPLAY=:$DISPLAY_NUM
RESOLUTION="1920x1080"
VNC_PORT=5900
NOVNC_PORT=6901
CDP_PORT=9222
CHROME_DATA="/profile"

# Cleanup any leftover locks
rm -f /tmp/.X$DISPLAY_NUM-lock /tmp/.X11-unix/X$DISPLAY_NUM
echo "Cleaning Chrome profile locks..."
rm -f /profile/SingletonLock /profile/SingletonCookie /profile/SingletonSocket

echo "=== Starting LeLinc Browser ==="

# 1. Start Xvfb (virtual framebuffer)
echo "Starting Xvfb on display :$DISPLAY_NUM..."
Xvfb :$DISPLAY_NUM -screen 0 ${RESOLUTION}x24 -ac &
sleep 1 2>/dev/null || true

# 2. Start fluxbox (window manager)
echo "Starting fluxbox..."
fluxbox &
sleep 1 2>/dev/null || true

# 3. Start Chrome with CDP debug port
echo "Starting Chrome..."
/root/.cloakbrowser/chromium-146.0.7680.177.5/chrome \
    --display=:$DISPLAY_NUM \
    --remote-debugging-port=$CDP_PORT --remote-debugging-address=0.0.0.0 --remote-allow-origins=* \
    --user-data-dir=$CHROME_DATA \
    --no-first-run \
    --disable-default-apps \
    --disable-sync \
    --disable-translate \
    --disable-features=TranslateUI \
    --window-size=1920,1080 \
    --window-position=0,0 \
    --no-sandbox \
    --disable-dev-shm-usage \
    --disable-gpu \
    about:blank &
sleep 3

# 4. Start x11vnc (VNC server)
echo "Starting x11vnc on port $VNC_PORT..."
x11vnc -display :$DISPLAY_NUM \
    -forever \
    -shared \
    -rfbport $VNC_PORT \
    -nopw \
    -quiet &
sleep 1 2>/dev/null || true

# 5. Start noVNC websockify (WebSocket bridge to VNC)
echo "Starting noVNC websockify on port $NOVNC_PORT..."
/usr/share/novnc/utils/novnc_proxy \
    --vnc localhost:$VNC_PORT \
    --listen $NOVNC_PORT \
    --web /usr/share/novnc &
sleep 1 2>/dev/null || true

# CDP forward: expose Chrome CDP on all interfaces so Docker can map it
echo "Starting CDP forward..."
# Kill any stale socat from previous start
pkill -f "socat.*19222" 2>/dev/null || true

# Retry socat until Chrome is ready
for i in $(seq 1 10); do
  socat TCP-LISTEN:19222,reuseaddr,fork TCP:127.0.0.1:9222 &
  sleep 1
  if curl -s http://127.0.0.1:9222/json/version >/dev/null 2>&1; then
    break
  fi
done
sleep 1 2>/dev/null || true
echo "=== LeLinc Browser Ready ==="
echo "VNC:      localhost:$VNC_PORT"
echo "noVNC:    http://localhost:$NOVNC_PORT/vnc.html"
echo "CDP:      http://localhost:$CDP_PORT"

# Keep container alive and show logs
wait
