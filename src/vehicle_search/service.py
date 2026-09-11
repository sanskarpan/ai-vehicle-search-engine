from __future__ import annotations

from .domain import Intent, vehicle_json
from .normalization import validate_intent
from .ranking import score, sort_key
from .storage import search


def reasons(v, predicates):
    out = []
    labels = {
        "price_inr": "Asking price",
        "odometer_km": "Odometer",
        "seats": "Seats",
        "adult_safety_stars": "Adult safety stars",
        "child_safety_stars": "Child safety stars",
        "body_type": "Body type",
        "fuel_type": "Fuel type",
        "transmission": "Transmission",
        "condition": "Condition",
        "city": "City",
        "features": "Features",
    }
    for p in predicates:
        val = (
            v.price_inr
            if p.field == "price_inr"
            else v.odometer_km
            if p.field == "odometer_km"
            else getattr(v, p.field, None)
        )
        if p.field == "features":
            out.append(f"Features include {', '.join(p.values)}.")
            continue
        if p.field in {"adult_safety_stars", "child_safety_stars"} and val is None:
            continue
        display = val
        if p.field == "price_inr":
            display = f"₹{val:,}"
        out.append(
            f"{labels.get(p.field, p.field)} matches {p.op} {p.values[0]} (value: {display})."
        )
    return out


def execute(intent: Intent, conn, query: str, limit: int, offset: int, sort_override=None):
    validate_intent(intent)
    if intent.issues or intent.intent != "search":
        raw_code = intent.issues[0].get("code") if intent.issues else "unsupported_query"
        code = {
            "ambiguous": "ambiguous_query",
            "contradictory": "contradictory_query",
            "unverifiable": "unverifiable_query",
        }.get(raw_code, "unsupported_query")
        messages = {
            "ambiguous_query": "Please clarify the ambiguous vehicle criterion.",
            "contradictory_query": "The requested criteria conflict; please revise them.",
            "unverifiable_query": "Please provide the criterion with a supported value and unit.",
            "unsupported_query": "Please provide a supported vehicle search with explicit criteria.",
        }
        return {
            "status": "needs_clarification",
            "clarification": {"code": code, "message": messages[code]},
            "interpretation": None,
            "results": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "has_more": False,
        }
    candidates = search(conn, intent.predicates)
    total = len(candidates)
    effective_sort = sort_override or intent.sort
    assumptions = list(intent.assumptions)
    if sort_override and intent.sort and sort_override != intent.sort:
        assumptions.append(f"API sort '{sort_override}' overrides query sort '{intent.sort}'.")
    ordered = sorted(candidates, key=lambda v: sort_key(v, intent.preferences, effective_sort))
    page = ordered[offset : offset + limit]
    return {
        "status": "ok",
        "clarification": None,
        "interpretation": {
            "predicates": [p.__dict__ for p in intent.predicates],
            "preferences": [p.__dict__ for p in intent.preferences],
            "sort": effective_sort or "relevance",
            "assumptions": assumptions,
        },
        "results": [
            {
                "vehicle": vehicle_json(v),
                "score": round(score(v, intent.preferences), 4),
                "match_reasons": reasons(v, intent.predicates),
            }
            for v in page
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(page) < total,
    }
