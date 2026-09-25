# WHO COULD — TECHNICAL DEVELOPMENT PLAN

## 1. Задача

Репозиторий:

`https://github.com/ifadieienko/who_could`

Нужно не просто добавить несколько функций, а довести проект до логически завершённого коммерческого состояния.

Текущий Who Could уже является работающей SaaS-платформой ремонтной мастерской с:

- multi-tenant мастерскими;
- сотрудниками и ролями;
- tenant isolation;
- configurable/versioned forms;
- configurable/versioned workflows;
- фотографиями и файлами;
- QR;
- сметами и согласованием клиентом;
- оплатами;
- аудитом действий;
- Stripe subscriptions;
- SMTP outbox;
- импортом/экспортом;
- backup/restore;
- MariaDB migrations;
- Playwright E2E;
- GitHub Actions.

Следующий этап — превратить существующую repair-specific архитектуру в:

> **configurable asset-service operations platform**

где ремонт техники является одним vertical template, а не фундаментальным ограничением модели.

Основные целевые verticals:

1. **Repair shop** — существующий, должен полностью сохраниться.
2. **Jewellery / Watch repair** — второй production-ready vertical.
3. **Calibration / Metrology** — основной стратегический vertical и коммерческий MVP.

Не строить пока универсальный аналог ServiceTitan/Jobber для всех возможных field-service бизнесов.

---

# 2. Исходное состояние

На момент подготовки этого плана основной `main`:

`9da392b6c54ae44c1331a326c4fe580f34d5839e`

Последний большой merged PR:

`#1 — Платформа ремонтных мастерских: изоляция, формы этапов, QR и подписки`

Текущая migration chain:

`0001 ... 0010_stage_forms_plans`

Существующие миграции **не переписывать**.

Текущий CI уже проверяет:

- MariaDB 11.4;
- server tests;
- populated legacy migration;
- tenant isolation;
- billing guards;
- frontend build;
- Playwright Chromium;
- deployment invariants.

Это необходимо сохранить.

Перед началом работы проверить фактический HEAD `main`. Если репозиторий изменился после этого документа, использовать актуальный код как source of truth.

---

# 3. Definition of Done для проекта

Проект можно считать доведённым до логического коммерческого состояния, когда одновременно выполнены следующие условия.

### Platform Core

Система больше не зависит концептуально от сущностей `Workshop → Device → Repair`.

В core должны существовать понятия:

`Organization → Customer → Asset → Job → Workflow → Forms → Documents → Events`

Repair-specific терминология должна задаваться vertical'ом/UI, а не архитектурой core.

### Repair vertical

Весь существующий ремонтный workflow продолжает работать без регрессий:

`приём → диагностика → согласование → ремонт → QC → готово → выдача → гарантия`

Сохраняются старые данные и миграция существующей базы.

### Jewellery / Watch vertical

Организацию можно создать как jewellery/watch workshop.

Работает полный сценарий:

`приём изделия → фиксация состояния/фото → custody → оценка → согласование → работа → QC → выдача`

### Calibration vertical

Работает коммерчески пригодный цикл:

`asset → calibration due → procedure → measurements → reference standards → review → certificate → next calibration`

### SaaS

Работают:

- signup;
- organization creation;
- employee invitation;
- roles;
- subscription;
- limits;
- password recovery;
- email;
- export;
- backup;
- restore;
- secure files;
- production deployment.

### Quality

Обязательны:

- migration tests;
- tenant-isolation tests;
- API tests;
- Playwright E2E для всех трёх verticals;
- fresh install test;
- upgrade test с существующей БД;
- backup/restore test;
- production build;
- green GitHub Actions.

Нельзя считать задачу завершённой только потому, что код компилируется.

---

# 4. Правила работы

## 4.1. Не делать giant rewrite

Не переписывать приложение с нуля.

Существующие:

- FastAPI;
- SQLAlchemy;
- MariaDB;
- React;
- Vite;
- Stripe integration;
- deployment scripts;
- auth;
- backup infrastructure

оставить.

Не переходить без необходимости на:

- PostgreSQL;
- Next.js;
- microservices;
- Redis;
- Kubernetes;
- Celery;
- другой ORM.

---

## 4.2. Не делать giant rename migration

Физические таблицы вроде:

`workshops`

`repair_orders`

`repair_devices`

могут временно сохранять старые имена.

Семантически core должен стать generic, но cosmetic rename существующих SQL tables не является приоритетом.

Сначала необходимо стабилизировать новую архитектуру.

