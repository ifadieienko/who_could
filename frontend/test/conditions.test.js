import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { conditionMatches } from "../src/features/forms/conditions.js";
const cases = JSON.parse(
  readFileSync(
    new URL("../../test-fixtures/form-conditions.json", import.meta.url),
  ),
);
test("condition semantics match the shared server/browser fixtures", () => {
  for (const c of cases)
    assert.equal(
      conditionMatches(c.condition, c.values),
      c.expected,
      JSON.stringify(c),
    );
});
