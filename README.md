# CS2 Tournament Center — Telegram Bot + Mini App

Готовый каркас для турниров по Counter-Strike 2: Telegram-бот на `aiogram 3.x`, API на FastAPI, асинхронный SQLAlchemy 2.x и Mini App на React + TypeScript + Vite.

## Архитектура

```text
Telegram Bot (aiogram) ──┐
                         ├── FastAPI /api/v1 ── SQLAlchemy async ── PostgreSQL
Mini App (React/Vite) ───┘                         └── SQLite для локального старта
```

Бот и API запускаются одним процессом: FastAPI обслуживает HTTP, а aiogram работает в фоне на том же event loop. Для нескольких production-инстансов polling нужно заменить на Telegram webhook и вынести запуск бота в отдельный процесс.

## Структура

```text
backend/
  app/
    api/             FastAPI routes и auth dependencies
    bot/             aiogram handlers и keyboards
    security/        проверка WebApp initData и Telegram Login Widget
    services/        регистрация, генерация сеток, результаты, продвижение
    models.py        SQLAlchemy модели Users/Teams/Tournaments/Matches
    schemas.py       Pydantic DTO и валидация входных данных
    main.py          FastAPI lifespan + aiogram polling
  migrations/        Alembic env и initial migration
frontend/
  src/               React Mini App, API-клиент, Telegram WebApp bridge
docker-compose.yml   PostgreSQL + backend + nginx frontend
```

## Модели и важные правила

- `users`: Telegram ID, username, CS2 nickname, Steam ID и роль `user/admin`.
- `teams` + `team_members`: команда с капитаном, тэгом и ссылками на профили игроков.
- `tournaments`: `1v1/2v2/5v5`, `registration/ongoing/finished`, призовой фонд, регламент и дедлайн.
- `tournament_registrations`: либо `team_id`, либо `user_id`; для одиночной регистрации создаётся внутренний singleton-team, чтобы матч-граф всегда работал через `team_id`.
- `matches`: участники, счёт, победитель, статус и ссылки на следующий матч. Для double elimination есть winners bracket, losers bracket и reset grand final.

Проверки выполняются на API-уровне и в БД: дедлайн, лимит участников, точный размер состава, уникальность регистрации и невозможность ничьей в матче на выбывание.

## API

Все Mini App endpoints требуют заголовок:

```http
X-Telegram-Init-Data: <window.Telegram.WebApp.initData>
```

Также поддерживается `Authorization: tma <initData>`. Подпись, `auth_date`, срок жизни и Telegram user payload проверяются на сервере. Не доверяйте `initDataUnsafe` на клиенте.

Основные endpoints:

```text
GET  /api/v1/me
PATCH /api/v1/me
GET  /api/v1/me/stats
GET  /api/v1/tournaments?status=registration|ongoing|finished
GET  /api/v1/tournaments/{id}
GET  /api/v1/tournaments/{id}/bracket
POST /api/v1/tournaments/{id}/registrations
GET  /api/v1/tournaments/{id}/registrations/me
POST /api/v1/auth/telegram-login                 # optional Login Widget

POST /api/v1/admin/tournaments
POST /api/v1/admin/tournaments/{id}/generate-bracket
POST /api/v1/admin/matches/{id}/result
POST /api/v1/admin/matches/{id}/notify
POST /api/v1/admin/tournaments/{id}/notify
```

`POST /registrations` принимает:

```json
{
  "registration_type": "team",
  "team_name": "Dust2 Kings",
  "team_tag": "D2K",
  "member_telegram_ids": [123456789, 987654321],
  "player_profile_links": ["https://steamcommunity.com/id/example"]
}
```

Для одиночной регистрации достаточно отправить `registration_type: "single"`.

## Локальный запуск

1. Создайте бота через `@BotFather` и скопируйте `.env.example` в `.env`.
2. Укажите `BOT_TOKEN`, `WEBAPP_URL` и свой Telegram ID в `ADMIN_TELEGRAM_IDS`.
3. Для первого старта можно оставить SQLite:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

Для фронтенда в другом терминале:

```powershell
cd frontend
npm install
$env:VITE_API_URL="http://localhost:8000/api/v1"
npm run dev
```

Telegram Mini App должен открываться по HTTPS. Для разработки подойдёт `ngrok`/Cloudflare Tunnel; URL туннеля нужно записать в `WEBAPP_URL` и указать в BotFather как Web App URL.

## PostgreSQL и Docker

Заполните `.env`, затем:

```powershell
docker compose up --build
```

Mini App будет доступен на `http://localhost:8080`, API — на `http://localhost:8000`. В production замените localhost на HTTPS-домен и поставьте reverse proxy с TLS.

Для миграций:

```powershell
cd backend
alembic upgrade head
```

`AUTO_CREATE_DB=true` оставлен для удобного первого старта. В production предпочтительнее `AUTO_CREATE_DB=false` и отдельный шаг `alembic upgrade head` в deploy pipeline.

## Администраторский сценарий

1. Укажите Telegram ID администратора в `ADMIN_TELEGRAM_IDS`.
2. Создайте турнир через Mini App или `POST /api/v1/admin/tournaments`.
3. После закрытия регистрации вызовите `generate-bracket`.
4. Перед матчем отправьте `POST /admin/matches/{id}/notify`.
5. После проверки счёта отправьте `POST /admin/matches/{id}/result`.
6. Сервис автоматически продвинет победителя по графу, переведёт loser в losers bracket для double elimination и завершит турнир после финала.

Для боевого использования добавьте RBAC-права уровня турнира, аудит действий администраторов, rate limit на регистрацию/результаты, Redis для фоновых уведомлений и отдельный worker для массовой рассылки.

