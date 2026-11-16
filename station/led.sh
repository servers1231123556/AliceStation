#!/bin/sh
# LED states via the firmware pattern engine (led_util = maind multicall).
# Only our own pattern processes are touched; the firmware engine is left alone.
LEDUTIL=/system/vendor/quasar/led_util
DIR=/data/ledp
FLAG=/tmp/led-manual

kill_ours() {
  for p in $(ps w 2>/dev/null | grep "led_util $DIR/" | grep -v grep | awk '{print $1}'); do
    kill "$p" 2>/dev/null
  done
}

case "$1" in
  green|blue|violet)
    case "$1" in
      green)  PAT=green.led ;;
      blue)   PAT=chase.led ;;
      violet) PAT=violet.led ;;
    esac
    kill_ours
    echo 1 > "$FLAG"
    ( "$LEDUTIL" "$DIR/$PAT" >/dev/null 2>&1 & )
    ;;
  off)
    kill_ours
    rm -f "$FLAG"
    ;;
  *)
    echo "usage: $0 green|blue|violet|off"
    ;;
esac
