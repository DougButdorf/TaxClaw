"""Strict field scoring. Missing is not null; null is not zero; extras are errors."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

MISSING = object()


def flatten(value: Any, path: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        if not value:
            return {path: {}}
        return {p: v for k, child in value.items()
                for p, v in flatten(child, f"{path}.{k}" if path else k).items()}
    if isinstance(value, list):
        if not value:
            return {path: []}
        return {p: v for i, child in enumerate(value)
                for p, v in flatten(child, f"{path}.{i}").items()}
    return {path: value}


def containers(value: Any, path: str = "") -> dict[str, str]:
    if not isinstance(value, (dict, list)):
        return {}
    result = {path: "object" if isinstance(value, dict) else "array"}
    items = value.items() if isinstance(value, dict) else enumerate(value)
    for key, child in items:
        result.update(containers(child, f"{path}.{key}" if path else str(key)))
    return result


def normalized(value: Any, kind: str) -> Any:
    if value is None or value is MISSING:
        return value
    if kind == "boolean":
        # Do not let bool == int, or a guessed string, pass checkbox grading.
        if type(value) is not bool:
            raise ValueError("not a JSON boolean")
        return value
    if kind in {"money", "number", "percent"}:
        if isinstance(value, bool):
            raise ValueError("boolean is not numeric")
        text = str(value).strip().replace(",", "")
        if kind == "money":
            if text.startswith("(") and text.endswith(")"):
                text = "-" + text[1:-1].removeprefix("$").strip()
            else:
                text = text.removeprefix("$").strip()
        if kind == "percent":
            text = text.removesuffix("%")
        result = Decimal(text)
        if not result.is_finite():
            raise ValueError("non-finite number")
        return result
    if not isinstance(value, str):
        raise ValueError("not a string")
    text = unicodedata.normalize("NFKC", value).strip()
    if kind == "date":
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                pass
        raise ValueError("unrecognized date")
    if kind == "identifier":
        # Preserve leading zeroes and all masking characters.
        return re.sub(r"[\s-]", "", text).casefold()
    return " ".join(text.split()).casefold()


def score(expected: dict, actual: Any, field_types: dict[str, str]) -> dict:
    gold = flatten(expected)
    found = flatten(actual) if isinstance(actual, dict) else {}
    expected_shapes, actual_shapes = containers(expected), containers(actual)
    shape_errors = sorted(path for path, kind in expected_shapes.items()
                          if actual_shapes.get(path) != kind)
    fields = []
    for path, wanted in gold.items():
        received = found.get(path, MISSING)
        try:
            shape_ok = not any(not prefix or path == prefix or path.startswith(prefix + ".")
                               for prefix in shape_errors)
            correct = (shape_ok and received is not MISSING and
                       normalized(wanted, field_types.get(path, "text")) ==
                       normalized(received, field_types.get(path, "text")))
        except (ValueError, TypeError, InvalidOperation):
            correct = False
        fields.append({"path": path, "kind": field_types.get(path, "text"),
                       "expected": wanted, "actual": None if received is MISSING else received,
                       "present": received is not MISSING, "correct": correct})
    extras = sorted(set(found) - set(gold))
    correct = sum(f["correct"] for f in fields)
    populated = [f for f in fields if f["expected"] is not None]
    blank = [f for f in fields if f["expected"] is None]
    return {"correct": correct, "expected_fields": len(gold),
            "accuracy": correct / len(gold) if gold else 0,
            "populated_correct": sum(f["correct"] for f in populated),
            "populated_fields": len(populated),
            "blank_correct": sum(f["correct"] for f in blank), "blank_fields": len(blank),
            "extra_fields": extras,
            "shape_errors": shape_errors,
            "exact_document": correct == len(gold) and not extras and not shape_errors,
            "fields": fields}
