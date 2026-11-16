#!/usr/bin/env python3
"""Prompt-rewriting proxy in front of Ollama for the Yandex Station.

- time/weather context only for questions about them
- deterministic "Включаю" for music requests
- deterministic identity answer
- silence for player controls and semantic frames
"""
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

UPSTREAM = "http://192.168.0.82:11434"
LISTEN = ("0.0.0.0", 11435)
UA = "alice-llm-proxy/1.0"

CITY = "Тарко-Сале"
LAT = 64.9167
LON = 77.7833
TZ_NAME = "Asia/Yekaterinburg"

MUSIC_RE = re.compile(
    r"^\s*(?:алиса[,\s]+)?(?:пожалуйста[,\s]+)?"
    r"(?:включи|вруби|поставь|проиграй|запусти|сыграй|переключи|найди)(?:\s|$)",
    re.IGNORECASE,
)
IDENT_RE = re.compile(
    r"(кто ты|что ты за|какая ты модель|какой моделью|какая модель|ты qwen|ты бот|представься)",
    re.IGNORECASE,
)
CONTROL_RE = re.compile(
    r"^(пауза|pause|стоп|stop|продолжи|продолжить|продолжай|resume|"
    r"дальше|назад|next|previous|что играет|что сейчас играет|громче|тише|"
    r"следующий|следующую|следующая|предыдущий|предыдущую|переключи трек|переключи песню|перемот.*).*$",
    re.IGNORECASE,
)
TIME_WEATHER_RE = re.compile(
    r"(погод|температ|ветер|осадк|дожд|снег|мороз|жарк|тепло|холодн|"
    r"котор(ый|ое) час|сколько времени|во сколько|время сейчас|текущ.* время|"
    r"дата|число|день недели|какой сегодня|какое сегодня|месяц|год)",
    re.IGNORECASE,
)
CJK_RE = re.compile(r"[\u3000-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uff00-\uffef]+")

OUT_BT_RE = re.compile(r"(переключ|включ|выведи|поставь).*(блют|bluetooth|усилит)", re.IGNORECASE)
OUT_SPK_RE = re.compile(r"(переключ|выключ|верни|обратно).*(колонк|динамик|станц)", re.IGNORECASE)
SSH_BIN = ["ssh", "-i", "/root/.ssh/station", "-p", "2222",
           "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
           "root@192.168.0.90"]


def set_output(target):
    import subprocess
    try:
        subprocess.run(SSH_BIN + ["sh /data/audio-out.sh %s" % target],
                       capture_output=True, timeout=20)
    except Exception as e:
        sys.stderr.write("audio-out failed: %s\n" % e)


def control_action(text):
    t = text.lower()
    if re.search(r"следующ|дальше|переключи трек|переключи песн|next", t):
        return "next"
    if re.search(r"предыдущ|назад|previous", t):
        return "previous"
    if re.search(r"пауза|pause", t):
        return "pause"
    if re.search(r"продолж|resume", t):
        return "resume"
    if re.search(r"стоп|stop", t):
        return "stop"
    return None


TRACK_RE = re.compile(
    r"(что\s+(?:сейчас\s+)?играет|какой\s+(?:сейчас\s+)?трек|что\s+за\s+(?:песня|трек|композиция)|что\s+включено)",
    re.IGNORECASE,
)


def now_playing():
    import subprocess
    try:
        out = subprocess.run(SSH_BIN + ["/data/yam/bin/ytm-alice --json status"],
                             capture_output=True, timeout=20).stdout.decode("utf-8", "replace")
        data = json.loads(out)
        st = data.get("state") or {}
        queue = st.get("queue") or []
        idx = st.get("index") or 0
        track = queue[idx] if 0 <= idx < len(queue) else {}
        title = (track.get("title") or "").strip()
        artists = (track.get("artists") or "").strip()
        status = st.get("status") or "stopped"
        if not title or status not in ("playing", "buffering", "paused"):
            return "Сейчас ничего не играет."
        name = ("%s — %s" % (title, artists)) if artists else title
        if status == "paused":
            return "На паузе: %s." % name
        return "Сейчас играет: %s." % name
    except Exception as e:
        sys.stderr.write("now_playing failed: %s\n" % e)
        return "Не получилось узнать, что играет."


PANEL = "http://127.0.0.1:8099"

