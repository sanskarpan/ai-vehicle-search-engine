from __future__ import annotations

import re
from decimal import Decimal

from .domain import *

ALIASES = {"suvs":"suv", "suv":"suv", "sport utility vehicles":"suv", "cars":"car",
 "automatic":"automatic", "at":"automatic", "cvt":"automatic", "dct":"automatic", "amt":"automatic",
 "diesel":"diesel", "petrol":"petrol", "gasoline":"petrol", "electric":"electric", "ev":"electric",
 "mpv":"mpv", "sedan":"sedan", "hatchback":"hatchback", "new":"new", "used":"used",
 "bangalore":"bengaluru", "bengaluru":"bengaluru"}

def money_or_km(text: str, kind: str) -> int:
    s = text.strip().lower().replace(",", "").replace("₹", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(lakh|lac|l|crore|cr|k|km)?", s)
    if not m: raise ValueError("invalid quantity")
    n = Decimal(m.group(1)); unit = m.group(2) or ""
    if kind == "price_inr":
        mult = {"lakh":100000,"lac":100000,"l":100000,"crore":10000000,"cr":10000000}.get(unit,1)
    else:
        mult = {"k":1000,"km":1}.get(unit,1)
    value = n * mult
    if value != value.to_integral_value(): raise ValueError("fractional result")
    out = int(value)
    limits = {"price_inr": (0, 1_000_000_000), "odometer_km": (0, 2_000_000)}
    if kind in limits and not limits[kind][0] <= out <= limits[kind][1]: raise ValueError("out of range")
    return out

def canonical_category(field: str, value: str) -> str:
    raw = value.strip().lower()
    if field == "body_type" and raw.endswith("s"): raw = raw[:-1]
    return ALIASES.get(raw, raw)

def expand_policies(intent: Intent) -> Intent:
    terms = {x.code for x in getattr(intent, "policy_terms", [])} if hasattr(intent, "policy_terms") else set()
    # Offline parser stores policies directly as assumptions/preferences; LLM adapter maps them before here.
    if "family" in terms:
        intent.predicates.append(Predicate("seats", "gte", [5], "policy", "family"))
        intent.preferences.append(Preference("family", "family"))
    if "high_safety" in terms:
        intent.predicates += [Predicate("adult_safety_stars", "gte", [4], "policy", "high safety"), Predicate("child_safety_stars", "gte", [4], "policy", "high safety")]
        intent.preferences.append(Preference("safety", "high safety"))
    if "five_star_safety" in terms:
        intent.predicates.append(Predicate("adult_safety_stars", "eq", [5], "policy", "5-star safety"))
        intent.preferences.append(Preference("safety", "5-star safety"))
    return intent

def validate_intent(intent: Intent) -> Intent:
    for p in intent.predicates:
        if not isinstance(p.values, list) or not p.values:
            intent.issues.append({"code":"unverifiable","evidence":p.evidence or p.field}); continue
        if p.field not in FIELDS or p.op not in {"eq","lt","lte","gt","gte","in","not_in","contains_all"}:
            intent.issues.append({"code":"unsupported","evidence":p.evidence or p.field}); continue
        if p.field == "features" and p.op != "contains_all":
            intent.issues.append({"code":"unsupported","evidence":p.evidence or "feature operator"}); continue
        if p.field != "features" and p.op == "contains_all":
            intent.issues.append({"code":"unsupported","evidence":p.evidence or "contains_all"}); continue
        if p.field in NUMERIC_FIELDS and p.op in {"in", "not_in"}:
            intent.issues.append({"code":"unsupported","evidence":p.evidence or "numeric set operator"}); continue
        if p.op not in {"in", "not_in", "contains_all"} and len(p.values) != 1:
            intent.issues.append({"code":"unverifiable","evidence":p.evidence or p.field}); continue
        if p.field in NUMERIC_FIELDS:
            try: p.values = [int(v) for v in p.values]
            except (TypeError, ValueError): intent.issues.append({"code":"unverifiable","evidence":p.evidence})
        elif p.field in CATEGORY_FIELDS: p.values = [canonical_category(p.field, str(v)) for v in p.values]
        elif p.field == "features":
            p.values = [str(v).lower() for v in p.values]
            if any(v not in ALLOWED_FEATURES for v in p.values): intent.issues.append({"code":"unsupported","evidence":p.evidence})
    # Intersect same-field numeric bounds and detect obvious contradictions.
    bounds: dict[str, list[tuple[str,int]]] = {}
    for p in intent.predicates:
        if p.field in NUMERIC_FIELDS and p.values: bounds.setdefault(p.field, []).append((p.op,p.values[0]))
    for field, bs in bounds.items():
        lo = max((v for op,v in bs if op in {"gt","gte"}), default=None); hi = min((v for op,v in bs if op in {"lt","lte"}), default=None)
        if lo is not None and hi is not None and (lo > hi or (lo == hi and any(op=="gt" for op,v in bs) and any(op=="lt" for op,v in bs))):
            intent.issues.append({"code":"contradictory","evidence":field})
    return intent
