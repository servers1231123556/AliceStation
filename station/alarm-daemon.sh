#!/bin/sh
# Station alarm daemon: fires `ytm-alice play <query>` at the given wall-clock time.
# /data/alarms.txt format, one per line:  <minutes since midnight>|<utc offset minutes>|<query>
export PATH="/data/yam/bin:$PATH"
FILE=/data/alarms.txt
YTM=/data/yam/bin/ytm-alice

[ -f "$FILE" ] || : > "$FILE"

while :; do
  now_utc_min=$(( $(date -u +%H) * 60 + $(date -u +%M) ))
  today=$(date -u +%Y%m%d)
  while IFS='|' read -r mins off query; do
    [ -z "$mins" ] && continue
    case "$mins" in *[!0-9]*) continue ;; esac
    case "$off" in -*) off2=${off#-}; off2=$((0 - off2)) ;; *) off2=$off ;; esac
    local_min=$(( (now_utc_min + off2) % 1440 ))
    if [ "$local_min" -eq "$mins" ]; then
      key="/tmp/alarm-${mins}-${off}-${today}"
      if [ ! -f "$key" ]; then
        touch "$key"
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) fire $mins $off $query" >> /tmp/alarm.log
        if [ -n "$query" ]; then
          "$YTM" play "$query" >/dev/null 2>&1
        else
          "$YTM" recommendations >/dev/null 2>&1
        fi
      fi
    fi
  done < "$FILE"
  sleep 15
done
