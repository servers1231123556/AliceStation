# AliceStation — своя Алиса на Яндекс Станции Мини 2

Полный комплект «с нуля»: перехват запросов станции, локальная модель вместо облака,
музыка из YouTube Music, своя панель на LXC и **нативное Android-приложение**,
Bluetooth-вывод, эквалайзер прошивки, будильник и подсветка.

Проверено на железе: **Станция Мини 2** (`yandexmini_2`, Buildroot 2020.02, ядро 4.9.68,
userland ARMHF/glibc 2.30, 238 МБ RAM).

---

## 1. Что умеет

| Возможность | Как работает |
|---|---|
| Голосовые ответы от локальной модели | Quasar Bridge подменяет облако на `llm-proxy` → Ollama `qwen2.5:3b` |
| Музыка без подписки Яндекса | `ytm-alice` играет YouTube Music через VPN |
| Поиск и запуск по голосу | поиск → запуск **по ID** (не ломается на падежах и латинице) |
| Рекомендации | сид — топ-исполнитель из истории, затем лайки, затем избранное |
| Радио по настроению | «включи что-нибудь спокойное» → подборка |
| Избранное и очередь | голосом и в приложении, обновление каждые 5 с |
| Будильник станции | включает музыку в заданное время (часовой пояс с телефона) |
| Погода по часам | met.no, карточка в приложении + голосовой ответ |
| Факты | Википедия, если модель не уверена |
| Подсветка | паттерны прошивки: «думает» — синяя загрузка, «говорит» — фиолетовый |
| Bluetooth-вывод | звук станции на усилитель (bluealsa + принудительный формат) |
| Эквалайзер | 5 полос в конфиге прошивки (см. §10 — влияет на голос, не на музыку) |

---

## 2. Архитектура

```
голос → Станция (aliced) → Quasar Bridge :8443 → llm-proxy :11435 → Ollama
                                   │                    └→ Википедия / met.no
                                   └→ облако Яндекса (погода, будильники, прочее)

музыка: ytm-alice → YouTube Music (трафик Google → LXC → sing-box VLESS)

управление: Android / веб-панель :8099 → SSH → станция
```

---

## 3. Структура проекта

```
AliceStation/
├─ README.md
├─ station/                  скрипты для колонки
│  ├─ led.sh                 подсветка: green | blue | violet | off (TTL-защита)
│  ├─ ledp/                  LED-паттерны (green, chase, violet)
│  ├─ led-janitor.sh         гасит зависшие анимации прошивки
│  ├─ ytm-led.sh             «огонь» во время музыки
│  ├─ alarm-daemon.sh        будильник станции
│  ├─ audio-out.sh           вывод: bt | spk (+ перезапуск трека)
│  ├─ audio-watch.sh         автопереключение при подключении Bluetooth
│  ├─ bt.sh                  поиск/сопряжение Bluetooth
│  ├─ asound.internal        конфиг: внутренний динамик (по умолчанию)
│  ├─ asound.bt              конфиг: Bluetooth-усилитель
│  ├─ ytm-routes.sh          маршруты Google → таблица 200
│  ├─ ytm-routes-watch.sh    сторож маршрутов
│  ├─ ytm-alice-settings.json  рабочие настройки ytm-alice
│  ├─ eqcfg.py               разбор user_config.dat (эквалайзер)
│  └─ init.d/                рабочие автозапуски S96…S99
├─ lxc/
│  ├─ llm-proxy.py           мозг: команды, погода, поиск, музыка, LED
│  ├─ sound-panel/           API + веб-панель (server.py, index.html)
│  ├─ bridge/config.json     конфиг Quasar Bridge
│  ├─ bridge/runtime.env.example
│  └─ singbox-config.example.json
├─ android/
│  ├─ AliceHome.apk          готовое приложение 2.0 (нативное)
│  ├─ build.ps1              сборка APK без Gradle
│  └─ project/               исходники
├─ eq-experiment/            НЕ РАБОТАЕТ, оставлено для будущей попытки
│  ├─ eqrelay.c              ALSA-loopback relay с 5 биквадами
│  ├─ eqrelay.sh, eq-watch.sh, build_bootlin.sh
│  └─ eqrelay-b              собранный armhf-бинарник
├─ tools/                    ssh-хелперы (ssh_run.py, sh.py)
└─ vendor/                   установочные пакеты (bridge, ytm-alice, yam)
```

---

## 4. Требования

- Станция Мини 2 с root по SSH (dropbear, порт 2222).
- LXC/мини-ПК Debian 12 с root и интернетом (`192.168.0.91` в примерах).
- Ollama (`192.168.0.82:11434`) с `qwen2.5:3b`.
- VLESS-сервер (для YouTube Music).
- Для сборки APK: JDK 17 + Android SDK build-tools 34 (или готовый APK из `android/`).

