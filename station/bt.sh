#!/bin/sh
# Bluetooth helper for the station: list / scan / pair / disconnect.
export DBUS_SYSTEM_BUS_ADDRESS="unix:path=/tmp/btbus/socket"

case "$1" in
  list)
    bluetoothctl devices 2>/dev/null | while read -r _ mac name; do
      [ -n "$mac" ] || continue
      info=$(bluetoothctl info "$mac" 2>/dev/null)
      p=$(echo "$info" | sed -n 's/.*Paired: \(yes\|no\).*/\1/p' | head -1)
      c=$(echo "$info" | sed -n 's/.*Connected: \(yes\|no\).*/\1/p' | head -1)
      echo "$mac|$name|${p:-no}|${c:-no}"
    done
    ;;
  scan)
    bluetoothctl --timeout 12 scan on >/dev/null 2>&1
    ;;
  pair)
    M=$2
    [ -n "$M" ] || exit 1
    {
      echo "agent KeyboardDisplay"
      echo "default-agent"
      sleep 1
      echo "scan on"
      sleep 6
      echo "pair $M"
      sleep 15
      echo "trust $M"
      sleep 2
      echo "connect $M"
      sleep 6
      echo "quit"
    } | bluetoothctl >/dev/null 2>&1
    ;;
  disconnect)
    bluetoothctl disconnect "$2" >/dev/null 2>&1
    ;;
  *)
    echo "usage: $0 list|scan|pair MAC|disconnect MAC"
    ;;
esac
