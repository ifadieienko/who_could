const numeric = (value) => typeof value === "number" && Number.isFinite(value);
export function conditionMatches(condition, values) {
  if (condition == null || Object.keys(condition).length === 0) return true;
  if (condition.all)
    return condition.all.every((child) => conditionMatches(child, values));
  if (condition.any)
    return condition.any.some((child) => conditionMatches(child, values));
  const value = values[condition.field] ?? null;
  const expected =
    (condition.operator ? condition.value : condition.equals) ?? null;
  const operator = condition.operator || "equals";
  if (operator === "equals") return value === expected;
  if (operator === "not_equals") return value !== expected;
  if (operator === "is_empty")
    return (
      value == null ||
      value === "" ||
      (Array.isArray(value) && value.length === 0)
    );
  if (operator === "contains")
    return typeof value === "string" && value.includes(expected);
  if (!numeric(value) || !numeric(expected)) return false;
  if (operator === "gt") return value > expected;
  if (operator === "gte") return value >= expected;
  if (operator === "lt") return value < expected;
  if (operator === "lte") return value <= expected;
  return false;
}
