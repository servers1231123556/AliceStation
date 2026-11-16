#!/bin/sh
# eqrelay control: start | stop | status
BIN=/data/eq/eqrelay-b3
GAINS=/data/eq/gains.txt
PIDF=/tmp/eqrelay.pid
LOG=/data/eq/relay.log
LOOP_CONF=/etc/asound.eqloop
INT_CONF=/etc/asound.internal

rw() { mount -o remount,rw / 2>/dev/null; }
ro() { mount -o remount,ro / 2>/dev/null; }

apply_loop() { rw; cp "$LOOP_CONF" /etc/asound.conf; sync; ro; }
apply_int()  { rw; cp "$INT_CONF"  /etc/asound.conf; sync; ro; }

running() {
  [ -f "$PIDF" ] && [ -d "/proc/$(cat "$PIDF" 2>/dev/null)" ] && return 0
  return 1
}

stop() {
  if [ -f "$PIDF" ]; then kill "$(cat "$PIDF")" 2>/dev/null; rm -f "$PIDF"; fi
  for p in $(ps w | grep '/data/eq/eqrelay-b3' | grep -v grep | awk '{print $1}'); do kill "$p" 2>/dev/null; done
  sleep 1
}

start() {
  stop
  mkdir -p /data/eq
  [ -f "$GAINS" ] || echo "0 0 0 0 0" > "$GAINS"
  : > "$LOG"
  nohup "$BIN" hw:Loopback,1,0 dmix_spk "$GAINS" >>"$LOG" 2>&1 </dev/null &
  echo $! > "$PIDF"
  sleep 2
  if running; then
    apply_loop
    echo "eqrelay started pid=$(cat "$PIDF")"
  else
    echo "eqrelay failed"
    tail -5 "$LOG" 2>/dev/null
    apply_int
  fi
}

case "$1" in
  start) start ;;
  stop) stop; apply_int; echo "eqrelay stopped, sound back to speaker" ;;
  status) if running; then echo "running pid=$(cat "$PIDF")"; else echo "not running"; fi ;;
  *) echo "usage: $0 start|stop|status" ;;
esac
