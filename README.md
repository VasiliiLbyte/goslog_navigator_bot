# ГосЛог Навигатор — Telegram-бот

Помощник для бизнеса по подключению к национальной системе **ГосЛог**: онбординг, мастер подготовки к подаче, проверка контрагентов по ИНН и утренние алерты.

## Стек

- **Python 3.12** + type hints  
- **aiogram 3.x** — Telegram Bot API (webhook или polling)  
- **FastAPI** + uvicorn — HTTP-сервер и webhook  
- **SQLAlchemy 2.x** + asyncpg — PostgreSQL (async)  
- **Alembic** — миграции схемы БД  
- **Redis** — FSM storage для aiogram  
- **httpx** — Ofdata и публичные HTTP-проверки  
- **APScheduler** (AsyncIOScheduler) — ежедневные алерты  
- **reportlab** — генерация PDF в мастере  
- **loguru** — логи  
- **Pydantic Settings** — конфигурация из `.env`

## Возможности по модулям

| Модуль | Суть |
|--------|------|
| **1–2** | `/start`, выбор ИП/ООО и ОКВЭД 52.29, **мастер из 5 шагов** (ИНН → Ofdata → PDF → инструкция). |
| **3** | `/проверить_инн` — проверка контрагента (Ofdata + попытка сверки с публичной страницей ГосЛог), сохранение в БД; `/контрагенты` — список; `/алерты_вкл` / `/алерты_выкл` — подписка на утреннюю сводку; `/мой_инн` — свой ИНН для строки «ваш ИНН в реестре» в алертах. |

Команды с кириллицей нужно добавить в **@BotFather** (Menu commands), иначе пользователи вводят их вручную.

## Быстрый старт

Рабочий каталог — тот, где лежат **`pyproject.toml`** и **`alembic.ini`** (в репозитории это обычно вложенная папка `goslog_navigator_bot/`).

### 1. Виртуальное окружение и зависимости

```bash
cd goslog_navigator_bot
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate

pip install -e ".[dev]"
```

Если `pip install -e .` ругается на discovery пакетов (несколько верхнеуровневых каталогов), временно можно запускать так:

```bash
export PYTHONPATH=.
# или: PYTHONPATH=. python -m goslog_navigator_bot.polling
```

### 2. Окружение

```bash
cp goslog_navigator_bot/.env.example .env
```

Обязательно задайте **`BOT_TOKEN`**, **`DB_URL`**, для webhook — **`WEBHOOK_URL`**.  
Для автозаполнения по ИНН (мастер и модуль 3) — **`FNS_API_KEY`** (см. `.env.example`).

### 3. PostgreSQL и Redis

```bash
docker run -d --name pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=goslog_navigator -p 5432:5432 postgres:16
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

### 4. Миграции БД

```bash
alembic upgrade head
```

Без этого шага новые таблицы/колонки (в т.ч. **модуль 3**: `counterparties`, поля алертов в `users`) в БД не появятся.

### 5. Запуск бота

```bash
# Локально без туннеля — polling (в .env: BOT_MODE=polling)
python -m goslog_navigator_bot.polling

# Прод с публичным URL — webhook (BOT_MODE=webhook)
uvicorn goslog_navigator_bot.main:app --host 0.0.0.0 --port 8000 --reload
```

Прокси для Telegram (при необходимости):

```bash
TELEGRAM_PROXY_URL=http://127.0.0.1:10809
```

### 6. Healthcheck (webhook-режим)

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

## Переменные окружения (фрагмент)

См. полный список в **`goslog_navigator_bot/.env.example`**. Кратко для модуля 3:

- **`GOSLOG_PUBLIC_CHECK_URL`** — базовый URL публичной проверки (по умолчанию `https://goslog.ru/check`).  
- **`DAILY_ALERTS_ENABLED`**, **`DAILY_ALERTS_HOUR`**, **`DAILY_ALERTS_MINUTE`**, **`DAILY_ALERTS_TIMEZONE`** — планировщик утренних алертов (по умолчанию 9:00, `Europe/Moscow`).

## Структура проекта

```
goslog_navigator_bot/          # корень Python-проекта (pyproject.toml, alembic.ini)
├── alembic/
│   └── versions/              # миграции (0001 wizard_sessions, 0002 counterparties + алерты)
├── goslog_navigator_bot/      # пакет приложения
│   ├── main.py                # FastAPI + webhook + lifespan (в т.ч. APScheduler)
│   ├── polling.py             # long polling + тот же планировщик
│   ├── bot/
│   │   ├── handlers/
│   │   │   ├── start.py       # /start, онбординг
│   │   │   ├── wizard.py      # мастер 5 шагов, Ofdata, PDF
│   │   │   └── check.py       # модуль 3: ИНН, контрагенты, алерты
│   │   ├── keyboards/
│   │   └── states/
│   │       └── user.py        # FSM (онбординг, wizard, проверка ИНН, мой ИНН)
│   ├── core/
│   ├── database/
│   │   ├── models.py          # User, WizardSession, Counterparty
│   │   ├── session.py
│   │   └── repositories/
│   ├── services/
│   │   └── counterparty_verify.py
│   └── scheduler/
│       └── daily_alerts.py
├── .env.example               # внутри пакета: goslog_navigator_bot/.env.example
└── README.md
```

## Тестирование

```bash
pytest --cov=goslog_navigator_bot --cov-report=term-missing
```

## Docker Compose

Отдельный `docker-compose.yml` в репозитории можно добавить при необходимости; сейчас достаточно ручного `docker run` для Postgres/Redis (см. выше).

## Лицензия

MIT