Физическое переименование таблиц допускается позже отдельной migration cleanup, если оно действительно необходимо.

---

## 4.3. Существующие migrations immutable

Нельзя редактировать migrations `0001–0010`.

Все изменения только новыми migrations.

Каждая значительная migration должна тестироваться как минимум:

`fresh DB → head`

и

`existing populated 0010 DB → head`

---

## 4.4. Сохранять данные

Нельзя удалять существующие:

- users;
- workshops;
- memberships;
- customers;
- devices;
- orders;
- estimates;
- payments;
- files;
- audit events;
- workflows;
- forms.

Если структура меняется, данные мигрируются.

---

## 4.5. Работать небольшими PR

Предпочтительный процесс:

`main → feature branch → tests → PR → green CI → merge`

Не накапливать огромную ветку со всеми изменениями проекта.

Каждый PR должен оставлять `main` в рабочем состоянии.

---

# 5. Целевая архитектура

## Core

```text
Organization
 ├ Members
 ├ Roles
 ├ Customers
 │   └ Sites
 │
 ├ Assets
 │   └ Asset history
 │
 ├ Jobs
 │   ├ Workflow snapshot
 │   ├ Form instances
 │   ├ Attachments
 │   ├ Estimates
 │   ├ Approvals
 │   ├ Documents
 │   ├ Payments
 │   └ Events
 │
 ├ Form templates
 ├ Workflow templates
 ├ Document templates
 ├ Schedule rules
 └ Subscription / entitlements
```

---

# 6. PHASE 0 — стабилизация и реорганизация кода

Перед расширением функционала привести структуру проекта в состояние, пригодное для дальнейшей разработки.

Сейчас имеются очень крупные файлы, в частности:

- `backend/app/repairs.py`
- `frontend/src/WorkshopApp.jsx`
- `frontend/src/WorkshopSettings.jsx`

Не переписывать поведение, но постепенно разделить ответственность.

## Backend target

Примерное направление:

```text
app/
  core/
    auth/
    tenancy/
    billing/
    storage/
    mail/
    security/

  organizations/
  customers/
  assets/
  jobs/
  forms/
  workflows/
  approvals/
  documents/
  scheduling/

  verticals/
    repair/
    jewellery/
    calibration/
```

Не нужно механически создавать abstraction/repository для каждого SQL-запроса.

Главная цель — перестать держать весь business logic в одном `repairs.py`.

## Frontend target

```text
src/
  app/
  api/
  components/

  features/
    organizations/
    customers/
    assets/
    jobs/
    forms/
    workflows/
    members/
    billing/

  verticals/
    repair/
    jewellery/
    calibration/
```

Разделить `WorkshopApp.jsx` и `WorkshopSettings.jsx` на страницы/features.

Не менять UI framework. Использовать существующие React/shadcn/Base UI.

### Acceptance

Существующие server + Playwright tests проходят без изменения пользовательского поведения.

---

# 7. PHASE 1 — Organization вместо Workshop на уровне core

Не обязательно сразу переименовывать SQL table.

На application/API уровне ввести generic concept:

`Organization`

Дополнить организацию:

```text
name
vertical_key
locale
timezone
currency
country
settings
created_at
```

Первичные vertical keys:

```text
repair
jewellery
calibration
```

## Currency

Убрать hardcoded `PLN` из business logic.

У организации должна быть одна default currency.

На первом этапе поддержать:

- PLN
- EUR
- GBP
- CZK

Все monetary amounts продолжать хранить integer minor units.

## Timezone

Даты в БД хранить UTC.

Отображать относительно timezone организации.

## Locale

UI не должен содержать business-critical hardcoded русские/польские строки внутри компонентов.

Добавить normal localization layer.

Минимально полностью поддержать:

- English;
- Polish.

Подготовить структуру для:

- German;
- Czech;
- Slovak.

DE/CS/SK тексты не считать production-ready без human review.

---

# 8. PHASE 2 — Generic permissions

Перейти концептуально от:

`orders.*`

к:

`jobs.*`

Например:

```text
jobs.read
jobs.create
jobs.edit
jobs.assign
jobs.transition
jobs.issue
jobs.reopen

customers.read

assets.read
assets.write

finance.read
finance.write

forms.manage
workflows.manage
documents.manage

members.manage
organization.manage

data.import
data.export
billing.manage
```

Старые permissions мигрировать без потери ролей.

При необходимости временно поддерживать aliases:

`orders.read → jobs.read`

и т. д.

