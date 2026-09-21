# Code review: состояние Who could MVP

## Исправлено

- Секрет больше не имеет известного fallback: normal-запуск требует `WHO_COULD_SECRET`, `.env` загружается явно, installer генерирует локальный секрет.
- Любой повреждённый bearer token стабильно даёт `401`, включая неверные base64/JSON/payload.
- Переходы задач и откликов заданы явно. Принятие возможно только владельцем для `sent`-отклика открытой задачи и выполняется транзакционно; остальные ожидающие отклики становятся `declined`.
- Pydantic использует Enum, тип `date`, нормализацию ISO currency и model-level проверку диапазона бюджета.
- Startup переведён на FastAPI lifespan. CORS ограничен ожидаемыми origins.
- API-тесты изолированы и покрывают негативные auth, ownership, conflict, validation и privacy сценарии на SQLite, PostgreSQL и MariaDB.
- Frontend отменяет старые поисковые запросы, debounce применяется только к тексту, поздний response игнорируется. Токен и сброс сессии на `401` централизованы.
- Добавлен Docker/Compose server deployment: непривилегированные backend/Nginx, локальный SQLite/PostgreSQL/MariaDB или внешняя БД, file-backed secrets, Alembic, HTTP/custom TLS/ACME, health checks, backup/restore и transactional update/rollback.
- CI проверяет production images, Compose/security invariants, три СУБД, backup/restore, update/rollback и настоящий `server.sh install` из пустого state. Fresh-install smoke также проверяет безопасное продолжение после прерванной установки и сохранность данных после stop/start.
- Для границы, которую hosted CI не может доказать, есть явный disposable-VM acceptance: реальный fresh host, reboot, restart persistence и опциональная реальная ACME-проверка.

## Что намеренно остаётся ограничением приложения

- Bearer token хранится в `localStorage`; для полноценного публичного production необходимо перейти на HttpOnly Secure session/cookie архитектуру с CSRF-защитой.
- Нет refresh/revocation, email verification, восстановления пароля, полноценного application-level abuse/WAF слоя, аудита, модерации и платежей.
- SQLite остаётся вариантом для небольших/одиночных deployment; для публичной нагрузки предпочтительнее PostgreSQL/MariaDB.
- Docker deployment является production foundation, но не заменяет внешний мониторинг, off-host backup policy, DNS/CA operations и инфраструктурный disaster-recovery процесс.
