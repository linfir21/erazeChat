# erazeChat

Энд-ту-энд (E2E) шифрованный чат для двоих, спрятанный внутри игры «2048».
Сервер — чистый ретранслятор: по сети ходит только шифртекст, расшифровать
который может только участник комнаты.

**Бэкенд работает строго как API**: веб-интерфейса нет. Комнаты создаёт
Telegram-бот (по секретному токену), клиенты (игра) обмениваются ключами
и шифртекстом через открытые эндпоинты.

## Состав репозитория

| Каталог | Описание |
|---|---|
| `DjangoChat/` (этот каталог) | Бэкенд: Django 6 + Django REST Framework + Django Channels (WebSocket) |
| `../2048/` | Клиент: Godot 4.7 (Android/ПК), игра «2048» со скрытым чатом |

## Как это работает

### Вход в чат

Чат открывается секретным жестом: **5 тапов по надписи «2048»** на главном
экране. Далее вводится код комнаты (8 символов) и никнейм.

### Модель комнат

- Комната создаётся только через API (`POST /api/room/create/`) **по токену
  бота**, код генерируется случайно. Код комнаты — «адрес» чата.
- В комнате **два слота** (A и B). Слот закрепляется за публичным ключом
  участника и сохраняется на сервере, даже если оба участника отключились.
- Клиент хранит свою пару ключей X25519 на устройстве (`user://e2ee_identity`),
  поэтому после перезапуска приложения он заходит в ту же комнату под тем же
  слотом.
- Вернуться в комнату можно в любой момент — достаточно кода комнаты и
  своего ключа. Чужой (третий) участник будет отклонён (`400 Room is full`).

### Шифрование (E2EE)

Реализация — `2048/scripts/E2ee.gd`:

- **X25519** (порт TweetNaCl) — обмен ключами Диффи-Хеллмана;
- общий секрет хэшируется SHA-256, из него выводятся два ключа:
  шифрование и имитовставка (HKDF-стиль с разделением контекста);
- сообщения шифруются **AES-256-CBC** с PKCS#7, к каждому сообщению
  добавляется **HMAC-SHA256** (encrypt-then-MAC);
- по сети передаётся `base64(iv ‖ hmac ‖ шифртекст)`.

Сервер не видит ни текстов сообщений, ни общего секрета — только публичные
ключи и шифртекст.

### История переписки и офлайн-доставка

История хранится **локально на устройстве** в зашифрованном виде:
файл `user://chat_<код комнаты>.log`. При входе в комнату история
расшифровывается общим секретом и выводится в чат.

Сервер при каждом сообщении кладёт шифртекст в «ящик» комнаты
(`RoomMessage`) и ретранслирует его онлайн-участникам. При входе клиент
забирает накопленное (`POST /messages/fetch/`), сервер удаляет выданное —
сообщения доходят, даже если адресат был офлайн. Дубли отсекаются на клиенте
по локальной истории.

## API

Все эндпоинты под префиксом `/api/`.

| Метод | Путь | Кто вызывает | Описание |
|---|---|---|---|
| `POST` | `/api/room/create/` | **только бот** (токен) | Создать комнату → `{room_id}` |
| `POST` | `/api/room/<id>/join/` | клиент (игра) | Войти, тело `{"public_key": hex}` → `{status, participant, other_public_key}` |
| `GET` | `/api/room/<id>/keys/` | клиент (игра) | Все публичные ключи комнаты → `{public_keys: [...]}` |
| `WS` | `/ws/chat/<id>/` | клиент (игра) | Ретрансляция `{"payload": "..."}` всем участникам (сообщение также кладётся в ящик) |
| `POST` | `/api/room/<id>/messages/fetch/` | клиент (игра) | Забрать накопленные зашифрованные сообщения (ящик очищается) → `{messages: [...]}` |

Создание комнаты требует заголовок:

```
X-Bot-Token: <ERAZE_BOT_TOKEN>
```

Без корректного токена — `403 Unauthorized`. Остальные эндпоинты открыты:
владение кодом комнаты и приватным ключом — и есть авторизация.

Ошибки join: `404 Room not found`, `400 public_key is required`,
`400 Room is full` (чужой ключ в заполненной комнате).

### Пример: создание комнаты из бота (Python)

```python
import requests

API = "https://chat.example.com/api"
TOKEN = "тот-что-в-ERAZE_BOT_TOKEN"

r = requests.post(f"{API}/room/create/", headers={"X-Bot-Token": TOKEN}, timeout=10)
r.raise_for_status()
room_id = r.json()["room_id"]      # например "BZJY43H6" — отправь его пользователям
```

