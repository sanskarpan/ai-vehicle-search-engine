from __future__ import annotations

import re
from decimal import Decimal

from .domain import (
    ALLOWED_FEATURES,
    CATEGORY_FIELDS,
    FIELDS,
    NUMERIC_FIELDS,
    Intent,
    Predicate,
    Preference,
)

ALIASES = {
    "suvs": "suv",
    "suv": "suv",
    "sport utility vehicles": "suv",
    "cars": "car",
    "automatic": "automatic",
    "at": "automatic",
    "cvt": "automatic",
    "dct": "automatic",
    "amt": "automatic",
    "diesel": "diesel",
    "petrol": "petrol",
    "gasoline": "petrol",
    "electric": "electric",
    "ev": "electric",
    "mpv": "mpv",
    "sedan": "sedan",
    "hatchback": "hatchback",
    "new": "new",
    "used": "used",
    "bangalore": "bengaluru",
    "bengaluru": "bengaluru",
}

CLOSED_CATEGORIES = {
    "body_type": {"suv", "sedan", "hatchback", "mpv"},
    "fuel_type": {"petrol", "diesel", "cng", "electric", "hybrid"},
    "transmission": {"manual", "automatic"},
    "condition": {"new", "used"},
}
NUMERIC_LIMITS = {
    "price_inr": (1, 1_000_000_000),
    "odometer_km": (0, 2_000_000),
    "year": (1980, 2030),
    "seats": (1, 9),
    "adult_safety_stars": (0, 5),
    "child_safety_stars": (0, 5),
}
ALLOWED_PREFERENCES = {"family", "safety", "affordability", "low_odometer"}
ALLOWED_SORTS = {None, "relevance", "price_asc", "price_desc", "odometer_asc", "year_desc"}


def money_or_km(text: str, kind: str) -> int:
    s = text.strip().lower().replace(",", "").replace("₹", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(lakh|lac|l|crore|cr|k|km)?", s)
    if not m:
        raise ValueError("invalid quantity")
    n = Decimal(m.group(1))
    unit = m.group(2) or ""
    if kind == "price_inr":
        if unit in {"k", "km"}:
            raise ValueError("unsupported price unit")
        mult = {"lakh": 100000, "lac": 100000, "l": 100000, "crore": 10000000, "cr": 10000000}.get(
            unit, 1
        )
    else:
        if unit in {"lakh", "lac", "l", "crore", "cr"}:
            raise ValueError("unsupported distance unit")
        mult = {"k": 1000, "km": 1}.get(unit, 1)
    value = n * mult
    if value != value.to_integral_value():
        raise ValueError("fractional result")
    out = int(value)
    limits = {"price_inr": (0, 1_000_000_000), "odometer_km": (0, 2_000_000)}
    if kind in limits and not limits[kind][0] <= out <= limits[kind][1]:
        raise ValueError("out of range")
    return out


def canonical_category(field: str, value: str) -> str:
    raw = value.strip().lower()
    if field == "body_type" and raw.endswith("s"):
        raw = raw[:-1]
    return ALIASES.get(raw, raw)


def _numeric_value(field: str, value: object) -> int:
    if isinstance(value, bool):
        raise TypeError("boolean is not a numeric value")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str):
        result = money_or_km(value, field) if field in {"price_inr", "odometer_km"} else int(value)
    else:
        raise TypeError("numeric value must be an integer or string")
    minimum, maximum = NUMERIC_LIMITS[field]
    if not minimum <= result <= maximum:
        raise ValueError(f"{field} is out of range")
    return result


def expand_policies(intent: Intent) -> Intent:
    terms = (
        {x.code for x in getattr(intent, "policy_terms", [])}
        if hasattr(intent, "policy_terms")
        else set()
    )
    # Offline parser stores policies directly as assumptions/preferences; LLM adapter maps them before here.
    if "family" in terms:
        intent.predicates.append(Predicate("seats", "gte", [5], "policy", "family"))
        intent.preferences.append(Preference("family", "family"))
    if "high_safety" in terms:
        intent.predicates += [
            Predicate("adult_safety_stars", "gte", [4], "policy", "high safety"),
            Predicate("child_safety_stars", "gte", [4], "policy", "high safety"),
        ]
        intent.preferences.append(Preference("safety", "high safety"))
    if "five_star_safety" in terms:
        intent.predicates.append(
            Predicate("adult_safety_stars", "eq", [5], "policy", "5-star safety")
        )
        intent.preferences.append(Preference("safety", "5-star safety"))
    return intent