Default role names должны задаваться vertical'ом.

Например repair:

`Reception / Technician`

Calibration:

`Technician / Reviewer / Quality Manager`

Jewellery:

`Reception / Jeweller`

---

# 9. PHASE 3 — Asset model

`Device` должен стать частным случаем `Asset`.

Создать generic asset model.

Минимально:

```text
Asset
  id
  organization_id
  customer_id
  site_id optional
  asset_type
  name
  manufacturer
  model
  serial
  external_id
  status
  custom_values
  created_at
  updated_at
```

Существующие Devices мигрировать в Assets без потери связи с orders.

## Asset history

Карточка Asset должна показывать:

- все jobs;
- photos/files;
- certificates/documents;
- custody movements;
- events;
- next scheduled service/calibration.

## Asset QR

QR должен открывать авторизованную asset card.

Никаких персональных данных в самом QR.

---

# 10. PHASE 4 — Customer и Site

Расширить Customer.

Поддержать:

```text
person
company
```

Добавить:

```text
company_name
tax_id optional
contact_person
email
phone
address
```

Добавить сущность:

`Site`

```text
customer
name
address
notes
```

Site является optional.

Это понадобится позже field-service verticals, но не должно усложнять repair/jewellery.

---

# 11. PHASE 5 — RepairOrder → Generic Job

На application level основной объект должен стать `Job`.

Минимальная модель:

```text
Job
  organization
  customer
  asset
  site optional

  vertical_key
  job_type

  workflow snapshot
  current stage

  assigned employee
  priority
  due date

  status
  version

  created
  updated
```

Существующие RepairOrder мигрировать/адаптировать.

Repair UI при этом по-прежнему может называть Job:

`Repair / Naprawa`

Calibration UI:

`Calibration`

Jewellery:

`Repair`

Внутренний core должен использовать `Job`.

---

# 12. PHASE 6 — переделка Form Engine

Это один из самых важных этапов.

Сейчас существуют фиксированные:

- intake;
- diagnosis;
- repair;
- quality.

Для multi-vertical модели этого недостаточно.

## Убрать fixed FormPhase

Форма должна иметь произвольный semantic key/purpose.

Например:

```text
intake
diagnosis
repair
quality

jewellery_condition
stone_check

calibration_setup
measurement
review
```

## JobFormInstance

Создать отдельную сущность form instance.

```text
JobFormInstance
  job_id
  form_template_family
  form_revision
  slot_key
  schema_snapshot
  values
  version
  created_at
  updated_at
```

Старый `stage_forms` JSON постепенно мигрировать в form instances.

Нельзя потерять snapshots старых заказов.

---

# 13. Form Engine — новые field types

Сохранить существующие типы и добавить минимум:

```text
string
text
number
date
datetime
checkbox
select
multiselect
file
image
signature
table
```

## Table / repeating rows

Критично для calibration.

Пример:

| Nominal | Reading | Error | Tolerance | Uncertainty | Result |
|---|---|---|---|---|---|

Администратор должен уметь задавать columns и row structure.

## Validation

Добавить:

```text
min
max
precision
regex
unit
min_length
max_length
```

## Conditions

Расширить текущий простой `equals`.

Нужны:

```text
equals
not_equals
gt
gte
lt
lte
contains
is_empty
```

и логика:

```text
AND
OR
```

Ограничить глубину expression tree.

---

# 14. Form calculations

Добавить безопасные calculated fields.

Никакого:

`eval()`

Никакого выполнения пользовательского Python/JavaScript.

Использовать restricted expression parser / AST whitelist.

Поддержать арифметику:

```text
+
-
*
/
()
```

и ссылки на numeric fields.

Все formulas должны быть частью immutable form revision.

Изменение formula создаёт новую revision.

---

# 15. PHASE 7 — Workflow Engine 2.0

Текущие workflow snapshots сохранить как сильную часть продукта.

Убрать требование, что каждый workflow обязательно содержит stage category `ready`.

Generic workflow должен иметь:

```text
initial stage
normal stages
waiting stages
review stages
terminal stages
```

Stage:

```text
key
label
category
allowed transitions
required form slots
required fields
required checks
permission
SLA
approval requirements
```

Каждый job продолжает хранить workflow snapshot.

Изменение workflow никогда не меняет существующий job задним числом.

---

# 16. Transition Guards

Переход может требовать:

- заполненную form;
- обязательные fields;
- checks;
- согласованную estimate revision;
- approval;
- signature;
- generated document;
- reviewer permission.

Transition guards должны быть декларативными.

