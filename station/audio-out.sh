#!/bin/sh
# Switch the station audio output: bt (Bluetooth amp) or spk (internal speaker)
YTM=/data/yam/bin/ytm-alice

case "$1" in
  bt)  SRC=/etc/asound.bt;       echo "bt" ;;
  spk) SRC=/etc/asound.internal; echo "spk" ;;
  *)   echo "usage: $0 bt|spk"; exit 1 ;;
esac
[ -s "$SRC" ] || { echo "missing $SRC"; exit 1; }

# remember what was playing
js=$($YTM --json status 2>/dev/null)
st=$(echo "$js" | sed -n 's/.*"status":"\([a-z]*\)".*/\1/p' | head -1)
idx=$(echo "$js" | sed -n 's/.*"index":\([0-9]*\).*/\1/p' | head -1)
pos=$(echo "$js" | sed -n 's/.*"position_ms":\([0-9]*\).*/\1/p' | head -1)

mount -o remount,rw / 2>/dev/null
cp "$SRC" /etc/asound.conf
sync
mount -o remount,ro / 2>/dev/null

# reopen the audio device so the change takes effect now
if [ "$st" = "playing" ] || [ "$st" = "buffering" ]; then
  $YTM stop >/dev/null 2>&1
  sleep 1
  if [ -n "$idx" ]; then
    $YTM jump "$((idx + 1))" >/dev/null 2>&1
    sleep 3
    [ -n "$pos" ] && [ "$pos" -gt 0 ] && $YTM seek "$((pos / 1000))" >/dev/null 2>&1
  fi
fi
