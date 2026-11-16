#!/bin/sh
# LED states written straight into sysfs at ~15-20 fps so the firmware animation
# cannot repaint over us. No led_util involved.
L=/sys/class/leds
FLAG=/tmp/led-manual
PIDF=/tmp/led-manual.pid

stop() {
  me=$$
  for p in $(ps w 2>/dev/null | grep '/data/led.sh' | grep -v grep | awk '{print $1}'); do
    [ "$p" = "$me" ] && continue
    kill "$p" 2>/dev/null
  done
  rm -f "$PIDF"
}

ring() { # ring r g b
  echo "$2" > "$L/mini2:red:ring$1/brightness" 2>/dev/null
  echo "$3" > "$L/mini2:green:ring$1/brightness" 2>/dev/null
  echo "$4" > "$L/mini2:blue:ring$1/brightness" 2>/dev/null
}

all() { n=1; while [ "$n" -le 6 ]; do ring "$n" "$1" "$2" "$3"; n=$((n+1)); done; }

case "$1" in
  green)
    stop
    echo "green" > "$FLAG"
    (
      while [ "$(cat "$FLAG" 2>/dev/null)" = "green" ]; do
        for g in 0 12 24 36 48 60 72 84 72 60 48 36 24 12; do
          all 0 "$g" 6
          sleep 0.07
        done
      done
    ) &
    echo $! > "$PIDF"
    ;;
  blue)
    stop
    echo "blue" > "$FLAG"
    (
      pos=1
      while [ "$(cat "$FLAG" 2>/dev/null)" = "blue" ]; do
        n=1
        while [ "$n" -le 6 ]; do
          if [ "$n" = "$pos" ]; then ring "$n" 0 70 210; else ring "$n" 0 4 16; fi
          n=$((n+1))
        done
        pos=$((pos + 1)); [ "$pos" -gt 6 ] && pos=1
        sleep 0.08
      done
    ) &
    echo $! > "$PIDF"
    ;;
  violet)
    stop
    echo "violet" > "$FLAG"
    (
      while [ "$(cat "$FLAG" 2>/dev/null)" = "violet" ]; do
        all 75 15 150
        sleep 0.07
      done
    ) &
    echo $! > "$PIDF"
    ;;
  off)
    stop
    rm -f "$FLAG"
    all 0 0 0
    ;;
  *)
    echo "usage: $0 green|blue|violet|off"
    ;;
esac
