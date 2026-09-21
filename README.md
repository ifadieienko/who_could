# Who could — локальный MVP фриланс-биржи

Приложение на **FastAPI + SQLAlchemy + React/Vite**, где один аккаунт может публиковать задачи и откликаться на чужие.

## Требования и установка

Нужны Python **3.10+** (с модулем `venv`) и совместимый с Vite 8 Node.js **20.19+ или 22.12+** (рекомендуется LTS 22) с npm.

```bash
python3 install.py                 # Linux/macOS
python install.py                  # Windows
```

Установщик проверяет реальные версии, создаёт `backend/.venv`, выполняет `npm ci`, инициализирует SQLite и создаёт уникальный `backend/.env`. Он не считает устаревший бинарник подходящим и сообщает, что именно требуется обновить.

### Секрет подписи

`WHO_COULD_SECRET` обязателен при обычном запуске и должен иметь не менее 32 символов. `install.py` безопасно генерирует его в игнорируемом Git файле `backend/.env`. Вручную:

```bash
cp backend/.env.example backend/.env
python -c "import secrets; print(secrets.token_urlsafe(48))"  # вставьте результат в .env
```

Для одноразового локального запуска без `.env` допустим `WHO_COULD_ENV=development`: backend создаст случайный process-only секрет, и сессии пропадут после рестарта. Этот режим нельзя использовать при deployment.

## Запуск

```bash
./scripts/start-database.sh        # применить Alembic migrations
./scripts/start-backend.sh         # http://127.0.0.1:8000, Swagger: /docs
./scripts/start-frontend.sh        # http://127.0.0.1:5173
# либо вместе: ./run-project.sh
```

На Windows используйте одноимённые `.cmd` и `run-project.cmd`. Разрешённые CORS origins: `http://127.0.0.1:5173` и `http://localhost:5173`.

## Проверки и CI

```bash
cd backend && alembic upgrade head && alembic check && python -m unittest discover -s tests
cd frontend && npm ci && npm run build
```

GitHub Actions на каждый `push` и `pull_request` независимо запускает backend-тесты и production build frontend (`.github/workflows/ci.yml`). Тесты используют временную SQLite-БД и проверяют auth, авторизацию, валидацию, приватность dashboard и конечные переходы статусов.

## Правила статусов

- задачи: `open → in_progress`, `open → closed`, `in_progress → closed`; неявного reopen нет;
- отклики: `sent → accepted` или `sent → declined`, оба результата конечны;
- принятие атомарно переводит задачу в работу и отклоняет остальные ожидающие отклики.

## Границы MVP

Bearer-токен в `localStorage` оставлены **только для локального MVP**. Клиент централизованно удаляет локальную сессию при `401`, но `localStorage` остаётся доступен JavaScript и не является production-хранилищем. Перед публичным deployment нужны HttpOnly Secure cookie/session architecture, CSRF-защита, production БД и миграции, rate limiting, восстановление аккаунта, аудит и модерация. Самодельная refresh-token система намеренно не добавлялась.


## Базы данных и миграции

Поддерживаются SQLite (локальный default), PostgreSQL и MariaDB. Схема управляется Alembic: `cd backend && alembic upgrade head`. Полный справочник переменных, TLS, pool и secret files: [docs/DATABASE_CONFIGURATION.md](docs/DATABASE_CONFIGURATION.md).

## Server deployment

Локальная разработка выше по-прежнему использует `install.py`. Для отдельного
Ubuntu/Linux-сервера доступен Docker installer/manager:

```bash
sudo ./server.sh install
```

Он интерактивно выбирает SQLite, локальный/внешний PostgreSQL или MariaDB,
создаёт file-backed secrets, применяет Alembic до запуска API и настраивает
Nginx/HTTP/HTTPS. Архитектура, все команды, ограничения безопасности и операции
описаны в [deploy/SERVER.md](deploy/SERVER.md), настройки — в
[deploy/CONFIGURATION.md](deploy/CONFIGURATION.md), резервное копирование — в
[deploy/BACKUP_RESTORE.md](deploy/BACKUP_RESTORE.md).

Safe release operations are documented in
[deploy/UPDATE_ROLLBACK.md](deploy/UPDATE_ROLLBACK.md):

```bash
sudo ./server.sh update --check
sudo ./server.sh update [--ref REF]
sudo ./server.sh releases
sudo ./server.sh rollback [RELEASE]
```

Опциональный host-level слой CrowdSec (SSH/Linux и Docker Nginx acquisition,
firewall bouncer, безопасная диагностика) устанавливается только явно:

```bash
sudo ./server.sh security-install
sudo ./server.sh security-status
```

Архитектура, оговорки Docker/UFW/nftables, удаление и disposable-VM acceptance
описаны в [deploy/SECURITY.md](deploy/SECURITY.md).
