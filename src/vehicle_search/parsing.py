from __future__ import annotations

import json
import re

from .domain import *
from .normalization import canonical_category, money_or_km, validate_intent


class ParserError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message


def offline_parse(query: str) -> Intent:
    q = query.strip()
    low = q.lower()
    intent = Intent(parser_mode="offline")
    if not q:
        raise ParserError("invalid_request", "query must not be empty")
    if re.search(
        r"\b(joke|weather|password|drop\s+table|ignore\s+(?:all|previous|the)\s+(?:instructions|rules))\b",
        low,
    ):
        intent.intent = "out_of_scope"
        intent.issues.append({"code": "unsupported", "evidence": q})
        return intent

    body_terms = {
        "suv": r"\b(?:suvs?|sport utility vehicles?)\b",
        "sedan": r"\bsedans?\b",
        "hatchback": r"\bhatchbacks?\b",
        "mpv": r"\bmpvs?\b",
    }
    body_matches = [(value, re.search(pattern, low)) for value, pattern in body_terms.items()]
    found_bodies = [(value, match) for value, match in body_matches if match]
    if len(found_bodies) > 1 and re.search(r"\bor\b", low):
        intent.predicates.append(
            Predicate(
                "body_type",
                "in",
                [x[0] for x in found_bodies],
                evidence=" or ".join(x[1].group(0) for x in found_bodies),
            )
        )
    else:
        for value, match in found_bodies:
            intent.predicates.append(Predicate("body_type", "in", [value], evidence=match.group(0)))
    if re.search(r"\b(?:suvs?|sedans?|hatchbacks?|mpvs?)\s+or\s+(?:cars?|vehicles?)\b", low):
        intent.issues.append({"code": "unsupported", "evidence": "or"})

    excluded_fuels = []
    for value in ("diesel", "petrol", "electric", "cng", "hybrid"):
        if re.search(rf"\b(?:not|exclude|excluding|without)\s+{value}\b", low):
            excluded_fuels.append(value)
    fuels = [
        value
        for value in ("diesel", "petrol", "electric", "cng", "hybrid")
        if re.search(rf"\b{value}\b", low) and value not in excluded_fuels
    ]
    if len(fuels) > 1:
        if re.search(r"\b(?:" + "|".join(fuels) + r")\s+or\s+(?:" + "|".join(fuels) + r")\b", low):
            intent.predicates.append(
                Predicate("fuel_type", "in", fuels, evidence=" or ".join(fuels))
            )
        else:
            intent.issues.append({"code": "contradictory", "evidence": " and ".join(fuels)})
    elif fuels:
        intent.predicates.append(Predicate("fuel_type", "in", fuels, evidence=fuels[0]))
    if excluded_fuels:
        intent.predicates.append(
            Predicate(
                "fuel_type",
                "not_in",
                excluded_fuels,
                evidence="exclude " + ", ".join(excluded_fuels),
            )
        )

    subtype = re.search(r"\b(cvt|dct|amt)\b", low)
    if subtype and re.search(r"\b(specifically|specific|only)\b", low):
        intent.issues.append({"code": "unsupported", "evidence": subtype.group(0)})
    elif (
        re.search(r"\bautomatic\b", low)
        or (re.search(r"\bat\b", low) and not re.search(r"\bat\s+(?:least|most)\b", low))
        or subtype
    ):
        match = re.search(r"\b(?:automatic|at|cvt|dct|amt)\b", low)
        intent.predicates.append(
            Predicate("transmission", "in", ["automatic"], evidence=match.group(0))
        )
    elif re.search(r"\bmanual\b", low):
        intent.predicates.append(Predicate("transmission", "in", ["manual"], evidence="manual"))

    quantity = r"(?:₹\s*|inr\s*)?[\d,.]+\s*(?:lakh|lac|crore|cr|km|k|l)?"
    range_match = re.search(rf"\bbetween\s+({quantity})\s+and\s+({quantity})", low)
    if range_match:
        try:
            lower = money_or_km(range_match.group(1).replace("inr", ""), "price_inr")
            upper = money_or_km(range_match.group(2).replace("inr", ""), "price_inr")
            intent.predicates.extend(
                [
                    Predicate("price_inr", "gte", [lower], evidence=range_match.group(1)),
                    Predicate("price_inr", "lte", [upper], evidence=range_match.group(2)),
                ]
            )
        except ValueError:
            intent.issues.append({"code": "unverifiable", "evidence": range_match.group(0)})

    comparator_pattern = re.compile(
        rf"\b(under|below|less than|up to|at most|no more than|over|above|more than|at least|minimum)\s+({quantity})"
    )
    for match in comparator_pattern.finditer(low):
        evidence = match.group(0)
        literal = match.group(2)
        if (
            range_match
            and match.start() >= range_match.start()
            and match.end() <= range_match.end()
        ):
            continue
        nearby = low[match.end() : match.end() + 14]
        if re.match(r"\s*(?:seats?|people|year)\b", nearby):
            continue
        is_distance = (
            literal.strip().endswith("km")
            or bool(re.match(r"\s*(?:km|kilomet(?:er|re)s?)\b", nearby))
            or "mileage" in low
        )
        field = "odometer_km" if is_distance else "price_inr"
        if field == "price_inr" and not re.search(r"₹|inr|(?:lakh|lac|l|crore|cr)\s*$", literal):
            intent.issues.append({"code": "ambiguous", "evidence": evidence})
            continue
        op = (
            "lte"
            if match.group(1) in {"up to", "at most", "no more than"}
            else "gte"
            if match.group(1) in {"at least", "minimum"}
            else "gt"
            if match.group(1) in {"over", "above", "more than"}
            else "lt"
        )
        try:
            cleaned = literal.replace("inr", "")
            value = money_or_km(cleaned, field)
            intent.predicates.append(Predicate(field, op, [value], evidence=evidence))
        except ValueError:
            intent.issues.append({"code": "unverifiable", "evidence": evidence})

    if re.search(r"\b(?:under|below|up to|at most)\s+\$", low):
        intent.issues.append({"code": "unsupported", "evidence": "currency"})
    if "low mileage" in low and not re.search(r"\d[^.]{0,20}(?:km|kilomet)", low):
        intent.issues.append({"code": "ambiguous", "evidence": "low mileage"})

    explicit_seats = re.search(r"\b(?:at least|minimum)\s+(\d+)\s+(?:seats?|people)\b", low)
    hyphen_seats = re.search(r"\b(\d+)[ -]seat\b", low)
    family_size = re.search(r"\bfamily\s+(?:of|for)\s+(\d+)\b", low)
    seat_count = (
        int((family_size or explicit_seats or hyphen_seats).group(1))
        if family_size or explicit_seats or hyphen_seats
        else None
    )
    if "family" in low:
        seats = seat_count or 5
        intent.predicates.append(Predicate("seats", "gte", [seats], "policy", "family"))
        intent.preferences.append(Preference("family", "family"))
        intent.assumptions.append(f"Family means at least {seats} seats in the demo policy.")
    elif seat_count is not None:
        evidence = (explicit_seats or hyphen_seats).group(0)
        intent.predicates.append(Predicate("seats", "gte", [seat_count], evidence=evidence))

    if "high safety" in low or "highly rated for safety" in low:
        intent.predicates.extend(
            [
                Predicate("adult_safety_stars", "gte", [4], "policy", "high safety"),
                Predicate("child_safety_stars", "gte", [4], "policy", "high safety"),
            ]
        )
        intent.preferences.append(Preference("safety", "high safety"))
        intent.assumptions.append("High safety means at least 4 adult and 4 child synthetic stars.")
    if re.search(r"\b(?:5|five)[ -]star(?: safety| cars?)?\b", low):
        evidence = re.search(r"\b(?:5|five)[ -]star(?: safety| cars?)?\b", low).group(0)
        intent.predicates.append(Predicate("adult_safety_stars", "eq", [5], "policy", evidence))
        intent.preferences.append(Preference("safety", evidence))
        intent.assumptions.append("Five-star safety uses the synthetic adult-star field.")
    if re.search(r"\b(?:safest|prioriti[sz]e safety)\b", low):
        intent.preferences.append(Preference("safety", "safety"))
    if "affordable" in low or "budget-friendly" in low:
        intent.preferences.append(Preference("affordability", "affordable"))
    if "low odometer" in low:
        intent.preferences.append(Preference("low_odometer", "low odometer"))

    for condition in ("new", "used"):
        if re.search(rf"\b{condition}\b", low):
            intent.predicates.append(Predicate("condition", "in", [condition], evidence=condition))
    year_match = re.search(r"\bnewer than\s+(\d{4})\b", low)
    if year_match:
        intent.predicates.append(
            Predicate("year", "gt", [int(year_match.group(1))], evidence=year_match.group(0))
        )

    for city in ("bangalore", "bengaluru", "pune", "mumbai", "delhi", "hyderabad", "chennai"):
        if re.search(rf"\b{city}\b", low):
            intent.predicates.append(
                Predicate("city", "in", [canonical_category("city", city)], evidence=city)
            )
    known_features = [
        feature
        for feature in ("isofix", "esc", "rear_ac", "parking_camera", "cruise_control")
        if feature.replace("_", " ") in low
    ]
    if known_features:
        intent.predicates.append(
            Predicate(
                "features", "contains_all", known_features, evidence=" and ".join(known_features)
            )
        )
    elif re.search(r"\bfeatures?\b", low):
        intent.issues.append({"code": "unsupported", "evidence": "feature"})

    if re.search(r"\b(?:cheapest|price ascending)\b", low):
        intent.sort = "price_asc"
    elif re.search(r"\b(?:most expensive|price descending)\b", low):
        intent.sort = "price_desc"
    elif "newest" in low:
        intent.sort = "year_desc"

    make_match = re.search(r"\b(?:show|find)\s+([a-z][a-z0-9-]*)\s+cars?\b", low)
    ignored_make_words = {
        "all",
        "new",
        "used",
        "affordable",
        "family",
        "diesel",
        "petrol",
        "electric",
        "automatic",
        "manual",
    }
    if make_match and make_match.group(1) not in ignored_make_words:
        intent.predicates.append(
            Predicate("make", "in", [make_match.group(1)], evidence=make_match.group(1))
        )

    if re.search(r"\b(range|fuel economy|mpg|mileage efficiency|kmpl)\b", low):
        intent.issues.append({"code": "unsupported", "evidence": "range or efficiency"})
    if re.search(r"\b(strong safety|rear air conditioning|rear aircon)\b", low):
        intent.issues.append({"code": "unsupported", "evidence": "unsupported attribute"})
    if re.search(r"\b(ignore|bypass)\b", low):
        intent.issues.append({"code": "unsupported", "evidence": "ignore instructions"})
    if re.search(r"\b(around|about|roughly|near)\b", low) and re.search(r"\d", low):
        intent.issues.append({"code": "ambiguous", "evidence": "approximate budget"})
    return validate_intent(intent)


