#!/bin/sh
# The firmware spawns "led_util <pattern>" and sometimes never stops it after a reply,
# which leaves the ring frozen. Kill such leftovers when they run too long.
MAX_AGE=22
SEEN=/tmp/ledseen
: > "$SEEN" 2>/dev/null

while :; do
  now=$(date +%s)
  : > /tmp/ledseen.new
  for p in $(ps w 2>/dev/null | grep 'led_util /system/vendor/quasar/ledpatterns' | grep -v grep | awk '{print $1}'); do
    first=$(grep "^$p " "$SEEN" 2>/dev/null | head -1 | awk '{print $2}')
    [ -z "$first" ] && first=$now
    age=$((now - first))
    if [ "$age" -ge "$MAX_AGE" ]; then
      kill "$p" 2>/dev/null
      # clear the frozen frame
      n=1
      while [ "$n" -le 6 ]; do
        for c in red green blue; do
          echo 0 > "/sys/class/leds/mini2:$c:ring$n/brightness" 2>/dev/null
        done
        n=$((n+1))
      done
    else
      echo "$p $first" >> /tmp/ledseen.new
    fi
  done
  mv /tmp/ledseen.new "$SEEN" 2>/dev/null
  sleep 2
done
