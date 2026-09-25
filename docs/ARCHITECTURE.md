# Platform architecture (incremental implementation)

The application remains FastAPI + SQLAlchemy + MariaDB and React + Vite. The
compatibility `/v2` API and database table names remain available.

## Implemented boundaries

- `organizations`: tenant settings, membership, roles and initialization.
- `core/tenancy`: scoped record lookup; `core/permissions`: permission aliases.
- `jobs`: repair lifecycle, snapshots, finance and serialization.
- `forms`, `workflows`, `customers`: their existing repair capabilities.
- `core/mail`: outbox inspection. Delivery remains in the existing worker.
- React screens live under `features`; the application shell owns navigation.

An organization uses the existing `workshops` table. Authenticated requests may
supply `X-Organization-Id` or legacy `X-Workshop-Id`; contradictory headers fail.
Membership is checked before accessing tenant records. Owners receive platform
administration permissions. Deactivated memberships retain business history.

`orders.*` and `jobs.*` are equivalent. `contacts.read` aliases `customers.read`.
Legacy `templates.manage` grants both form and workflow administration. A new
role with only `forms.manage` cannot administer workflows.

Money is integer minor units. Each job freezes its organization's currency on
creation. Estimates inherit the job currency; changing the organization default
does not reinterpret existing jobs, payments or quotes. Warranty jobs inherit
the original job currency. Supported currencies: PLN, EUR, GBP, CZK.

Dates remain UTC in storage. Browser display and deadline entry use the selected
organization's IANA timezone. Nonexistent or ambiguous DST deadline input is
rejected rather than silently shifted.

## Still scheduled in the supplied development plan

Generic job APIs, form instances and advanced field types,
generic workflow guards, PDF documents, scheduling, jewellery and calibration,
full English/Polish localization, invitations and storage hardening are not
claimed complete by this foundation. Organization settings currently have
English/Polish/Russian labels; existing repair screens retain their legacy labels.
See `PLATFORM_DEVELOPMENT_PLAN.md` for the full accepted scope.

## Asset/customer foundation

`assets` exposes paginated `/v2/assets`, `/v2/customer-records` and `/v2/sites`.
`Asset` maps to `repair_devices`, so historical order links need no replacement.
QR links open authenticated asset cards. Job history and image listing obey job
scope and restricted form-field permissions; downloads retain existing checks.
Own-work roles cannot mutate shared customer/site/asset records. Reassignment to
a different customer is rejected pending a dedicated ownership-transfer flow.
Assets can be retired without destroying history. Documents, custody and next
service entries will be attached by their later domain modules.

New customer/asset screens use `app/i18n.js` and shared EN/PL/RU dictionaries.
DE/CS/SK are reserved but not presented as translated languages.

## Generic job compatibility API

`Job` maps to `repair_orders`. `/v2/jobs` creates work for an existing active
asset, with description, type, priority, optional site, due date and versioned
form/workflow selections. Its lifecycle URLs use the very same handlers as
`/v2/orders`: no alternate permission, quota, payment or version-check path.
Responses expose generic identifiers and retain repair names during migration.
Existing repairs default to vertical/type `repair` and priority `normal`.

The asset card can start a generic job. Job creation/list screens use shared
localization. Detailed lifecycle screens remain shared with repairs while the
subsequent form/workflow/vertical work replaces their repair-specific labels.
