#!/usr/bin/env python3
"""Sound panel for the Yandex Station: EQ curve, DRC, player, seek."""
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = ("0.0.0.0", 8099)
BASE = Path(__file__).resolve().parent
STATION = "root@192.168.0.90"
SSH = ["ssh", "-i", "/root/.ssh/station", "-p", "2222",
       "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
       "-o", "ConnectTimeout=5",
       "-o", "ControlMaster=auto", "-o", "ControlPath=/tmp/ytm-ssh-%C",
       "-o", "ControlPersist=180", STATION]
SSH_SEM = threading.Semaphore(2)
YTM = "/data/yam/bin/ytm-alice"
CFG = "/data/quasar/data/user_config.dat"

FREQS = [60, 230, 910, 3600, 14000]
LABELS = ["60", "230", "910", "3.6k", "14k"]

READ_SOUND = "for n in 7 8; do amixer -c0 cget numid=$n | sed -n 's/^ *: values=//p'; done"

PRESETS = {
    "flat":  {"label": "Плоско", "gains": [0, 0, 0, 0, 0]},
    "bass":  {"label": "Бас",    "gains": [8, 5, 0, -2, -4]},
    "voice": {"label": "Голос",  "gains": [-4, 0, 4, 3, -1]},
    "rock":  {"label": "Рок",    "gains": [5, 2, -2, 3, 4]},
    "night": {"label": "Ночной", "gains": [3, 2, 1, -2, -5]},
}

_lock = threading.Lock()
_cache = {"ts": 0.0, "data": None}
_eq_job = {"running": False, "error": ""}