def parse_provider_json(raw: str, query: str) -> Intent:
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ParserError("llm_invalid_response", "provider returned invalid JSON") from e
    allowed = {
        "intent",
        "predicates",
        "preferences",
        "sort",
        "sort_evidence",
        "issues",
        "policy_terms",
    }
    if set(obj) - allowed:
        raise ParserError("llm_invalid_response", "provider returned extra fields")
    if obj.get("intent") not in {"search", "clarify", "out_of_scope"}:
        raise ParserError("llm_invalid_response", "invalid intent")
    i = Intent(intent=obj.get("intent", "search"), parser_mode="llm")
    for p in obj.get("predicates", []):
        if not isinstance(p, dict) or not {"field", "op", "values", "evidence"} <= set(p):
            raise ParserError("llm_invalid_response", "invalid predicate")
        if (
            not isinstance(p["values"], list)
            or not p["values"]
            or not all(isinstance(v, str) for v in p["values"])
        ):
            raise ParserError("llm_invalid_response", "invalid predicate values")
        if (
            not isinstance(p["evidence"], str)
            or not isinstance(p["field"], str)
            or not isinstance(p["op"], str)
        ):
            raise ParserError("llm_invalid_response", "invalid predicate fields")
        if not p["evidence"] or p["evidence"] not in query:
            raise ParserError("llm_invalid_response", "predicate evidence is not in query")
        i.predicates.append(Predicate(p["field"], p["op"], p["values"], "explicit", p["evidence"]))
    for preference in obj.get("preferences", []):
        if not isinstance(preference, dict) or set(preference) != {"code", "evidence"}:
            raise ParserError("llm_invalid_response", "invalid preference")
        if not isinstance(preference["code"], str) or not isinstance(preference["evidence"], str):
            raise ParserError("llm_invalid_response", "invalid preference")
        if not preference["evidence"] or preference["evidence"] not in query:
            raise ParserError("llm_invalid_response", "preference evidence is not in query")
        i.preferences.append(Preference(preference["code"], preference["evidence"]))
    i.sort = obj.get("sort") if obj.get("sort") != "unspecified" else None
    sort_evidence = obj.get("sort_evidence")
    if not isinstance(obj.get("sort"), str) or not isinstance(sort_evidence, str):
        raise ParserError("llm_invalid_response", "invalid sort")
    if i.sort is not None and (not sort_evidence or sort_evidence not in query):
        raise ParserError("llm_invalid_response", "sort evidence is not in query")
    for issue in obj.get("issues", []):
        if not isinstance(issue, dict) or set(issue) != {"code", "evidence"}:
            raise ParserError("llm_invalid_response", "invalid issue")
        if not isinstance(issue["code"], str) or not isinstance(issue["evidence"], str):
            raise ParserError("llm_invalid_response", "invalid issue")
        if not issue["evidence"] or issue["evidence"] not in query:
            raise ParserError("llm_invalid_response", "issue evidence is not in query")
        i.issues.append(issue)
    for x in obj.get("policy_terms", []):
        if not isinstance(x, dict) or set(x) != {"code", "evidence"}:
            raise ParserError("llm_invalid_response", "invalid policy term")
        code = x.get("code")
        ev = x.get("evidence", "")
        if not isinstance(code, str) or not isinstance(ev, str) or not ev or ev not in query:
            raise ParserError("llm_invalid_response", "policy evidence is not in query")
        if code == "family":
            i.predicates.append(Predicate("seats", "gte", [5], "policy", ev))
            i.preferences.append(Preference("family", ev))
            i.assumptions.append("Family means at least 5 seats in the demo policy.")
        elif code == "high_safety":
            i.predicates += [
                Predicate("adult_safety_stars", "gte", [4], "policy", ev),
                Predicate("child_safety_stars", "gte", [4], "policy", ev),
            ]
            i.preferences.append(Preference("safety", ev))
            i.assumptions.append("High safety means at least 4 adult and 4 child synthetic stars.")
        elif code == "five_star_safety":
            i.predicates.append(Predicate("adult_safety_stars", "eq", [5], "policy", ev))
            i.preferences.append(Preference("safety", ev))
            i.assumptions.append("5-star safety uses the synthetic adult-star field.")
        else:
            raise ParserError("llm_invalid_response", "unsupported policy term")
    declared_issues = len(i.issues)
    validate_intent(i)
    if len(i.issues) > declared_issues:
        raise ParserError("llm_invalid_response", "provider returned an invalid canonical intent")
    return i


def require_supported_coverage(intent: Intent, query: str) -> Intent:
    """Reject a schema-valid provider answer that drops a deterministic supported constraint."""
    reference = offline_parse(query)
    if reference.issues:
        known = {(x.get("code"), x.get("evidence")) for x in intent.issues}
        for issue in reference.issues:
            if (issue.get("code"), issue.get("evidence")) not in known:
                intent.issues.append(issue)
        return intent

    def key(predicate: Predicate):
        values = (
            frozenset(predicate.values)
            if predicate.op in {"in", "not_in", "contains_all"}
            else tuple(predicate.values)
        )
        return predicate.field, predicate.op, values

    expected = {key(p) for p in reference.predicates}
    actual = {key(p) for p in intent.predicates}
    if expected and not expected.issubset(actual):
        raise ParserError("llm_invalid_response", "provider omitted a supported query constraint")
    return intent