Не разбрасывать vertical-specific `if calibration...` по generic job service.

---

# 17. PHASE 8 — Generic Approval Engine

Текущая quote approval логика должна стать частным случаем generic approval.

Создать concept:

`ApprovalRequest`

Он может относиться к:

```text
estimate
document
job transition
calibration review
```

Хранить:

```text
subject type
subject id/revision
token_hash
expires_at
decision
decision_name
decision_at
metadata
```

Ссылки случайные.

В БД хранить hashes.

Повторное решение запрещено.

Старый estimate approval должен продолжить работать через эту модель либо compatibility layer.

---

# 18. PHASE 9 — Documents

Создать generic document subsystem.

Типы:

```text
intake receipt
release receipt
estimate
service report
calibration certificate
inspection report
```

Нужны:

`DocumentTemplate`

и

`GeneratedDocument`.

Generated document должен быть immutable.

Хранить:

```text
document type
job
revision
template revision
generated timestamp
generated by
file
checksum
```

После выпуска документа его содержимое нельзя silently менять.

Исправление документа создаёт новую revision.

## PDF

Добавить стабильную server-side PDF generation.

Выбрать один renderer и закрепить dependency versions.

PDF generation должна иметь automated smoke tests.

---

# 19. PHASE 10 — Scheduling / recurring service

Добавить generic `ScheduleRule`.

Необходим для:

- calibration;
- preventive maintenance;
- future inspections.

Минимально:

```text
organization
asset
job type
workflow
interval
next_due_at
reminder offsets
active
```

Scheduler должен быть idempotent.

Предпочтительно расширить существующую DB/outbox инфраструктуру.

Не добавлять Redis/Celery только ради scheduler.

Cron/worker с DB locking допустим.

Не создавать duplicate scheduled jobs при повторном запуске.

---

# 20. PHASE 11 — Notifications

Обобщить существующий SMTP outbox.

Типы событий:

```text
estimate approval
job ready
password reset
employee invitation
calibration due
certificate issued
job status
```

Сохранить:

- retry;
- dedupe key;
- attempts;
- error;
- next_attempt.

SMS/WhatsApp пока не реализовывать.

---

# 21. PHASE 12 — Employee invitation flow

Текущая модель, где owner создаёт сотруднику пароль, должна быть заменена нормальным invite flow.

Owner вводит email.

Система создаёт invitation token.

Пользователь:

- принимает приглашение;
- создаёт пароль, если account новый;
- либо подключает существующий account.

Invitation:

- token hash;
- expiration;
- one-time usage.

После acceptance создаётся Membership.

Не отправлять пароли email'ом.

---

# 22. PHASE 13 — Vertical Template System

Vertical не должен быть отдельным приложением.

Создать registry/configuration system.

Пример:

```text
repair
jewellery
calibration
```

Vertical определяет:

- terminology;
- default roles;
- default forms;
- default workflows;
- asset types;
- dashboard defaults;
- enabled features.

При создании Organization выбранный vertical seeds default configuration.

После этого owner может кастомизировать forms/workflow.

---

# 23. REPAIR VERTICAL

Перевести текущий repair functionality на generic core.

Обязательное правило:

**существующий repair functional coverage нельзя ухудшить.**

Должны сохраниться:

- intake;
- photos;
- diagnosis;
- repair;
- quality control;
- estimate revisions;
- customer approval;
- payments;
- ready;
- release;
- reopening;
- warranty job;
- QR;
- labels;
- files;
- events;
- imports;
- exports.

Старый существующий Playwright repair scenario должен продолжить работать.

---

# 24. JEWELLERY / WATCH VERTICAL

Это первый новый production vertical.

Добавить asset types:

```text
ring
necklace
bracelet
earrings
watch
other
```

Дополнительные данные:

```text
material
weight
stones
stone count
engraving
estimated value
condition
customer notes
```

## Intake

Обязательные фотографии изделия.

Condition form.

Accessories/packaging.

## Custody

Создать generic `CustodyEvent`.

```text
asset
job
actor
from_location
to_location
external_party optional
note
timestamp
```

Пример:

```text
Reception
→ Safe 3
→ Jeweller Anna
→ External goldsmith
→ Safe 3
→ Customer
```

Custody history должна быть append-only.

## Workflow

Seed:

```text
Received
Inspection
Estimate
Waiting for approval
Repair
Finishing
Quality control
Ready
Collected
```

Использовать существующий estimate/approval engine.

## Acceptance E2E

