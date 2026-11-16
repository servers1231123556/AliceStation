#!/bin/sh
# Keep YouTube routes alive: wlan0 re-association removes device-bound routes.
PIDFILE=/tmp/ytm-routes.pid
if [ -f "$PIDFILE" ]; then
  old=$(cat "$PIDFILE" 2>/dev/null)
  if [ -n "$old" ] && [ -d "/proc/$old" ]; then
    exit 0
  fi
fi
echo $$ > "$PIDFILE"
while :; do
  n=$(ip route show table 200 2>/dev/null | grep -c 'via 192.168.0.91')
  if [ "$n" -lt 100 ]; then
    sh /data/ytm-routes.sh >/dev/null 2>&1
    echo "$(date +%s) reapplied (was $n)" >> /tmp/ytm-routes.log
  fi
  sleep 20
done
