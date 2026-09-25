export const money = (n) => `${((n || 0) / 100).toFixed(2)} PLN`;
export const dateValue = (v) =>
  new Date(/(Z|[+-]\d\d:\d\d)$/.test(v) ? v : v + "Z");
export const time = (v) => (v ? dateValue(v).toLocaleString() : "—");
export const localInput = (v) => {
  if (!v) return "";
  const d = dateValue(v);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
};
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