Playwright должен пройти:

```text
create jewellery organization
→ customer
→ asset
→ condition/photos
→ custody
→ estimate
→ external customer approval
→ work
→ QC
→ ready
→ release
```

---

# 25. CALIBRATION VERTICAL

Это основной стратегический vertical.

Не заявлять автоматически ISO/IEC 17025 compliance.

Продукт должен предоставлять технические инструменты для лабораторий, но ответственность за accredited process остаётся у лаборатории.

---

# 26. Calibration Assets

Asset должен дополнительно поддерживать:

```text
manufacturer
model
serial
asset category
measurement range
resolution
accuracy/specification
unit
calibration interval
last calibration
next calibration
```

Reference standard тоже является Asset.

Добавить classification:

```text
customer_instrument
reference_standard
```

---

# 27. Calibration Procedures

Создать:

`CalibrationProcedure`

с immutable versions.

Procedure revision должна содержать:

- title;
- code;
- instructions;
- measurement table schema;
- required fields;
- acceptance/decision configuration;
- document template;
- required role/reviewer.

Существующий job хранит procedure revision snapshot/reference.

Изменение процедуры не изменяет старую calibration.

---

# 28. Measurement Sessions

Создать structured measurement model.

Минимальная строка:

```text
nominal
reading
error
lower_limit
upper_limit
tolerance
uncertainty
unit
result
notes
```

Поддержать:

```text
as_found
as_left
```

Не обязательно каждое поле должно использоваться каждой процедурой.

Структура должна задаваться procedure/form configuration.

---

# 29. Decision rules

Не hardcode одну формулу pass/fail.

Procedure revision должна явно хранить используемое decision rule.

Если автоматическое решение не настроено:

`result = manual`

Система не должна создавать ложную уверенность в conformity.

Автоматические calculations должны быть полностью reproducible и versioned.

---

# 30. Reference standards

Calibration job должен сохранять, какие standards использовались.

Для каждого:

```text
asset
certificate reference
calibration date
valid until
```

При использовании expired standard UI должен показать явное предупреждение.

Исторический job всё равно должен сохранять реально использованный standard.

---

# 31. Uncertainty

Добавить базовую uncertainty model отдельным модулем.

Минимальная структура component:

```text
source
value
distribution
divisor
sensitivity coefficient
standard uncertainty
```

Рассчитывать:

```text
combined uncertainty
coverage factor
expanded uncertainty
```

Все calculation rules должны иметь unit tests.

Не использовать floating-point хаотично для критичных decimal calculations.

Использовать `Decimal` там, где это необходимо.

---

# 32. Calibration Review

После measurement technician завершает работу.

Reviewer должен подтвердить results.

Нельзя выпустить certificate до review.

Roles:

```text
technician
reviewer
quality manager
```

Один пользователь может иметь несколько permissions.

Review должен оставлять immutable audit event.

---

# 33. Calibration Certificate

Сгенерировать PDF certificate.

Минимально:

- organization;
- customer;
- asset;
- serial;
- procedure;
- calibration date;
- results;
- uncertainty;
- reference standards;
- technician;
- reviewer;
- certificate number;
- issue date.

Certificate numbering должно быть atomic и tenant-scoped.

Например:

`CAL-2027-000123`

Не допускать duplicate numbers при concurrency.

После issue certificate immutable.

Correction → new revision.

---

# 34. Recalibration

После завершения calibration:

```text
last_calibration = current date
next_calibration = calculated due date
```

Scheduler создаёт reminders.

Dashboard:

```text
overdue
due in 7 days
due in 30 days
```

---

# 35. Customer Portal

Обобщить public customer access.

Не создавать публично угадываемые ссылки.

Использовать secure random tokens.

Portal может позволять:

Repair/Jewellery:

- посмотреть статус;
- принять estimate.

Calibration:

- скачать certificate;
- посмотреть calibration summary.

Не раскрывать внутренние notes/events/employee data.

---

# 36. Search

Добавить нормальный tenant-scoped global search.

Искать по:

- job number;
- customer;
- email;
- phone;
- asset name;
- manufacturer/model;
- serial;
- external ID;
- certificate number.

Результаты всегда должны проходить organization permission filter.

---

# 37. Pagination

Все потенциально большие списки должны быть paginated.

Не загружать тысячи:

- jobs;
- assets;
- customers;
- events;
- certificates

одним запросом.

Использовать стабильные cursors либо нормальную server-side pagination.

---

# 38. Storage abstraction

Сейчас файлы используют local `UPLOAD_DIR`.