Все IP — заглушки, замените на свои.

---

## 5. Установка станции

```bash
ssh -p 2222 root@192.168.0.90
```

### 5.1 Quasar Bridge

```bash
scp -P 2222 vendor/qb-pkg.tar.gz root@192.168.0.90:/data/
cd /data && tar xzf qb-pkg.tar.gz -C /data/opt/quasar-bridge
sh /data/opt/quasar-bridge/install.sh
# конфиг
scp -P 2222 lxc/bridge/config.json root@192.168.0.90:/data/opt/quasar-bridge/config.json
cat > /data/opt/quasar-bridge/runtime.env <<'EOF'
QUASAR_LLM_BASE_URL=http://192.168.0.91:11435/v1
QUASAR_LLM_MODEL=qwen2.5:3b
EOF
sh /data/opt/quasar-bridge/app/control.sh restart
sh /data/opt/quasar-bridge/app/control.sh check-backends   # ждём "LLM: ok"
```

### 5.2 YouTube Music

```bash
scp -P 2222 vendor/yam-aarch64 root@192.168.0.90:/data/yam/bin/yam
scp -P 2222 vendor/ytm-alice.yampkg root@192.168.0.90:/data/
chmod +x /data/yam/bin/yam
/data/yam/bin/yam install /data/ytm-alice.yampkg
ytm-alice daemon start
```

Голосовые команды — из `station/ytm-alice-settings.json` (ключ `voice_commands`).
Важно: **`включи {query}` не маппится** — поиск и запуск делает прокси.

### 5.3 Блокировка облачной музыки

```bash
cp /etc/hosts /etc/hosts.bak
cat >> /etc/hosts <<'EOF'
127.0.0.1 api.music.yandex.net
127.0.0.1 ws.api.music.yandex.net
127.0.0.1 music.yandex.net
127.0.0.1 music.yandex.ru
127.0.0.1 quasar.yandex.net
EOF
```

### 5.4 Скрипты и автозапуски

```bash
scp -P 2222 station/*.sh root@192.168.0.90:/data/
scp -P 2222 -r station/ledp root@192.168.0.90:/data/
scp -P 2222 station/init.d/S9* root@192.168.0.90:/etc/init.d/
chmod +x /data/*.sh /etc/init.d/S9*
sh /data/ytm-routes.sh
```

### 5.5 Звук

```bash
scp -P 2222 station/asound.internal station/asound.bt root@192.168.0.90:/etc/
cp /etc/asound.internal /etc/asound.conf    # по умолчанию — динамик
```

Bluetooth: `sh /data/audio-out.sh bt` (требует `asound.bt` с 48 кГц/S16/стерео).

### 5.6 Подсветка

```bash
mkdir -p /data/ledp
scp -P 2222 station/ledp/* root@192.168.0.90:/data/ledp/
```

Паттерны прошивки (по желанию, см. §9): заменить
`/system/vendor/quasar/ledpatterns/oknix/alice_thinking.led` на синюю загрузку,
`alice_speaking.led` — на ровный фиолетовый. Оригиналы сохранить в `/data/ledp/orig/`.

---

## 6. Установка LXC

```bash
apt install -y python3 sing-box nftables
cp lxc/singbox-config.example.json /etc/sing-box/config.json   # свой сервер
systemctl enable --now sing-box

mkdir -p /opt/llm-proxy /opt/sound-panel
cp lxc/llm-proxy.py /opt/llm-proxy/proxy.py
cp lxc/sound-panel/* /opt/sound-panel/
ssh-keygen -t ed25519 -f /root/.ssh/station -N ''
ssh-copy-id -p 2222 -i /root/.ssh/station root@192.168.0.90
```

Юниты (оба с `Restart=always`):

```ini
# /etc/systemd/system/llm-proxy.service
ExecStart=/usr/bin/python3 /opt/llm-proxy/proxy.py
Environment=UPSTREAM=http://192.168.0.82:11434

# /etc/systemd/system/sound-panel.service
ExecStart=/usr/bin/python3 /opt/sound-panel/server.py
```

```bash
systemctl enable --now llm-proxy sound-panel
```

Панель: `http://192.168.0.91:8099` (данные: `favorites.json`, `history.json` рядом).

---

## 7. Android-приложение 2.0 (нативное)

Готовый файл: `android/AliceHome.apk` (пакет `ru.alice.remote`, minSdk 24).

```bash
adb install -r android/AliceHome.apk
```

