"""Bounded declarative conditions; no evaluation of user code."""
import math

OPERATORS = {"equals", "not_equals", "gt", "gte", "lt", "lte", "contains", "is_empty"}


def numeric(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def condition_leaves(condition):
    leaves = []
    count = 0
    def visit(node, depth):
        nonlocal count
        count += 1
        if depth > 3 or count > 20 or not isinstance(node, dict):
            raise ValueError("Condition exceeds depth/node limits")
        group = next((key for key in ("all", "any") if key in node), None)
        if group:
            if set(node) != {group} or not isinstance(node[group], list) or not 1 <= len(node[group]) <= 10:
                raise ValueError("Condition groups need 1–10 rules")
            for child in node[group]:
                visit(child, depth + 1)
            return
        if set(node) == {"field", "equals"}:
            operator, value = "equals", node["equals"]
        else:
            operator, value = node.get("operator"), node.get("value")
            expected = {"field", "operator"} if operator == "is_empty" else {"field", "operator", "value"}
            if not isinstance(operator, str) or operator not in OPERATORS or set(node) != expected:
                raise ValueError("Invalid condition operator or operands")
        if not isinstance(node.get("field"), str) or not node["field"]:
            raise ValueError("Condition needs a field key")
        if not (value is None or isinstance(value, (str, bool)) or numeric(value)):
            raise ValueError("Condition operands must be finite scalar values")
        if isinstance(value, str) and len(value) > 1000:
            raise ValueError("Condition text is too long")
        if operator in {"gt", "gte", "lt", "lte"} and not numeric(value):
            raise ValueError("Comparison needs a numeric operand")
        if operator == "contains" and not isinstance(value, str):
            raise ValueError("Contains needs a text operand")
        leaves.append((node["field"], operator, value))
    visit(condition, 0)
    return leaves


def matches(condition, values):
    if not condition:
        return True
    if "all" in condition:
        return all(matches(child, values) for child in condition["all"])
    if "any" in condition:
        return any(matches(child, values) for child in condition["any"])
    value = values.get(condition["field"])
    operator = condition.get("operator", "equals")
    expected = condition.get("value") if "operator" in condition else condition.get("equals")
    equal = (type(value) is type(expected) or numeric(value) and numeric(expected)) and value == expected
    if operator == "equals": return equal
    if operator == "not_equals": return not equal
    if operator == "is_empty": return value is None or value == "" or value == []
    if operator == "contains": return isinstance(value, str) and expected in value
    if not numeric(value) or not numeric(expected): return False
    if operator == "gt": return value > expected
    if operator == "gte": return value >= expected
    if operator == "lt": return value < expected
    if operator == "lte": return value <= expected
    return False