def validate_intent(intent: Intent) -> Intent:
    """Normalize and validate an intent in place, without duplicating issues on repeat calls."""
    issues = list(intent.issues)
    intent.issues = []
    if intent.intent not in {"search", "clarify", "out_of_scope"}:
        issues.append({"code": "unsupported", "evidence": "intent"})
    if intent.sort not in ALLOWED_SORTS:
        issues.append({"code": "unsupported", "evidence": "sort"})
    if any(p.code not in ALLOWED_PREFERENCES for p in intent.preferences):
        issues.append({"code": "unsupported", "evidence": "preference"})

    for p in intent.predicates:
        if not isinstance(p.values, list) or not p.values:
            issues.append({"code": "unverifiable", "evidence": p.evidence or p.field})
            continue
        if p.field not in FIELDS or p.op not in {
            "eq",
            "lt",
            "lte",
            "gt",
            "gte",
            "in",
            "not_in",
            "contains_all",
        }:
            issues.append({"code": "unsupported", "evidence": p.evidence or p.field})
            continue
        if p.field == "features" and p.op != "contains_all":
            issues.append({"code": "unsupported", "evidence": p.evidence or "feature operator"})
            continue
        if p.field != "features" and p.op == "contains_all":
            issues.append({"code": "unsupported", "evidence": p.evidence or "contains_all"})
            continue
        if p.field in NUMERIC_FIELDS and p.op in {"in", "not_in"}:
            issues.append({"code": "unsupported", "evidence": p.evidence or "numeric set operator"})
            continue
        if p.field in CATEGORY_FIELDS and p.op not in {"eq", "in", "not_in"}:
            issues.append({"code": "unsupported", "evidence": p.evidence or "category operator"})
            continue
        if p.op not in {"in", "not_in", "contains_all"} and len(p.values) != 1:
            issues.append({"code": "unverifiable", "evidence": p.evidence or p.field})
            continue
        if p.field in NUMERIC_FIELDS:
            try:
                p.values = [_numeric_value(p.field, p.values[0])]
            except (TypeError, ValueError):
                issues.append({"code": "unverifiable", "evidence": p.evidence})
        elif p.field in CATEGORY_FIELDS:
            p.values = [canonical_category(p.field, str(v)) for v in p.values]
            if p.field in CLOSED_CATEGORIES and any(
                v not in CLOSED_CATEGORIES[p.field] for v in p.values
            ):
                issues.append({"code": "unsupported", "evidence": p.evidence or p.field})
        elif p.field == "features":
            p.values = [str(v).lower() for v in p.values]
            if any(v not in ALLOWED_FEATURES for v in p.values):
                issues.append({"code": "unsupported", "evidence": p.evidence})

    # Detect empty intersections across numeric bounds and equality predicates.
    bounds: dict[str, list[tuple[str, int]]] = {}
    for p in intent.predicates:
        if p.field in NUMERIC_FIELDS and p.values and isinstance(p.values[0], int):
            bounds.setdefault(p.field, []).append((p.op, p.values[0]))
    for field, bs in bounds.items():
        equalities = {v for op, v in bs if op == "eq"}
        if len(equalities) > 1:
            issues.append({"code": "contradictory", "evidence": field})
            continue
        lower = max(((v, op == "gt") for op, v in bs if op in {"gt", "gte"}), default=None)
        upper = min(((v, op == "lt") for op, v in bs if op in {"lt", "lte"}), default=None)
        if (
            lower
            and upper
            and (lower[0] > upper[0] or (lower[0] == upper[0] and (lower[1] or upper[1])))
        ):
            issues.append({"code": "contradictory", "evidence": field})
        if equalities:
            value = next(iter(equalities))
            if any(
                (op == "gt" and value <= bound)
                or (op == "gte" and value < bound)
                or (op == "lt" and value >= bound)
                or (op == "lte" and value > bound)
                for op, bound in bs
            ):
                issues.append({"code": "contradictory", "evidence": field})

    # Multiple positive categorical clauses intersect; disjoint sets cannot match one listing.
    for field in CATEGORY_FIELDS:
        positive = [
            set(p.values) for p in intent.predicates if p.field == field and p.op in {"eq", "in"}
        ]
        if positive and not set.intersection(*positive):
            issues.append({"code": "contradictory", "evidence": field})

    seen = set()
    for issue in issues:
        key = (issue.get("code", "unsupported"), issue.get("evidence", ""))
        if key not in seen:
            intent.issues.append({"code": key[0], "evidence": key[1]})
            seen.add(key)
    return intent