Экраны: **Дом** (станция, трек, погода по часам, Bluetooth, вывод),
**Звук** (5 полос, пресеты, DRC), **Музыка** (плеер, перемотка, избранное, очередь),
**Ещё** (статус станции, быстрые команды, будильник).

Долгий тап по заголовку «Мой дом» — смена адреса панели.
Открыть сразу нужную вкладку: `adb shell am start -n ru.alice.remote/.MainActivity --ei tab 2`.

Сборка:

```powershell
powershell -ExecutionPolicy Bypass -File android\build.ps1
# ключ подписи: F:\android\app.jks (не удалять!)
```

---

## 8. Громкость — важно

На станции **две** громкости:

| Контроль | Что это | Как ставить |
|---|---|---|
| `numid=1` `SPK Master Playback Volume` | аппаратная, 0…255 | держать **255** |
| `numid=190` `Master Playback Volume` | программная, 0…255 | её крутят «громче/тише» и панель |

Если звук пропал — проверьте именно эти два и mute:

```bash
amixer -c0 cset numid=1 255
amixer -c0 cset numid=190 153,153     # ~60%
amixer -c0 cset numid=189 off         # SPK mute
echo 0 > /data/quasar/data/is_speaker_muted
```

---

## 9. Подсветка

- `led.sh green|blue|violet|off` — свои состояния с TTL (зелёная 90 с, синяя 40 с, фиолетовая 25 с).
- `led-janitor.sh` — каждые 2 с убивает зависшие `led_util` прошивки старше 22 с и гасит диоды.
- Паттерны прошивки: формат `loop` + строки `<rrggbb> ×6 <длительность>`.
- Если кольцо «застыло» — `sh /data/led.sh off`.

---

## 10. Эквалайзер: честно

- 5 полос пишутся в `user_config.dat` (`device_config.equalizer`), значение переживает перезагрузку.
- **На музыку это не влияет**: `ytm-alice` играет через GStreamer → ALSA напрямую,
  мимо DSP-тракта `maind`. Слышимая часть — только голос Алисы (и то не гарантировано).
- Попытка сделать настоящий EQ для музыки лежит в `eq-experiment/`:
  схема «loopback + relay с биквадами» собирается (кросс-тулчейн Bootlin, glibc 2.30),
  но звук до динамика не доходит — поток идёт рывками.
  Автозапуск отключён (`S98eqrelay.disabled`), состояние возвращено на динамик.
  **Не включать без отладки** — останетесь без звука.

---

## 11. Обслуживание

| Задача | Команда |
|---|---|
| Логи диалогов | `tail -f /data/opt/quasar-bridge/conversations.jsonl` |
| Перезапуск бриджа | `sh /data/opt/quasar-bridge/app/control.sh restart` |
| Логи прокси/панели | `journalctl -u llm-proxy -f` / `-u sound-panel -f` |
| Вернуть звук на динамик | `sh /data/audio-out.sh spk` |
| Проверить плеер | `ytm-alice status` |
| Очередь / избранное | `/api/queue`, `/api/favorites` |
| Перезапуск плеера при `error` | `ytm-alice daemon restart` |

---

## 12. Известные проблемы

1. **Звонки, охрана, сценарии, подписка** — только облако Яндекса, локального API нет.
2. **Лайки в аккаунт** не ставятся: `ytm-alice` на TV-токене без cookies → «избранное» локальное.
3. **Bluetooth-ключи** не сохраняются после перезагрузки (BlueZ на read-only разделе).
4. **Эквалайзер для музыки** не работает (см. §10).
5. **После перезагрузки** громкость может оказаться в нуле — поднять по §8.
6. **Википедия** иногда 429 → отвечает модель (есть кэш на час).
7. **Скорость**: старт трека ~12 с (VPN), ответ модели 2–6 с.
8. **LED-движок** залипает при грубом вмешательстве — лечится `led.sh off` или перезагрузкой.

---

## 13. Журнал изменений

- Нативное приложение 2.0 (4 экрана, виджет, переход по `--ei tab N`).
- Погода по часам (met.no) — карточка и голос.
- Избранное и очередь (голос + UI), история прослушиваний, рекомендации от истории.
- Радио по настроению (7 настроений).
- Будильник станции с часовым поясом телефона.
- Поиск → запуск по ID; сторож YouTube-видео.
- Подсветка: подмена паттернов прошивки + уборщик зависших анимаций.
- Эквалайзер: попытка реального DSP (неудачная, отключена).
- Исправления: громкость (два контроля), кэш панели, `?t=` в URL, зависший фиолетовый.

---

Собрано в живой отладке на реальной станции. Скрипты рабочие, проверены на железе.