Создать storage interface.

Поддержать:

```text
LocalStorage
S3CompatibleStorage
```

S3-compatible должен работать как минимум с:

- MinIO;
- AWS S3-compatible API.

Bucket private.

Доступ к файлам только после application permission check.

Не использовать permanent public URLs.

CI для storage желательно проверять через MinIO service container.

---

# 39. Audit

`JobEvent`/audit log должен оставаться append-only.

Нельзя предоставлять UI/API редактирования старого audit event.

Значимые операции должны создавать events:

- assignment;
- transition;
- data change;
- estimate;
- approval;
- custody;
- calibration measurement completion;
- review;
- certificate;
- release;
- reopen.

Для sensitive final records использовать revision/new event вместо overwrite history.

---

# 40. Billing

Обобщить:

`open_orders → open_jobs`

Plan entitlement engine не должен зависеть от repair terminology.

Поддержать limits:

```text
members
open_jobs
storage_bytes
assets optional
```

Stripe Checkout/Portal/webhook сохранить.

Цена не должна определять permissions на client side.

Entitlements всегда проверяются server side.

---

# 41. Security hardening

Сохранить существующие protections и добавить:

- rate limiting login/reset/public token endpoints;
- email invite token expiry;
- consistent authorization tests;
- upload validation;
- safe filename handling;
- CSP;
- frame protection;
- secure cookies production-only HTTPS;
- request IDs;
- structured security logs.

Не создавать global administrator, который автоматически видит данные всех tenants.

Для support доступ к организации должен даваться явно.

---

# 42. Frontend UX

Не пытаться создать абсолютно разный frontend для каждого vertical.

Использовать общий shell:

```text
Dashboard
Jobs
Customers
Assets
Schedule
Documents
Settings
```

Vertical изменяет:

- labels;
- fields;
- default views;
- workflow;
- optional modules.

## Responsive

Карточка job и asset должна нормально работать на телефоне.

Технический сотрудник должен иметь возможность:

- открыть QR;
- заполнить form;
- добавить photo;
- выполнить transition.

Offline пока не нужен.

---

# 43. Dashboard

Generic dashboard:

```text
Open jobs
Waiting jobs
Overdue jobs
Due soon
Ready / completed
```

Calibration дополнительно:

```text
Assets due
Overdue calibrations
Certificates awaiting review
```

Jewellery:

```text
Awaiting approval
In repair
Ready
```

---

# 44. Не делать до завершения v1

Не уходить в scope creep.

Не являются release blockers:

- native Android/iOS application;
- route optimization;
- GPS tracking;
- full field dispatch;
- full ERP;
- accounting;
- fiscal cash register;
- online card payment за выполненные услуги;
- SMS;
- WhatsApp;
- OCR;
- AI;
- marketplace;
- SAP integration;
- advanced procurement;
- qualified electronic signatures;
- автоматическое обещание ISO 17025 compliance.

Полноценный inventory/parts management оставить следующим большим этапом после validation Calibration/Jewellery.

Существующий warehouse functionality сохранить совместимым, но не делать его foundation нового core.

---

# 45. Testing strategy

Разделить tests по domains.

Пример:

```text
backend/tests/
  test_auth.py
  test_tenancy.py
  test_organizations.py
  test_assets.py
  test_jobs.py
  test_forms.py
  test_workflows.py
  test_approvals.py
  test_documents.py
  test_scheduling.py
  test_billing.py
  test_storage.py

  verticals/
    test_repair.py
    test_jewellery.py
    test_calibration.py

  test_migration.py
```

Не обязательно переименовывать всё сразу, но двигаться к этой структуре.

---

# 46. Обязательные isolation tests

Создать две организации.

Проверять, что User A не может через ID substitution получить:

- customer;
- asset;
- job;
- attachment;
- estimate;
- document;
- event;
- certificate;
- custody event

Organization B.

Проверять GET и mutation endpoints.

---

# 47. Обязательные concurrency tests

Проверять как минимум:

- optimistic Job version;
- estimate decision;
- certificate numbering;
- asset scheduling;
- plan limits;
- simultaneous transition;
- invitation use;
- public approval token.

---

# 48. Playwright

Минимум четыре E2E suites:

```text
repair.spec
jewellery.spec
calibration.spec
auth-tenancy.spec
```

## Repair

Сохранить существующий full lifecycle.

## Jewellery

Полный jewellery scenario.

## Calibration

