#!/bin/sh
# Fire effect for the station ring: flickering flame with random embers.
L=/sys/class/leds
STATE=/data/yam/var/local.ytm-alice/state.json

setb() { echo "$2" > "$L/mini2:$1:ring$3/brightness" 2>/dev/null; }
setp() { setb red "$2" "$1"; setb green "$3" "$1"; setb blue "$4" "$1"; }

alloff() { i=1; while [ "$i" -le 6 ]; do setp "$i" 0 0 0; i=$((i+1)); done; }

status() { sed -n 's/.*"status":"\([a-z]*\)".*/\1/p' "$STATE" 2>/dev/null | head -1; }

rnd() { echo $(( (RANDOM + $$) % $1 )); }

alloff
prev=""
spark=0
while :; do
  if [ -f /tmp/led-manual ]; then sleep 0.4; continue; fi
  st=$(status)
  case "$st" in
    playing)
      i=1
      while [ "$i" -le 6 ]; do
        r=$(( 170 + $(rnd 85) ))
        g=$(( 20 + $(rnd 110) ))
        setp "$i" "$r" "$g" 0
        i=$((i+1))
      done
      # random ember: one segment flashes bright
      spark=$(rnd 5)
      if [ "$spark" -eq 0 ]; then
        i=$(rnd 6); i=$((i+1))
        setp "$i" 255 255 40
      fi
      sleep 0.08
      prev=playing
      ;;
    buffering|searching)
      i=1
      while [ "$i" -le 6 ]; do
        alloff
        setp "$i" 255 120 0
        sleep 0.1
        i=$((i+1))
      done
      prev=loading
      ;;
    *)
      if [ "$prev" != off ]; then
        alloff
        prev=off
      fi
      sleep 0.6
      ;;
  esac
done
