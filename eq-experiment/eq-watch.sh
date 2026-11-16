#!/bin/sh
# Watchdog: if the EQ relay died while audio is routed through it, fall back to the speaker.
LOOP_TAG="hw:Loopback,0"
while :; do
  if grep -q "$LOOP_TAG" /etc/asound.conf 2>/dev/null; then
    if ! ls /proc/*/comm >/dev/null 2>&1 || ! ps w | grep -q '[e]qrelay'; then
      mount -o remount,rw / 2>/dev/null
      cp /etc/asound.internal /etc/asound.conf
      sync
      mount -o remount,ro / 2>/dev/null
      echo "$(date -u +%H:%M:%S) relay gone, restored speaker" >> /data/eq/watch.log
    fi
  fi
  sleep 3
done