```text
create organization
→ create customer
→ create asset
→ procedure
→ calibration job
→ measurement
→ reference standard
→ technician completion
→ reviewer approval
→ certificate
→ next due date
```

---

# 49. Migration tests

Сохранить populated legacy fixture.

Добавить populated `0010` fixture.

Проверять:

```text
0010
→ generic platform head
```

После upgrade должны совпасть:

- users;
- organizations/workshops;
- employees;
- customers;
- devices/assets;
- repairs/jobs;
- estimates;
- files;
- payments;
- events.

---

# 50. Observability

Добавить structured logging.

Минимум:

```text
timestamp
level
request_id
organization_id where applicable
user_id where applicable
route
status
duration
```

Не логировать:

- passwords;
- session tokens;
- approval tokens;
- Stripe secrets;
- private file contents.

Добавить:

`/health`

и readiness check, если требуется отдельный endpoint.

Optional Sentry integration допустим через env, но SaaS не должен от него зависеть.

---

# 51. Backup / Restore

Существующий backup system сохранить.

После появления S3 storage обновить документацию.

Backup/restore test должен подтверждать восстановление:

- DB;
- local files либо storage metadata;
- generated documents.

Production release не считать готовым без проверенного restore procedure.

---

# 52. Documentation

Обновить README.

Создать:

```text
docs/ARCHITECTURE.md
docs/VERTICALS.md
docs/MIGRATION_TO_PLATFORM.md
docs/CALIBRATION.md
docs/JEWELLERY.md
docs/PRODUCTION_RELEASE.md
```

README не должен продолжать описывать продукт только как «ремонтную мастерскую».

Предлагаемое позиционирование:

> Who Could — configurable service operations platform for businesses working with customer assets.

---

# 53. Предлагаемый порядок PR

### PR 1 — Structural cleanup

Backend/frontend modularization без функциональных изменений.

### PR 2 — Organization platform

Organization metadata, currency, timezone, locale, generic permissions.

### PR 3 — Asset + Customer + Site

Generic assets и migration Device → Asset compatibility.

### PR 4 — Generic Job API

Job abstraction + repair compatibility.

### PR 5 — Form Engine 2

Generic form instances, tables, repeating rows, validation, conditions.

### PR 6 — Workflow 2 + approvals

Generic stages/guards + ApprovalRequest.

### PR 7 — Documents + scheduling

Generated documents, PDF, recurring rules, scheduler.

### PR 8 — Repair migration

Весь repair vertical работает через new core.

### PR 9 — Jewellery vertical

Templates, custody, jewellery E2E.

### PR 10 — Calibration foundation

Assets, procedures, measurements, standards.

### PR 11 — Calibration completion

Review, uncertainty, certificates, recalibration.

### PR 12 — SaaS hardening

Invites, S3, rate limits, observability, generalized billing.

### PR 13 — Release

Migration fixture, E2E, deployment, docs, backup/restore, cleanup.

Количество PR можно изменить, если это делает изменения безопаснее.

Главное — не превращать всё в один огромный PR.

---

# 54. Приоритеты

## P0 — обязательно до v1

- Generic Organization.
- Generic Asset.
- Generic Job.
- Generic permissions.
- Generic FormInstance.
- Arbitrary form purposes.
- Table/repeating form fields.
- Workflow terminal stages.
- Repair compatibility.
- Jewellery vertical.
- Calibration procedures.
- Calibration measurements.
- Reference standards.
- Calibration review.
- Certificates.
- Recurring calibration.
- Tenant isolation.
- Migrations.
- E2E.
- Production security.

## P1 — коммерческая готовность

- Customer portal.
- Generic documents.
- PDF.
- employee invites.
- i18n.
- S3-compatible storage.
- global tenant search.
- improved dashboards.
- localization/currency/timezone.
- scheduler/reminders.
- observability.

## P2 — после validation рынка

- true inventory;
- parts reservations;
- purchasing;
- supplier integration;
- field dispatch;
- technician offline mode;
- mobile PWA offline cache;
- accounting integrations;
- industrial equipment vertical;
- inspection vertical.

---

# 55. Особо важные архитектурные решения

Не допускать следующих ошибок.

### Не создавать отдельную кодовую базу под Jewellery.

Это vertical configuration + небольшие domain additions.

### Не создавать отдельную кодовую базу под Calibration.

Calibration-specific domain tables допустимы, но auth/tenancy/jobs/forms/files/documents должны быть общими.

### Не хранить новый calibration data как один огромный opaque JSON.

Procedure schema может быть JSON/versioned, но ключевые business entities:

- calibration session;
- measurements;
- reference standards;
- certificate;

должны иметь понятную структуру и тестируемую модель.

### Не выполнять пользовательские formulas через eval.

### Не делать mutable certificates.

### Не менять старые jobs при редактировании workflow/form/procedure.

### Не ломать repair vertical ради generic naming.

---

# 56. UX principle

Главное конкурентное преимущество продукта:

> **The software adapts to the service process instead of forcing the service process to adapt to the software.**

Но это не означает, что пользователь должен начинать с пустого экрана.

Каждый vertical обязан иметь качественные default templates.

Пользователь получает готовую систему и только затем может её кастомизировать.

---

# 57. Release criteria

Создать release candidate только если:

1. CI полностью зелёный.
2. Fresh install работает.
3. Migration существующей populated DB работает.
4. Repair E2E зелёный.
5. Jewellery E2E зелёный.
6. Calibration E2E зелёный.
7. Tenant isolation tests зелёные.
8. Concurrency tests зелёные.
9. PDF generation работает.
10. Scheduler не создаёт duplicate jobs.
11. Stripe test mode проверен.
12. SMTP test environment проверен.
13. Backup создан.
14. Restore проверен.
15. Production build работает через HTTPS.
16. Нет известных P0 defects.
17. Документация соответствует коду.

---

# 58. Финальная ручная проверка

Перед окончательным завершением создать три demo organizations:

```text
Demo Repair
Demo Jewellery
Demo Calibration
```

Для каждой пройти полный пользовательский цикл.

Проверить desktop и mobile viewport.

Проверить:

- permissions;
- employee deactivation;
- files;
- QR;
- forms;
- workflow;
- documents;
- public customer link;
- export.

---

# 59. Что делать с legacy

Не удалять legacy tables/code просто ради чистоты.

Удалять только если:

- новый путь полностью заменяет старый;
- migration существует;
- tests подтверждают перенос;
- production functionality не зависит от legacy path.

`tests_legacy` можно оставить архивом до стабилизации v1.

После v1 можно создать отдельный cleanup PR.

---

# 60. Инструкция Work по автономности

Не останавливаться после составления ещё одного плана.

Не ограничиваться анализом.

После инспекции репозитория непосредственно:

1. создать рабочую ветку;
2. реализовывать этап;
3. писать/обновлять tests;
4. запускать tests;
5. исправлять failures;
6. создавать PR;
7. проверять CI;
8. merge только green state;
9. переходить к следующему этапу.

Не спрашивать пользователя подтверждение для обычных внутренних архитектурных решений, рефакторинга, тестов и PR.

Если есть несколько разумных реализаций — выбрать более простую, безопасную и совместимую.

Запрос пользователя нужен только при:

- необходимости реальных credentials;
- платной внешней операции;
- irreversible production operation;
- решении, которое существенно меняет product scope.

---

# 61. Правило принятия решений

При конфликте требований использовать такой порядок:

```text
1. Data integrity
2. Tenant isolation / security
3. Existing repair compatibility
4. Migration safety
5. Testability
6. Generic platform architecture
7. UX
8. Implementation simplicity
9. Cosmetic code cleanliness
```

---

# 62. Финальный deliverable от Work

После завершения Work должен предоставить:

### Реализовано

Перечень major capabilities.

### PR / commits

Ссылки на merged PR.

### Database

Список новых migrations.

### Tests

Количество/типы пройденных tests.

### E2E

Результаты Repair / Jewellery / Calibration.

### Deployment

Точные production deployment steps.

### Migration

Инструкцию upgrade существующей установки.

### Known limitations

Только реальные оставшиеся ограничения.

### Next phase

Отдельно перечислить P2-функции, которые сознательно не вошли в v1.

Не считать P2 blockers незавершённостью v1.

---

# Конечная цель

После выполнения этого плана Who Could должен перестать быть экспериментальным приложением «для ремонтной мастерской» и стать production-ready SaaS-платформой:

```text
WHO COULD CORE
│
├── Repair
│
├── Jewellery / Watch
│
└── Calibration / Metrology
```

с общими:

```text
Organizations
Customers
Assets
Jobs
Forms
Workflows
Approvals
Documents
Files
Audit
Scheduling
Billing
```

и возможностью позже добавлять новые verticals без переписывания core.

На этом этапе **v1 считается логически завершённым**.

Следующая стратегическая фаза после проверки реальных клиентов — Industrial / Commercial Equipment Service, inventory и field-service capabilities.