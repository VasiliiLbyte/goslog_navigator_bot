# ГосЛог Навигатор — Telegram-бот

Помощник для бизнеса по подключению к национальной системе **ГосЛог**.

## Стек

- **Python 3.12** + type hints
- **aiogram 3.x** — Telegram Bot API (webhook-режим)
- **FastAPI** + uvicorn — HTTP-сервер
- **SQLAlchemy 2.x** + asyncpg — PostgreSQL (async)
- **Redis** — FSM storage для aiogram
- **loguru** — структурированные логи
- **Pydantic Settings** — конфигурация из `.env`

## Быстрый старт

### 1. Клонируйте и установите зависимости

```bash
git clone <repo-url> && cd goslog-navigator-bot
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -e ".[dev]"
```

### 2. Настройте окружение

```bash
cp goslog_navigator_bot/.env.example .env
# Отредактируйте .env — обязательно укажите BOT_TOKEN и DB_URL
```

### 3. Поднимите PostgreSQL и Redis

```bash
# Если есть Docker:
docker run -d --name pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=goslog_navigator -p 5432:5432 postgres:16
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

### 4. Запустите бота

```bash
# Для локальной разработки (polling — без webhook/туннелей)
# Укажите BOT_MODE=polling в .env
python -m goslog_navigator_bot.polling

# Для webhook-режима (нужен публичный URL, например через ngrok)
# Укажите BOT_MODE=webhook в .env
uvicorn goslog_navigator_bot.main:app --host 0.0.0.0 --port 8000 --reload
```

Если доступ к Telegram ограничен сетью, добавьте прокси в `.env`:

```bash
TELEGRAM_PROXY_URL=http://127.0.0.1:10809
```

Для `v2rayN` обычно подходит локальный HTTP-прокси на `10809`.

### 5. Проверьте healthcheck

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

## Docker Compose (планируется)

```yaml
# docker-compose.yml — будет добавлен в следующем модуле
```

## Структура проекта

```
goslog_navigator_bot/
├── bot/
│   ├── handlers/
│   │   └── start.py          # /start + онбординг
│   ├── keyboards/
│   │   └── inline.py         # Inline-кнопки ИП/ООО, ОКВЭД
│   ├── states/
│   │   └── user.py           # FSM-состояния
│   └── middlewares/           # (для будущих middleware)
├── core/
│   ├── config.py              # Pydantic Settings
│   └── logger.py              # loguru setup
├── database/
│   ├── models.py              # User, WizardSession
│   └── session.py             # async sessionmaker
├── .env.example
└── main.py                    # FastAPI + webhook + lifespan
```

## Тестирование

```bash
pytest --cov=goslog_navigator_bot --cov-report=term-missing
```

## Лицензия

MIT
