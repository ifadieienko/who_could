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

Form instances and advanced field types,
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

## Generic job API

`GET /v2/jobs` exposes existing repair records through a generic read contract.
It accepts `after` (the numeric job number), `limit` (1–100), `status`,
`asset_id`, and `customer_id`; the response is `{items, next}`. Ordering by
immutable numeric ID prevents edits from moving records between cursor pages.
Filtering by customer additionally requires `customers.read`.

`GET /v2/jobs/{public_id}` returns the existing permission-filtered detail with
`organization_id`, `asset_id`, and `description` replacing the top-level
`device_id` and `problem` names. Public IDs, numbers, snapshots, statuses and
versions remain unchanged. `/events` and `/attachments` retain the compatibility
API's descending `before` cursors and field/finance redaction. All reads enforce
organization membership and all/own job scope. The `Job` model currently aliases
the existing mapper; migration 0013 adds metadata to that table.

`POST /v2/jobs` accepts existing `customer_id` and `asset_id`, optional `site_id`,
`job_type` (lowercase semantic key, default `repair`), `priority` (`low`, `normal`,
`high`, `urgent`), `description`, intake template/workflow IDs, stage forms,
values and the existing intake metadata. It requires `jobs.create` and
`customers.read`, and enforces the same subscription, quota, form validation and
snapshot rules as repair creation. Asset and site must belong to the selected
customer and organization. A job site is explicitly selected; omitting it means
no site, even if the asset currently has one.

`PATCH /v2/jobs/{public_id}` requires `version` and `jobs.edit`. It updates
`description`, intake metadata, values, deadline, priority and site. Explicit
`site_id: null` clears the site; omitted fields remain unchanged. Site changes
also require `customers.read`. Closed jobs and stale versions are rejected.
Corrections to accepted intake data require a reason; snapshots are preserved.
Both APIs share the update service, including locking and append-only audit.

Organization vertical is frozen at creation. Vertical, job type, customer and
asset cannot be changed by PATCH. Warranty jobs inherit original metadata,
including site and priority. Old API/import creation remains a repair job.
Historical sites are not inferred from mutable asset records during migration.

The repair UI and `/v2/orders` retain their contract. Generic lifecycle actions,
arbitrary form slots and vertical workflows remain later work; custom job types alone do not enable jewellery/calibration functionality.

## Job UI

The job queue links to `/jobs/new` for existing customer/asset records. The form
supports repair, inspection and maintenance job types, priority, explicit site,
intake/workflow selection and required stage-form revisions. Customer changes
clear asset/site selections. Asset search and asset/site pagination use bounded
API pages. Creating an asset job requires create-job, customer-read and asset-read
permissions in the UI; the backend independently validates each relationship.

Order details display immutable job type and editable priority/site in a separate
settings panel. Save uses the generic API with its loaded version; conflicts are
shown without overwriting server changes. Reloading the order refreshes settings.
Closed/read-only orders disable controls. New text has EN/PL/RU translations.
The existing intake form and lifecycle actions remain available unchanged.


### Form purposes and interface language

Form purposes now accept lowercase semantic keys (1–20 characters, beginning with a letter), such as `measurement`, `review` and `jewellery_condition`. The existing database columns and repair purposes remain compatible; `intake` retains its dedicated snapshot and cannot be assigned as a stage slot. Published templates can be attached to workflow stages and jobs by purpose, with existing validation, permissions, snapshots and version conflicts preserved. Custom-purpose photos must belong to a form assigned to that job. Form tabs use separate internal identifiers to avoid collisions with names such as `history`.

This is the first part of Form Engine 2: storage still uses the existing `stage_forms` JSON. Separate `JobFormInstance` records, table fields, richer validation and calculations remain to be implemented.

A persistent top-right language selector is available on every application route, including authentication, password reset and the public quote page. The personal browser choice takes precedence over the organization's default without changing other members' preferences. Switching does not remount the active page or discard drafts. Navigation, authentication and platform screens use the selected dictionary; legacy repair screens and server messages still contain untranslated text. Organization currency and time zone remain independent of the selected interface language.