FAV_PLAY_RE = re.compile(r"включи.*(избранн|любим|избранное)", re.IGNORECASE)
LIKE_RE = re.compile(
    r"(добавь|сохрани|запомни).*(избранн|любим|нравится)|мне нравится|в избранное|в любимые",
    re.IGNORECASE,
)
MOOD_RE = re.compile(
    r"включи.*(спокойн|чилл|расслаб|энергичн|бодр|танцев|весёл|весел|грустн|романтичн|"
    r"работ|фокус|ночн|сон|медленн|быстр)",
    re.IGNORECASE,
)

MOOD_MAP = (
    (r"спокойн|чилл|расслаб|медленн", "lofi chill beats"),
    (r"энергичн|бодр|танцев|быстр", "dance party mix"),
    (r"весёл|весел", "happy upbeat songs"),
    (r"грустн", "sad songs playlist"),
    (r"романтичн", "love songs"),
    (r"работ|фокус", "focus study music"),
    (r"ночн|сон", "night drive music"),
)


def panel_post(path, payload):
    try:
        req = urllib.request.Request(
            PANEL + path, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        sys.stderr.write("panel call failed: %s\n" % e)
        return {}


def mood_query(text):
    for pattern, query in MOOD_MAP:
        if re.search(pattern, text, re.IGNORECASE):
            return query
    return None


PLAY_CMD_RE = re.compile(
    r"^(?:алиса[,\s]+)?(?:пожалуйста[,\s]+)?"
    r"(?:включи|вруби|поставь|проиграй|запусти|сыграй|найди)"
    r"(?:\s+(?:песню|трек|музыку|композицию|исполнителя|группу|альбом|плейлист))?"
    r"\s+(?P<q>.+)$",
    re.IGNORECASE,
)

CASE_SUFFIXES = ("ами", "ями", "ого", "его", "ому", "ему", "ой", "ей", "ом", "ем",
                 "ах", "ях", "а", "я", "у", "ю", "ы", "и", "е")


def strip_case(q):
    words = q.split()
    if not words:
        return q
    last = words[-1]
    for suf in CASE_SUFFIXES:
        if len(last) > len(suf) + 3 and last.lower().endswith(suf):
            words[-1] = last[: -len(suf)]
            break
    return " ".join(words)


def play_query(q):
    import subprocess

    def call(arg):
        try:
            return subprocess.run(SSH_BIN + [arg], capture_output=True, timeout=40)
        except Exception as e:
            sys.stderr.write("play_query call failed: %s\n" % e)
            return None

    for variant in (q, strip_case(q)):
        res = call('/data/yam/bin/ytm-alice --json search "%s"' % variant.replace('"', " "))
        if not res:
            continue
        try:
            tracks = (json.loads(res.stdout.decode("utf-8", "replace")).get("tracks") or [])
        except Exception:
            tracks = []
        if tracks:
            tid = tracks[0].get("id")
            if tid:
                call('/data/yam/bin/ytm-alice play "https://music.youtube.com/watch?v=%s"' % tid)
                sys.stderr.write("play_query: %r -> %r (%r)\n" % (q, variant, tracks[0].get("title")))
                return True
    call('/data/yam/bin/ytm-alice play "%s"' % q.replace('"', " "))
    return False


RECOMMEND_RE = re.compile(
    r"^(?:алиса[,\s]+)?(?:пожалуйста[,\s]+)?"
    r"(?:плей|play|играй|включи музыку|включи мою волну|включи мою подборку|"
    r"включи музыку для меня|включи рекомендации|рекомендации|включи что-нибудь|"
    r"включи что нибудь|поставь что-нибудь)$",
    re.IGNORECASE,
)


def panel_get(path):
    try:
        with urllib.request.urlopen(PANEL + path, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return {}


def smart_mix():
    """Seed a YouTube Music radio from the user's own likes instead of YouTube history."""
    import subprocess
    import random

    def call(arg):
        try:
            return subprocess.run(SSH_BIN + [arg], capture_output=True, timeout=45)
        except Exception as e:
            sys.stderr.write("smart_mix call failed: %s\n" % e)
            return None

    seed = (panel_get("/api/mixseed") or {}).get("artist") or ""
    if seed:
        if play_query(seed):
            sys.stderr.write("smart_mix: history artist %r\n" % seed)
            return

    tracks = []
    res = call("/data/yam/bin/ytm-alice --json liked")
    if res:
        try:
            tracks = json.loads(res.stdout.decode("utf-8", "replace")).get("tracks") or []
        except Exception:
            tracks = []
    tracks = [t for t in tracks if t.get("id") and t.get("title")]
    junk = ("bass boost", "slowed", "8d", "jumpstyle", "oiia", "oija", "mrbeast", "vlog",
            "прикол", "мем", "scooby", "banana")
    clean = [t for t in tracks
             if not any(j in ((t.get("title") or "") + " " + (t.get("artists") or "")).lower()
                        for j in junk)]
    if len(clean) >= 1:
        tracks = clean
    if len(tracks) >= 3:
        pick = random.choice(tracks[:60])
        call('/data/yam/bin/ytm-alice play "https://music.youtube.com/watch?v=%s"' % pick["id"])
        sys.stderr.write("smart_mix: like seed %r\n" % pick.get("title"))
        return

    favs = panel_get("/api/favorites").get("favorites") or []
    favs = [f for f in favs if f.get("id")]
    if favs:
        pick = random.choice(favs[:60])
        call('/data/yam/bin/ytm-alice play "https://music.youtube.com/watch?v=%s"' % pick["id"])
        sys.stderr.write("smart_mix: favorite seed %r\n" % pick.get("title"))
        return

    call("/data/yam/bin/ytm-alice recommendations")
    sys.stderr.write("smart_mix: fallback to recommendations\n")

LED_MANUAL = False  # firmware patterns draw our colors; keep manual writes off


def led(state):
    if not LED_MANUAL:
        return
    import subprocess
    try:
        subprocess.run(SSH_BIN + ["sh /data/led.sh %s" % state], capture_output=True, timeout=10)
    except Exception:
        pass


def led_speaking():
    led("violet")
    threading.Timer(12.0, led, args=("off",)).start()


def led_answer():
    led("blue")
    threading.Timer(1.6, led, args=("violet",)).start()
    threading.Timer(12.0, led, args=("off",)).start()


def run_player_cmd(action):
    import subprocess
    try:
        subprocess.run(SSH_BIN + ["/data/yam/bin/ytm-alice %s" % action],
                       capture_output=True, timeout=25)
    except Exception as e:
        sys.stderr.write("player cmd failed: %s\n" % e)

SYMBOLS = {
    "clearsky": "ясно", "fair": "ясно", "partlycloudy": "переменная облачность",
    "cloudy": "облачно", "fog": "туман", "lightrain": "небольшой дождь",
    "rain": "дождь", "heavyrain": "сильный дождь", "lightrainshowers": "небольшой дождь",
    "rainshowers": "ливень", "heavyrainshowers": "сильный ливень", "lightsleet": "небольшой мокрый снег",
    "sleet": "мокрый снег", "lightsnow": "небольшой снег", "snow": "снег",
    "heavysnow": "сильный снег", "lightsnowshowers": "небольшой снегопад",
    "snowshowers": "снегопад", "thunderstorm": "гроза", "rainandthunder": "дождь с грозой",
    "snowandthunder": "снег с грозой",
}

_lock = threading.Lock()
_weather = {"ts": 0.0, "text": ""}


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


HOURLY_RE = re.compile(
    r"(по\s+часам|на\s+завтра|на\s+вечер|будет\s+ли\s+(?:дождь|снег)|"
    r"когда\s+(?:дождь|снег|потеплеет|похолодает)|прогноз)",
    re.IGNORECASE,
)


def weather_hourly_text():
    try:
        raw = json.loads(fetch(
            "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=%s&lon=%s" % (LAT, LON), 20))
    except Exception as e:
        sys.stderr.write("hourly weather failed: %s\n" % e)
        return None
    series = (raw.get("properties") or {}).get("timeseries") or []
    if not series:
        return None
    parts = []
    for ts in series[:8]:
        t = ts.get("time") or ""
        hh = t[11:13]
        inst = (ts.get("data") or {}).get("instant", {}).get("details", {})
        nxt = (ts.get("data") or {}).get("next_1_hours") or {}
        code = ((nxt.get("summary") or {}).get("symbol_code") or "").split("_")[0]
        temp = round(inst.get("air_temperature", 0))
        desc = SYMBOLS.get(code, "")
        if desc:
            parts.append("%s: %+d, %s" % (hh, temp, desc))
        else:
            parts.append("%s: %+d" % (hh, temp))
    if not parts:
        return None
    return "По часам: " + "; ".join(parts) + "."


def weather_text():
    with _lock:
        if time.time() - _weather["ts"] < 900:
            return _weather["text"]
    try:
        raw = json.loads(fetch(
            "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=%s&lon=%s" % (LAT, LON), 20))
        ts = raw["properties"]["timeseries"][0]
        details = ts["data"]["instant"]["details"]
        code = ts["data"].get("next_1_hours", {}).get("summary", {}).get("symbol_code", "")
        desc = SYMBOLS.get(code.split("_")[0], code or "нет данных")
        temp = round(details.get("air_temperature", 0))
        wind = round(details.get("wind_speed", 0))
        if temp < 0:
            tstr = "минус %d градуса" % abs(temp)
        else:
            tstr = "плюс %d градусов" % temp
        text = "%s, %s, ветер %d метров в секунду" % (tstr, desc, wind)
    except Exception as e:
        sys.stderr.write("weather failed: %s\n" % e)
        text = ""
    with _lock:
        _weather["ts"] = time.time()
        _weather["text"] = text
    return text


def context_prefix():
    try:
        now = datetime.now(ZoneInfo(TZ_NAME))
    except Exception:
        now = datetime.now()
    months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря"]
    days = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    stamp = "%d %s %d, %s, %02d:%02d" % (now.day, months[now.month - 1], now.year,
                                         days[now.weekday()], now.hour, now.minute)
    parts = ["Справочные данные (только для ответа на прямой вопрос): сейчас %s (%s), город: %s."
             % (stamp, TZ_NAME, CITY)]
    w = weather_text()
    if w:
        parts.append("Погода в %s сейчас: %s." % (CITY, w))
    parts.append(
        "Отвечай кратко и по-русски. На вопрос о времени назови только часы и минуты, "
        "о дате — число, месяц и день недели, о погоде — температуру, осадки и ветер как в данных."
    )
    return " ".join(parts)


def rewrite(raw):
    """Return ("forward", bytes) | ("silent", None) | ("text", str)."""
    try:
        data = json.loads(raw)
    except Exception:
        return ("forward", raw)
    if not isinstance(data, dict):
        return ("forward", raw)
    messages = data.get("messages")
    if not isinstance(messages, list) or not messages:
        return ("forward", raw)
    user_msgs = [
        str(m.get("content", "")) for m in messages
        if isinstance(m, dict) and m.get("role") == "user"
    ]
    user_text = (user_msgs[-1] if user_msgs else "").strip()
    user_text = re.sub(r"^(?:(?:алиса|alice)[,\s]+|пожалуйста[,\s]+)+", "", user_text, flags=re.IGNORECASE).strip()

    if not user_text or re.fullmatch(r"[A-Za-z0-9+/=]{8,}", user_text):
        return ("silent", None)
    if TRACK_RE.search(user_text):
        return ("text", now_playing())
    if CONTROL_RE.match(user_text):
        act = control_action(user_text)
        if act:
            threading.Thread(target=run_player_cmd, args=(act,), daemon=True).start()
        return ("text", "Хорошо")
    if OUT_BT_RE.search(user_text):
        threading.Thread(target=set_output, args=("bt",), daemon=True).start()
        return ("text", "Переключаю звук на Bluetooth")
    if OUT_SPK_RE.search(user_text):
        threading.Thread(target=set_output, args=("spk",), daemon=True).start()
        return ("text", "Переключаю звук на колонку")
    if MOOD_RE.search(user_text):
        q = mood_query(user_text)
        if q:
            threading.Thread(target=run_player_cmd, args=("play \"%s\"" % q,), daemon=True).start()
            return ("text", "Включаю")
    if FAV_PLAY_RE.search(user_text):
        threading.Thread(target=panel_post, args=("/api/favorites", {"action": "play", "index": 0}),
                         daemon=True).start()
        return ("text", "Включаю избранное")
    if LIKE_RE.search(user_text):
        def _like():
            panel_post("/api/favorites", {"action": "add_current"})
            led("violet")
            threading.Timer(4.0, led, args=("off",)).start()
        threading.Thread(target=_like, daemon=True).start()
        return ("text", "Добавила в избранное")
    if RECOMMEND_RE.match(user_text):
        threading.Thread(target=smart_mix, daemon=True).start()
        return ("text", "Включаю")
    m = PLAY_CMD_RE.match(user_text)
    if m:
        q = m.group("q").strip().strip('"').strip()
        if q and q.lower() not in ("музыку", "музыка", "песню", "трек", "что-нибудь"):
            threading.Thread(target=play_query, args=(q,), daemon=True).start()
            return ("text", "Включаю")
    if MUSIC_RE.search(user_text):
        return ("text", "Включаю")
    if IDENT_RE.search(user_text):
        return ("text", "Я Qwen, локальная языковая модель. Работаю на сервере пользователя, без облака.")

    if TIME_WEATHER_RE.search(user_text):
        if HOURLY_RE.search(user_text):
            hourly = weather_hourly_text()
            if hourly:
                return ("text", hourly)
        ctx = context_prefix()
        for m in messages:
            if isinstance(m, dict) and m.get("role") == "system":
                m["content"] = str(m.get("content", "")) + "\n\n" + ctx
                break
        else:
            messages.insert(0, {"role": "system", "content": ctx})

    if FACT_RE.search(user_text):
        q = clean_query(user_text)
        led("green")
        try:
            ans = wiki_answer(q) or (None if re.search("[А-Яа-яЁё]", q) else wiki_answer(q, "en"))
        except Exception:
            ans = None
        if ans and len(ans) > 80:
            led_answer()
            return ("text", _shorten(ans))
        led("off")
    threading.Thread(target=led, args=("blue",), daemon=True).start()
    return ("forward", json.dumps(data, ensure_ascii=False).encode("utf-8"))


def clean_response(payload: bytes) -> bytes:
    try:
        data = json.loads(payload)
        changed = False
        for ch in data.get("choices", []):
            msg = ch.get("message") or {}
            content = msg.get("content")
            if isinstance(content, str) and CJK_RE.search(content):
                msg["content"] = CJK_RE.sub("", content).strip()
                changed = True
        return json.dumps(data, ensure_ascii=False).encode("utf-8") if changed else payload
    except Exception:
        return payload


UNCERTAIN_RE = re.compile(
    r"(не знаю|не могу найти|у меня нет (?:информации|данных|доступа)|не располагаю|затрудняюсь|"
    r"не уверен|к сожалению, (?:я )?не|не удалось найти|нет (?:точной )?информации|"
    r"я не обладаю|не имею (?:информации|данных)|я не в курсе|не могу ответить|"
    r"i don'?t know|i do not know|i cannot|i can'?t)",
    re.IGNORECASE,
)

QUESTION_RE = re.compile(
    r"(\?|\b(?:кто|что|где|когда|почему|зачем|сколько|какой|какая|какие|какого|чьей?|который|расскажи)\b)",
    re.IGNORECASE,
)

PREFIX_RE = re.compile(r"^(?:(?:алиса|alice)[,\s]+|пожалуйста[,\s]+)+", re.IGNORECASE)

_WIKI_CACHE = {}

FACT_RE = re.compile(
    r"(кто так|кто така|что так|где наход|когда родил|сколько лет|из чего состоит|"
    r"что означает|расскажи (?:о|про|об)\s|who is|what is|where is)",
    re.IGNORECASE,
)


def clean_query(text):
    t = PREFIX_RE.sub("", text).strip()
    t = re.sub(r"^(?:расскажи(?:те)?(?:\s+(?:мне|нам|пожалуйста))?|скажи(?:те)?|объясни(?:те)?|"
               r"подскажи(?:те)?|напомни(?:те)?)\s+", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^(?:что\s+(?:такое|значит|означает)|кто\s+(?:такой|такая|такие|это)|"
               r"где\s+(?:находится|находятся|найти)|сколько\s+(?:лет|стоит)|"
               r"из\s+чего\s+состоит|what\s+is|who\s+is|where\s+is)\s+", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^(?:про|об|о|мне)\s+", "", t, flags=re.IGNORECASE)
    t = t.strip(" ?.!,…")
    return t or PREFIX_RE.sub("", text).strip()


def _shorten(text, limit=380):
    text = text.replace("\u0301", "").replace("\u200b", "").replace("\u00ad", "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    dot = cut.rfind(". ")
    if dot > 120:
        return cut[: dot + 1]
    return cut.rsplit(" ", 1)[0] + "…"


def _wiki_intro(title, lang):
    from urllib.parse import quote
    try:
        url = ("https://%s.wikipedia.org/w/api.php?action=query&format=json&prop=extracts"
               "&exintro=1&explaintext=1&redirects=1&titles=" % lang) + quote(title)
        js = json.loads(fetch(url, timeout=8).decode("utf-8"))
        for page in ((js.get("query") or {}).get("pages") or {}).values():
            ex = (page.get("extract") or "").strip()
            if ex:
                return ex
    except Exception as e:
        sys.stderr.write("wiki-intro(%s) failed: %s\n" % (lang, e))
    return None


def wiki_answer(query, lang="ru"):
    from urllib.parse import quote
    key = (lang, query.lower().strip())
    hit = _WIKI_CACHE.get(key)
    if hit and time.time() - hit[1] < 3600:
        return hit[0]
    try:
        url = "https://%s.wikipedia.org/w/rest.php/v1/search/page?limit=3&q=%s" % (lang, quote(query))
        js = json.loads(fetch(url, timeout=8).decode("utf-8"))
        for p in (js.get("pages") or [])[:3]:
            title = (p.get("title") or "").strip()
            if not title or "значения" in title.lower():
                continue
            ex = _wiki_intro(title, lang) or re.sub(r"<[^>]+>", "", p.get("excerpt") or "").strip()
            if ex and "может означать" not in ex.lower():
                _WIKI_CACHE[key] = (ex, time.time())
                return ex
    except Exception as e:
        sys.stderr.write("wiki(%s) failed: %s\n" % (lang, e))
    return None


def ddg_answer(query):
    from urllib.parse import quote
    try:
        url = ("https://api.duckduckgo.com/?format=json&no_html=1&skip_disambig=1&q="
               + quote(query))
        js = json.loads(fetch(url, timeout=8).decode("utf-8"))
        return (js.get("AbstractText") or "").strip() or None
    except Exception as e:
        sys.stderr.write("ddg failed: %s\n" % e)
    return None


def web_fallback(payload, request_body):
    try:
        req = json.loads(request_body)
        msgs = req.get("messages") or []
        users = [
            str(m.get("content", "")) for m in msgs
            if isinstance(m, dict) and m.get("role") == "user"
        ]
        question = (users[-1] if users else "").strip()
    except Exception:
        return payload
    question = PREFIX_RE.sub("", question).strip()
    if not question or not QUESTION_RE.search(question):
        return payload
    try:
        data = json.loads(payload)
        ch = (data.get("choices") or [{}])[0]
        content = ((ch.get("message") or {}).get("content") or "").strip()
        if content and len(content) > 25 and not UNCERTAIN_RE.search(content):
            return payload
        q = clean_query(question)
        led("green")
        ans = wiki_answer(q) or (None if re.search("[А-Яа-яЁё]", q) else wiki_answer(q, "en")) or ddg_answer(q)
        if not ans:
            led("off")
            return payload
        text = _shorten(ans)
        ch.setdefault("message", {})["role"] = "assistant"
        ch["message"]["content"] = text
        led_answer()
        sys.stderr.write("web fallback: %r -> %d chars\n" % (question[:50], len(text)))
        return json.dumps(data, ensure_ascii=False).encode("utf-8")
    except Exception as e:
        sys.stderr.write("web fallback failed: %s\n" % e)
        return payload


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _reply(self, content):
        payload = json.dumps({
            "id": "proxy", "object": "chat.completion", "model": "proxy",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content}}],
        }, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _proxy(self, method):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        if method == "POST" and self.path.startswith("/v1/chat/completions"):
            kind, value = rewrite(body)
            if kind == "silent":
                return self._reply(" ")
            if kind == "text":
                return self._reply(value)
            body = value
        req = urllib.request.Request(
            UPSTREAM + self.path, data=body if method == "POST" else None, method=method
        )
        for key in ("Content-Type", "Authorization", "Accept"):
            if self.headers.get(key):
                req.add_header(key, self.headers[key])
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                payload = resp.read()
                if self.path.startswith("/v1/chat/completions"):
                    payload = clean_response(payload)
                    payload = web_fallback(payload, body)
                    threading.Thread(target=led_speaking, daemon=True).start()
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        except urllib.error.HTTPError as e:
            payload = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", e.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as e:
            payload = json.dumps({"error": {"message": "proxy: %s" % e}}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    def do_POST(self):
        self._proxy("POST")

    def do_GET(self):
        self._proxy("GET")


if __name__ == "__main__":
    ThreadingHTTPServer(LISTEN, Handler).serve_forever()
