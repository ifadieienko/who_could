"""Bounded, non-recursive table values. Permissions apply to the whole field."""
from datetime import date
from decimal import Decimal
import math
from fastapi import HTTPException


def normalize_table(spec, value, *, complete=False):
    title = spec["label"]
    def invalid(message):
        raise HTTPException(422, title + ": " + message)
    if value is None or value == "":
        value = []
    if not isinstance(value, list) or len(value) > spec.get("max_rows", 100):
        invalid("Недопустимое количество строк")
    if complete and len(value) < max(spec.get("min_rows", 0), int(spec.get("required", False))):
        invalid("Добавьте обязательные строки")
    columns = {c["key"]: c for c in spec["columns"]}
    rows = []
    for index, row in enumerate(value, 1):
        if not isinstance(row, dict) or set(row) - columns.keys():
            invalid(f"Строка {index}: неизвестные столбцы")
        result = {}
        for key, col in columns.items():
            cell = row.get(key)
            typ = col["type"]
            where = f"Строка {index}, {col['label']}"
            if cell is None or cell == "":
                cell = None
            elif typ in {"string", "text", "select"}:
                if not isinstance(cell, str) or len(cell) > 1000:
                    invalid(where + ": некорректный текст")
                cell = cell.strip() or None
                if cell is not None and typ == "select" and cell not in col["options"]:
                    invalid(where + ": недопустимый вариант")
            elif typ == "number":
                if isinstance(cell, bool) or not isinstance(cell, (int, float)) or not math.isfinite(cell) or abs(cell) > 1e12:
                    invalid(where + ": некорректное число")
                if col.get("min") is not None and cell < col["min"] or col.get("max") is not None and cell > col["max"]:
                    invalid(where + ": число вне диапазона")
                precision = col.get("precision")
                if precision is not None and max(0, -Decimal(str(cell)).normalize().as_tuple().exponent) > precision:
                    invalid(where + ": слишком много знаков после запятой")
            elif typ == "checkbox":
                if not isinstance(cell, bool):
                    invalid(where + ": ожидается флажок")
            elif typ == "date":
                try:
                    cell = date.fromisoformat(cell).isoformat()
                except (TypeError, ValueError):
                    invalid(where + ": некорректная дата")
            if complete and col.get("required") and (cell is None or typ == "checkbox" and cell is not True):
                invalid(where + ": обязательное значение")
            result[key] = cell
        rows.append(result)
    return rows