def run_ssh(command, timeout=20, data=None):
    with SSH_SEM:
        p = subprocess.run(SSH + [command], input=data, capture_output=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError((p.stderr.decode("utf-8", "replace") if isinstance(p.stderr, bytes) else p.stderr) or "ssh failed")
    return p.stdout


def run_ssh_text(command, timeout=20):
    out = run_ssh(command, timeout)
    return out.decode("utf-8", "replace")


# --- user_config.dat container -------------------------------------------

def read_varint(buf, pos):
    shift = value = 0
    while True:
        b = buf[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        if not b & 0x80:
            return value, pos
        shift += 7


def write_varint(value):
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def parse_cfg(data):
    if data[0] != 0x0A:
        raise ValueError("bad container")
    l1, pos = read_varint(data, 1)
    payload = data[pos:pos + l1]
    rest = data[pos + l1:]
    if payload[0] != 0x0A:
        raise ValueError("bad uid tag")
    ulen, p = read_varint(payload, 1)
    uid = payload[p:p + ulen]
    p += ulen
    if payload[p] != 0x12:
        raise ValueError("bad json tag")
    l2, p = read_varint(payload, p + 1)
    raw = payload[p:p + l2]
    tail = payload[p + l2:]
    return uid, raw, rest, tail


def build_cfg(uid, raw, rest, tail):
    inner = b"\x0a" + write_varint(len(uid)) + uid + b"\x12" + write_varint(len(raw)) + raw + tail
    return b"\x0a" + write_varint(len(inner)) + inner + rest


def load_cfg():
    data = run_ssh("cat " + CFG)
    return parse_cfg(data)


def save_cfg(uid, raw, rest, tail):
    data = build_cfg(uid, raw, rest, tail)
    run_ssh("cat > " + CFG, data=data)


def read_eq():
    uid, raw, rest, tail = load_cfg()
    cfg = json.loads(raw)
    eq = cfg.get("device_config", {}).get("equalizer", {}) or {}
    custom = eq.get("custom_preset_bands") or [0, 0, 0, 0, 0]
    bands = [int(round(x)) for x in (custom + [0] * 5)[:5]]
    return bands, bool(eq.get("enabled")), eq.get("active_preset_id", "")


def write_eq(gains, enabled=True):
    uid, raw, rest, tail = load_cfg()
    cfg = json.loads(raw)
    eq = cfg.setdefault("device_config", {}).setdefault("equalizer", {})
    eq["active_preset_id"] = "custom"
    eq["custom_preset_bands"] = [max(-12, min(12, int(g))) for g in gains]
    eq["bands"] = [
        {"freq": f, "gain": max(-12, min(12, int(g))), "width": w}
        for f, g, w in zip(FREQS, gains, [90, 340, 1340, 5200, 13000])
    ]
    eq["enabled"] = bool(enabled)
    eq.setdefault("modes", {})
    raw_new = json.dumps(cfg, ensure_ascii=False, separators=(",", ":")).encode()
    save_cfg(uid, raw_new, rest, tail)


def reload_eq():
    # Stop the audio stack first so it cannot rewrite the config under us,
    # then let the launcher start it again and read our file.
    run_ssh_text(
        "p=$(ps w | grep 'maind --platformd' | grep -v grep | awk '{print $1}' | head -1); "
        "[ -n \"$p\" ] && kill $p; "
        "i=0; while ps w | grep -q 'maind --platformd'; do i=$((i+1)); [ $i -ge 15 ] && break; sleep 1; done; "
        "sleep 3", timeout=45)
    with _lock:
        _cache["ts"] = 0.0


# --- sound / player -------------------------------------------------------

def parse_sound(out):
    vals = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if len(vals) < 2:
        raise RuntimeError("unexpected amixer output")
    return {"eq": vals[0] == "on", "drc": vals[1] == "on"}


def parse_player(out):
    try:
        data = json.loads(out)
    except Exception:
        return {"status": "unknown", "id": "", "title": "", "artists": "", "position_ms": 0, "duration_ms": 0}
    st = data.get("state") or {}
    queue = st.get("queue") or []
    idx = st.get("index") or 0
    track = queue[idx] if 0 <= idx < len(queue) else {}
    return {
        "status": st.get("status", "unknown"),
        "id": track.get("id", ""),
        "title": track.get("title", ""),
        "artists": track.get("artists", ""),
        "position_ms": st.get("position_ms", 0),
        "duration_ms": track.get("duration_ms", 0),
    }


def start_eq_job(gains, enabled):
    if _eq_job["running"]:
        return False
    _eq_job["running"] = True
    _eq_job["error"] = ""

    def run():
        try:
            reload_eq()
            write_eq(gains, enabled)
            time.sleep(8)
        except Exception as e:
            _eq_job["error"] = str(e)
        finally:
            _eq_job["running"] = False
            with _lock:
                _cache["ts"] = 0.0

    threading.Thread(target=run, daemon=True).start()
    return True


def read_all():
    with _lock:
        if _cache["data"] and time.time() - _cache["ts"] < 1.0:
            return _cache["data"]
    out = run_ssh_text(READ_SOUND + "; echo '---PLAYER---'; " + YTM + " --json status 2>/dev/null")
    sound_part, _, player_part = out.partition("---PLAYER---")
    gains, eq_enabled, _ = read_eq()
    data = {
        "sound": parse_sound(sound_part),
        "player": parse_player(player_part.strip()),
        "eq": {"gains": gains, "enabled": eq_enabled, "freqs": FREQS, "labels": LABELS,
               "presets": [{"id": k, "label": v["label"], "gains": v["gains"]} for k, v in PRESETS.items()],
               "applying": _eq_job["running"], "error": _eq_job["error"]},
    }
    with _lock:
        _cache["data"] = data
        _cache["ts"] = time.time()
    return data


def apply_sound(values):
    cmds = []
    if "eq" in values:
        cmds.append("amixer -c0 cset numid=7 %s" % ("on" if values["eq"] else "off"))
    if "drc" in values:
        cmds.append("amixer -c0 cset numid=8 %s" % ("on" if values["drc"] else "off"))
    if cmds:
        run_ssh_text("; ".join(cmds))
    with _lock:
        _cache["ts"] = 0.0


def player_action(values):
    action = values.get("action")
    if action in ("pause", "resume", "next", "previous", "stop"):
        run_ssh_text("%s %s" % (YTM, action))
    elif action == "toggle":
        st = read_all()["player"]["status"]
        run_ssh_text("%s %s" % (YTM, "pause" if st in ("playing", "buffering") else "resume"))
    elif action == "seek":
        delta = float(values.get("value", 0))
        st = read_all()["player"]
        target = max(0.0, (st["position_ms"] + delta * 1000) / 1000.0)
        run_ssh_text("%s seek %.1f" % (YTM, target))
    else:
        raise RuntimeError("unknown player action")
    with _lock:
        _cache["ts"] = 0.0


def bt_state():
    out = run_ssh_text("sh /data/bt.sh list 2>/dev/null; echo '---OUT---'; "
                       "sed -n 's/.*slave.pcm \"\\(.*\\)\"/\\1/p' /etc/asound.conf | head -1")
    dev_part, _, out_part = out.partition("---OUT---")
    devices = []
    for line in dev_part.splitlines():
        parts = line.strip().split("|")
        if len(parts) == 4 and parts[0]:
            devices.append({"mac": parts[0], "name": parts[1],
                            "paired": parts[2] == "yes", "connected": parts[3] == "yes"})
    target = out_part.strip().splitlines()[0].strip() if out_part.strip() else ""
    output = "bt" if "bt_forced" in target else "spk"
    return {"devices": devices, "output": output}


def bt_action(values):
    action = values.get("action")
    mac = values.get("mac", "")
    if action == "scan":
        run_ssh_text("sh /data/bt.sh scan", timeout=40)
    elif action == "pair" and mac:
        run_ssh_text("sh /data/bt.sh pair %s" % mac, timeout=90)
    elif action == "disconnect" and mac:
        run_ssh_text("sh /data/bt.sh disconnect %s" % mac, timeout=30)
    else:
        raise RuntimeError("unknown bt action")


def set_output(target):
    if target not in ("bt", "spk"):
        raise RuntimeError("bad output")
    run_ssh_text("sh /data/audio-out.sh %s" % target, timeout=30)


def sys_state():
    out = run_ssh_text(
        "cat /proc/loadavg; "
        "grep -E 'MemTotal|MemAvailable' /proc/meminfo; "
        "cat /proc/uptime; "
        "cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo 0; "
        "df -k /data | tail -1"
    )
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    load = lines[0].split()[:3] if lines else ["0", "0", "0"]
    mem = {}
    for l in lines:
        if l.startswith("MemTotal"):
            mem["total"] = int(l.split()[1])
        elif l.startswith("MemAvailable"):
            mem["avail"] = int(l.split()[1])
    up = float(lines[3].split()[0]) if len(lines) > 3 else 0
    try:
        temp = int(float(lines[4])) / 1000.0 if len(lines) > 4 else 0
    except Exception:
        temp = 0
    disk = lines[5].split() if len(lines) > 5 else []
    total_mb = mem.get("total", 0) // 1024
    avail_mb = mem.get("avail", 0) // 1024
    return {
        "load": load,
        "mem_total_mb": total_mb,
        "mem_used_mb": max(0, total_mb - avail_mb),
        "mem_pct": round((total_mb - avail_mb) * 100 / total_mb) if total_mb else 0,
        "uptime_h": round(up / 3600, 1),
        "temp_c": round(temp, 1),
        "disk_total_mb": int(disk[1]) // 1024 if len(disk) > 1 else 0,
        "disk_used_mb": int(disk[2]) // 1024 if len(disk) > 2 else 0,
    }


FAV_PATH = BASE / "favorites.json"


def favorites_state():
    try:
        data = json.loads(FAV_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            data = []
    except Exception:
        data = []
    return {"favorites": data}


def favorites_action(values):
    action = values.get("action")
    favs = favorites_state()["favorites"]
    if action in ("add_current", "add"):
        if action == "add_current":
            p = read_all()["player"]
            item = {"id": p.get("id") or "", "title": p.get("title") or "",
                    "artists": p.get("artists") or ""}
        else:
            item = {"id": str(values.get("id", "")), "title": str(values.get("title", "")),
                    "artists": str(values.get("artists", ""))}
        if item["id"] and item["title"]:
            favs = [f for f in favs if f.get("id") != item["id"]]
            favs.insert(0, item)
            favs = favs[:200]
    elif action == "remove":
        rid = str(values.get("id", ""))
        favs = [f for f in favs if f.get("id") != rid]
    elif action == "play":
        idx = int(values.get("index", 0))
        if 0 <= idx < len(favs):
            run_ssh_text('%s play "https://music.youtube.com/watch?v=%s"' % (YTM, favs[idx]["id"]),
                         timeout=40)
    FAV_PATH.write_text(json.dumps(favs, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"favorites": favs}


def queue_state():
    out = run_ssh_text(YTM + " --json status 2>/dev/null", timeout=20)
    try:
        data = json.loads(out)
    except Exception:
        return {"index": 0, "queue": []}
    st = data.get("state") or {}
    items = []
    for t in (st.get("queue") or [])[:60]:
        items.append({"id": t.get("id", ""), "title": t.get("title", ""),
                      "artists": t.get("artists", "")})
    return {"index": int(st.get("index") or 0), "queue": items}


def queue_action(values):
    n = int(values.get("number", 0))
    if n > 0:
        run_ssh_text("%s jump %d" % (YTM, n), timeout=25)
    return queue_state()


HISTORY_PATH = BASE / "history.json"
_bad_words = ("official video", "music video", "клип", "видеоклип", "m/v", "mrbeast",
              "vlog", "bass boost", "slowed", "8d audio", "jumpstyle", "oiia", "oija",
              "scooby", "banana song", "прикол", "тикток", "tiktok", "мем")


def _looks_junk(text):
    low = (text or "").lower()
    return any(b in low for b in _bad_words)


def _load_history():
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_history(items):
    try:
        HISTORY_PATH.write_text(json.dumps(items[-1000:], ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def record_history(track):
    tid = track.get("id") or ""
    title = (track.get("title") or "").strip()
    if not tid or not title:
        return
    items = _load_history()
    if items and items[-1].get("id") == tid:
        return
    items.append({"id": tid, "title": title, "artists": (track.get("artists") or "").strip(),
                  "ts": int(time.time())})
    _save_history(items)


def mix_seed():
    items = _load_history()
    counts = {}
    for it in items:
        art = (it.get("artists") or "").strip()
        if not art or len(art) < 2:
            continue
        low = art.lower()
        if " - topic" in low or _looks_junk(art) or _looks_junk(it.get("title")):
            continue
        counts[art] = counts.get(art, 0) + 1
    best = sorted(counts.items(), key=lambda kv: -kv[1])[:1]
    artist = best[0][0] if best else ""
    return {"artist": artist, "plays": best[0][1] if best else 0, "total": len(items)}


def history_state():
    items = _load_history()
    return {"items": items[-100:], "total": len(items)}


def alarms_state():
    out = run_ssh_text("cat /data/alarms.txt 2>/dev/null")
    items = []
    for line in out.splitlines():
        parts = line.strip().split("|", 2)
        if len(parts) == 3 and parts[0].strip().isdigit():
            try:
                items.append({"minutes": int(parts[0]), "offset": int(parts[1] or 0),
                              "query": parts[2].strip()})
            except ValueError:
                continue
    items.sort(key=lambda a: a["minutes"])
    return {"alarms": items}


def alarms_action(values):
    action = values.get("action")
    items = alarms_state()["alarms"]
    if action == "add":
        items.append({
            "minutes": int(values.get("minutes", 0)) % 1440,
            "offset": int(values.get("offset", 0)),
            "query": str(values.get("query", "")).replace("|", " ").strip(),
        })
    elif action == "remove":
        idx = int(values.get("index", -1))
        if 0 <= idx < len(items):
            items.pop(idx)
    items.sort(key=lambda a: a["minutes"])
    lines = ["%d|%d|%s" % (a["minutes"], a["offset"], a["query"]) for a in items]
    if lines:
        quoted = " ".join("'%s'" % l.replace("'", "") for l in lines)
        cmd = "printf '%%s\\n' %s > /data/alarms.txt" % quoted
    else:
        cmd = ": > /data/alarms.txt"
    run_ssh_text(cmd, timeout=20)
    return alarms_state()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        try:
            self.path = self.path.split('?', 1)[0]
            if self.path in ("/", "/index.html"):
                return self._send(200, (BASE / "index.html").read_bytes(), "text/html; charset=utf-8")
            if self.path.startswith("/api/state"):
                return self._send(200, json.dumps(read_all(), ensure_ascii=False))
            if self.path.startswith("/api/bt"):
                return self._send(200, json.dumps(bt_state(), ensure_ascii=False))
            if self.path.startswith("/api/sys"):
                return self._send(200, json.dumps(sys_state(), ensure_ascii=False))
            if self.path.startswith("/api/alarms"):
                return self._send(200, json.dumps(alarms_state(), ensure_ascii=False))
            if self.path.startswith("/api/favorites"):
                return self._send(200, json.dumps(favorites_state(), ensure_ascii=False))
            if self.path.startswith("/api/queue"):
                return self._send(200, json.dumps(queue_state(), ensure_ascii=False))
            if self.path.startswith("/api/history"):
                return self._send(200, json.dumps(history_state(), ensure_ascii=False))
            if self.path.startswith("/api/mixseed"):
                return self._send(200, json.dumps(mix_seed(), ensure_ascii=False))
            self._send(404, json.dumps({"error": "not found"}))
        except Exception as e:
            self._send(502, json.dumps({"error": str(e)}, ensure_ascii=False))

    def do_POST(self):
        try:
            self.path = self.path.split('?', 1)[0]
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length) or b"{}")
            if self.path.startswith("/api/set"):
                apply_sound(data)
            elif self.path.startswith("/api/player"):
                player_action(data)
            elif self.path.startswith("/api/bt"):
                bt_action(data)
                return self._send(200, json.dumps(bt_state(), ensure_ascii=False))
            elif self.path.startswith("/api/out"):
                set_output(data.get("target"))
                return self._send(200, json.dumps(bt_state(), ensure_ascii=False))
            elif self.path.startswith("/api/alarms"):
                return self._send(200, json.dumps(alarms_action(data), ensure_ascii=False))
            elif self.path.startswith("/api/favorites"):
                return self._send(200, json.dumps(favorites_action(data), ensure_ascii=False))
            elif self.path.startswith("/api/queue"):
                return self._send(200, json.dumps(queue_action(data), ensure_ascii=False))
            elif self.path.startswith("/api/eq"):
                if not start_eq_job(data.get("gains", [0, 0, 0, 0, 0]), data.get("enabled", True)):
                    return self._send(409, json.dumps({"error": "уже применяется"}))
                return self._send(200, json.dumps({"applying": True}))
            else:
                return self._send(404, json.dumps({"error": "not found"}))
            self._send(200, json.dumps(read_all(), ensure_ascii=False))
        except Exception as e:
            self._send(502, json.dumps({"error": str(e)}, ensure_ascii=False))


VIDEO_MARKERS = (
    "official video", "music video", "official music video", "клип", "видеоклип",
    "m/v", "full video", "премьера клипа", "lyric video", "live video",
)


def video_guard():
    """Skip YouTube-video fallbacks: ytm-alice plays a video when no matching song exists."""
    skipped = []
    cooldown_until = 0.0
    while True:
        try:
            if time.time() < cooldown_until:
                time.sleep(5)
                continue
            out = run_ssh_text(YTM + " --json status 2>/dev/null", timeout=15)
            data = json.loads(out)
            st = data.get("state") or {}
            queue = st.get("queue") or []
            idx = st.get("index") or 0
            tr = queue[idx] if 0 <= idx < len(queue) else {}
            status = st.get("status")
            pos = st.get("position_ms") or 0
            dur = tr.get("duration_ms") or 0
            title = (tr.get("title") or "").strip()
            tid = tr.get("id") or ""
            if status in ("playing", "buffering"):
                record_history(tr)
            if status in ("playing", "buffering") and pos < 45000 and tid and tid not in skipped:
                low = title.lower()
                looks_video = any(m in low for m in VIDEO_MARKERS) or dur > 20 * 60 * 1000
                if looks_video:
                    skipped.append(tid)
                    skipped = skipped[-10:]
                    sys.stderr.write("video-guard: skip %r (%ds)\n" % (title[:50], dur // 1000))
                    run_ssh_text(YTM + " next", timeout=20)
                    if len(skipped) >= 3:
                        cooldown_until = time.time() + 300
                        skipped = []
        except Exception as e:
            sys.stderr.write("video-guard: %s\n" % e)
        time.sleep(5)


if __name__ == "__main__":
    threading.Thread(target=video_guard, daemon=True).start()
    ThreadingHTTPServer(HOST, Handler).serve_forever()