## Конфигурация (переменные окружения)

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `DJANGO_SECRET_KEY` | ключ разработки | **Обязательно** задать свой в продакшене |
| `DJANGO_DEBUG` | `0` | `1` — только для разработки |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost` | Домен(ы) сервера через запятую |
| `ERAZE_BOT_TOKEN` | задан в коде | Токен бота для создания комнат. На сервере задай свой через env |
| `REDIS_HOST` | — | Если задан — Redis как channel layer; иначе InMemory (один процесс) |
| `REDIS_PORT` | `6379` | Порт Redis |

## Запуск локально (разработка)

```bash
cd DjangoChat
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
python manage.py migrate
# для локальной разработки включи DEBUG и укажи токен:
set DJANGO_DEBUG=1                       # Windows (PowerShell: $env:DJANGO_DEBUG=1)
set ERAZE_BOT_TOKEN=dev-bot-token
python manage.py runserver               # daphne в INSTALLED_APPS отдаёт HTTP + WebSocket
```

Сервер: `http://127.0.0.1:8000`. В клиенте `../2048/scripts/ChatManager.gd`
укажи `SERVER_HOST = "127.0.0.1:8000"`, `USE_TLS = false`.

## Деплой на сервер (Ubuntu VPS + интернет)

Ниже — рабочая схема: **daphne** (ASGI: HTTP + WebSocket) за **nginx** с
бесплатным TLS-сертификатом от Let's Encrypt. Подразумевается, что у тебя
уже есть VPS и домен, например `chat.example.com`, с A-записью на IP сервера.

### 1. Базовая подготовка сервера

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip nginx ufw
sudo ufw allow 'Nginx Full'
sudo ufw allow OpenSSH
sudo ufw enable
```

### 2. Зависимости проекта

```bash
sudo mkdir -p /opt/erazechat && sudo chown $USER /opt/erazechat
# скопируй проект на сервер (кроме venv/ и db.sqlite3 — их создадим на месте):
git clone <твой-репозиторий> /opt/erazechat/DjangoChat   # или scp/rsync
cd /opt/erazechat/DjangoChat

python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

### 3. Переменные окружения

```bash
sudo mkdir -p /etc/erazechat
sudo nano /etc/erazechat/env
```

Содержимое (замени значения):

```
DJANGO_SECRET_KEY=сгенерируй-новый-случайный-ключ
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=chat.example.com
ERAZE_BOT_TOKEN=длинная-случайная-строка-для-бота
```

Затем:

```bash
sudo chmod 600 /etc/erazechat/env
set -a; . /etc/erazechat/env; set +a
venv/bin/python manage.py migrate
```

> Один процесс daphne с InMemory-channel-layer — нормально для старта.
> Если планируешь несколько воркеров/инстансов — поставь Redis
> (`sudo apt install redis-server`) и добавь в env: `REDIS_HOST=127.0.0.1`.

### 4. systemd-сервис

```bash
sudo nano /etc/systemd/system/erazechat.service
```

```ini
[Unit]
Description=erazeChat backend (daphne)
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/erazechat/DjangoChat
EnvironmentFile=/etc/erazechat/env
ExecStart=/opt/erazechat/DjangoChat/venv/bin/daphne -b 127.0.0.1 -p 8000 core.asgi:application
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now erazechat
systemctl status erazechat          # должен быть active (running)
```

### 5. nginx

```bash
sudo nano /etc/nginx/sites-available/erazechat
```

```nginx
server {
    listen 80;
    server_name chat.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # WebSocket
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/erazechat /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 6. HTTPS (обязательно для Android!)

Приложения Android с targetSdk 28+ **блокируют незашифрованный трафик**,
поэтому для реального устройства нужен HTTPS/WSS:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d chat.example.com
# сертификат сам пропишется в конфиг nginx и будет обновляться
```

### 7. Проверка

```bash
# без токена — 403:
curl -i -X POST https://chat.example.com/api/room/create/
# с токеном — 201 и код комнаты:
curl -s -X POST -H "X-Bot-Token: твой-токен" https://chat.example.com/api/room/create/
```

### 8. Подключение игры

1. В `../2048/scripts/ChatManager.gd` укажи:
   ```gdscript
   const SERVER_HOST := "chat.example.com"
   const USE_TLS := true
   ```
2. Собери APK: `Собрать APK.bat`.
3. Пользователь запускает игру → 5 тапов по «2048» → вводит код комнаты
   (который бот выдал обоим собеседникам) и ник.

## Структура бэкенда

```
chat/
├── models.py      # Room, RoomKey (служебные ключи — только публичные)
├── views.py       # create (только бот) / join / keys / fetch (DRF)
├── consumers.py   # WebSocket-ретранслятор (Channels)
├── routing.py     # ws/chat/<room_id>/
└── urls.py
core/
├── settings.py    # env-конфиг, токен бота, channel layer, ASGI
├── asgi.py
└── urls.py        # только /admin/ и /api/
```

## Ограничения и замечания по безопасности

- **Привязка к устройству.** Участник идентифицируется ключом. При удалении
  приложения доступ к старой комнате теряется (слот остаётся за старым ключом).
- **Приватный ключ** лежит в `user://e2ee_identity` в открытом (hex) виде.
  На Android это приватный каталог приложения, но на rooted-устройствах
  файл доступен.
- **Нет PFS**: общий секрет долгоживущий, компрометация приватного ключа
  вскроет всю переписку.
- Ящик недоставленных сообщений доступен по коду комнаты без авторизации,
  но содержит только шифртекст — прочитать его может лишь участник
  с приватным ключом.
- `DEBUG=0` по умолчанию; `SECRET_KEY` и `ERAZE_BOT_TOKEN` берутся из env.
# erazeChat
