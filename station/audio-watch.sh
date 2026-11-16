#!/bin/sh
# Keep audio output in sync with the Bluetooth amp connection state.
MAC=87:00:A9:BC:26:2A
export DBUS_SYSTEM_BUS_ADDRESS="unix:path=/tmp/btbus/socket"
PIDFILE=/tmp/audio-watch.pid
if [ -f "$PIDFILE" ]; then
  old=$(cat "$PIDFILE" 2>/dev/null)
  [ -n "$old" ] && [ -d "/proc/$old" ] && exit 0
fi
echo $$ > "$PIDFILE"

prev=""
while :; do
  c=$(bluetoothctl info "$MAC" 2>/dev/null | sed -n 's/.*Connected: \(yes\|no\).*/\1/p' | head -1)
  [ -z "$c" ] && c="no"
  if [ -n "$prev" ] && [ "$c" != "$prev" ]; then
    if [ "$c" = "yes" ]; then
      sh /data/audio-out.sh bt
    else
      sh /data/audio-out.sh spk
    fi
    echo "$(date +%s) $prev -> $c" >> /tmp/audio-watch.log
  fi
  prev="$c"
  sleep 8
done
