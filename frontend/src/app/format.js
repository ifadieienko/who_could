let organization = { locale: "ru", timezone: "Europe/Warsaw", currency: "PLN" };
export function configureOrganization(value) {
  organization = { ...organization, ...value };
}
export const money = (n, currency = organization.currency) =>
  `${((n || 0) / 100).toFixed(2)} ${currency}`;
export const dateValue = (v) =>
  new Date(/(Z|[+-]\d\d:\d\d)$/.test(v) ? v : v + "Z");
export const time = (v) =>
  v
    ? dateValue(v).toLocaleString(organization.locale, {
        timeZone: organization.timezone,
      })
    : "—";
const wallTime = (d, zone) => {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: zone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(d)
      .map((p) => [p.type, p.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
};
export const localInput = (v) =>
  v ? wallTime(dateValue(v), organization.timezone) : "";
// Resolve against the organization's IANA zone, including DST; never silently
// reinterpret a nonexistent local time as a different hour.
export function localToISO(value) {
  if (!value) return null;
  const target = Date.parse(value + "Z");
  if (!Number.isFinite(target)) throw new Error("Invalid date");
  const offsets = new Set(
    [-36, -12, 0, 12, 36].map((hours) => {
      const instant = target + hours * 3600000;
      return (
        Date.parse(wallTime(new Date(instant), organization.timezone) + "Z") -
        instant
      );
    }),
  );
  const matches = [...offsets]
    .map((offset) => new Date(target - offset))
    .filter((d) => wallTime(d, organization.timezone) === value)
    .sort((a, b) => a - b);
  if (!matches.length)
    throw new Error(
      "This local time does not exist because clocks change. Choose another time.",
    );
  if (matches.length > 1)
    throw new Error(
      "This local time occurs twice because clocks change. Choose an unambiguous time.",
    );
  return matches[0].toISOString();
}
export const statusNames = {
  draft: "Черновик",
  active: "В работе",
  waiting: "Ожидание",
  ready: "К выдаче",
  issued: "Выдан",
  cancelled: "Отменён",
  pending: "Ожидает решения",
  accepted: "Принята",
  declined: "Отклонена",
  superseded: "Заменена",
};
