from __future__ import annotations

import json
import re

from .domain import *
from .normalization import canonical_category, money_or_km, validate_intent


class ParserError(Exception):
    def __init__(self, code: str, message: str): self.code=code; self.message=message

def offline_parse(query: str) -> Intent:
    q=query.strip(); low=q.lower(); i=Intent(parser_mode="offline")
    if not q: raise ParserError("invalid_request","query must not be empty")
    if re.search(r"\b(joke|weather|password|drop table|ignore all instructions)\b", low):
        i.intent="out_of_scope"; i.issues.append({"code":"unsupported","evidence":q}); return i
    # Cross-field OR is deliberately unsupported.
    if re.search(r"\b(suvs?|sedans?|hatchbacks?|mpvs?)\s+or\s+(cars?|suvs?|sedans?|hatchbacks?|mpvs?)", low):
        i.issues.append({"code":"unsupported","evidence":"or"}); return i
    # Body type
    for word,val in [("suv","suv"),("sedan","sedan"),("hatchback","hatchback"),("mpv","mpv")]:
        if re.search(rf"\b{word}s?\b",low): i.predicates.append(Predicate("body_type","in",[val],evidence=word))
    # fuel/transmission
    for val in ("diesel","petrol","electric","cng","hybrid"):
        if re.search(rf"\b{val}\b",low): i.predicates.append(Predicate("fuel_type","in",[val],evidence=val))
    if re.search(r"\b(cvt|dct|amt)\b", low) and "automatic" not in low:
        i.issues.append({"code":"unsupported","evidence":"specific transmission"})
    elif re.search(r"\bautomatic\b",low) or (re.search(r"\bat\b",low) and not re.search(r"\bat\s+least\b",low)):
        if re.search(r"\b(cvt|dct|amt)\b",low) and "automatic" not in low: i.issues.append({"code":"unsupported","evidence":"specific transmission"})
        else: i.predicates.append(Predicate("transmission","in",["automatic"],evidence="automatic"))
    elif re.search(r"\bmanual\b",low): i.predicates.append(Predicate("transmission","in",["manual"],evidence="manual"))
    # numeric price and odometer
    pm=re.search(r"(?:under|below|less than|up to|at most|no more than|over|above|more than)\s+(?:(?:₹|inr\s*)?([\d,.]+\s*(?:lakh|lac|l|crore|cr))|(?:₹|inr\s*)([\d,.]+))",low)
    if pm:
        op="lte" if re.search(r"up to|at most|no more",pm.group(0)) else ("gt" if re.search(r"over|above|more than",pm.group(0)) else "lt")
        literal=pm.group(1) or pm.group(2)
        try: i.predicates.append(Predicate("price_inr",op,[money_or_km(literal,"price_inr")],evidence=pm.group(0)))
        except ValueError: i.issues.append({"code":"unverifiable","evidence":pm.group(0)})
    extra_pm=re.search(r"(?:over|above|more than)\s+(?:(?:₹|inr\s*)?([\d,.]+\s*(?:lakh|lac|l|crore|cr))|(?:₹|inr\s*)([\d,.]+))",low)
    if extra_pm and (not pm or extra_pm.group(0) != pm.group(0)):
        literal=extra_pm.group(1) or extra_pm.group(2)
        try: i.predicates.append(Predicate("price_inr","gt",[money_or_km(literal,"price_inr")],evidence=extra_pm.group(0)))
        except ValueError: i.issues.append({"code":"unverifiable","evidence":extra_pm.group(0)})
    elif re.search(r"(?:under|below)\s+\$",low): i.issues.append({"code":"unsupported","evidence":"currency"})
    elif re.search(r"(?:under|below|up to|at most)\s+\d",low) and not pm and "km" not in low: i.issues.append({"code":"ambiguous","evidence":"budget unit"})
    om=re.search(r"(?:below|under|less than|up to|at most)\s+([\d,.]+\s*(?:km|k))\s*(?:km|kilomet(?:er|re)s?)?",low)
    if om and ("km" in low or "mileage" in low):
        op="lte" if re.search(r"up to|at most",om.group(0)) else "lt"
        try: i.predicates.append(Predicate("odometer_km",op,[money_or_km(om.group(1),"odometer_km")],evidence=om.group(0)))
        except ValueError: i.issues.append({"code":"unverifiable","evidence":om.group(0)})
    if "low mileage" in low and "km" not in low: i.issues.append({"code":"ambiguous","evidence":"low mileage"})
    # policies
    if "family" in low:
        m=re.search(r"family\s+(?:of|for)\s+(\d+)",low); seats=int(m.group(1)) if m else 5
        i.predicates.append(Predicate("seats","gte",[seats],"policy","family")); i.preferences.append(Preference("family","family")); i.assumptions.append(f"Family means at least {seats} seats in the demo policy.")
    if "high safety" in low or "highly rated for safety" in low:
        i.predicates += [Predicate("adult_safety_stars","gte",[4],"policy","high safety"),Predicate("child_safety_stars","gte",[4],"policy","high safety")]; i.preferences.append(Preference("safety","high safety")); i.assumptions.append("High safety means at least 4 adult and 4 child synthetic stars.")
    if "5-star safety" in low or "5 star safety" in low:
        i.predicates.append(Predicate("adult_safety_stars","eq",[5],"policy","5-star safety")); i.preferences.append(Preference("safety","5-star safety")); i.assumptions.append("5-star safety uses the synthetic adult-star field.")
    if "affordable" in low or "budget-friendly" in low: i.preferences.append(Preference("affordability","affordable"))
    if "low odometer" in low: i.preferences.append(Preference("low_odometer","low odometer"))
    if re.search(r"\bnew\b", low): i.predicates.append(Predicate("condition","in",["new"],evidence="new"))
    ym=re.search(r"newer than\s+(\d{4})",low)
    if ym: i.predicates.append(Predicate("year","gt",[int(ym.group(1))],evidence=ym.group(0)))
    if re.search(r"\b(exclude|excluding|without)\s+diesel\b",low):
        i.predicates=[p for p in i.predicates if not (p.field=="fuel_type" and "diesel" in p.values)]
        i.predicates.append(Predicate("fuel_type","not_in",["diesel"],evidence="exclude diesel"))
    # city aliases and simple feature
    for city in ("bangalore","bengaluru","pune","mumbai","delhi","hyderabad","chennai"):
        if city in low: i.predicates.append(Predicate("city","in",[canonical_category("city",city)],evidence=city))
    if "isofix" in low: i.predicates.append(Predicate("features","contains_all",["isofix"],evidence="isofix"))
    if re.search(r"\b(cheapest|price ascending)\b",low): i.sort="price_asc"
    elif re.search(r"\bmost expensive|price descending\b",low): i.sort="price_desc"
    elif "newest" in low: i.sort="year_desc"
    # Contradictory fuel conjunction and unsupported range/approximation.
    if "petrol" in low and "diesel" in low and "or" not in low: i.issues.append({"code":"contradictory","evidence":"petrol and diesel"})
    if re.search(r"\b(range|fuel economy|mpg|mileage efficiency)\b",low): i.issues.append({"code":"unsupported","evidence":"range or efficiency"})
    if re.search(r"\b(strong safety|rear air conditioning|rear aircon)\b",low): i.issues.append({"code":"unsupported","evidence":"unsupported attribute"})
    if re.search(r"\b(ignore|bypass)\b",low): i.issues.append({"code":"unsupported","evidence":"ignore instructions"})
    if re.search(r"\b(around|about|roughly|near)\b",low) and re.search(r"\d",low): i.issues.append({"code":"ambiguous","evidence":"approximate budget"})
    # The offline grammar is intentionally conservative; explicit unsupported patterns above clarify.
    return validate_intent(i)

def parse_provider_json(raw: str, query: str) -> Intent:
    try: obj=json.loads(raw)
    except json.JSONDecodeError as e: raise ParserError("llm_invalid_response","provider returned invalid JSON") from e
    allowed={"intent","predicates","preferences","sort","sort_evidence","issues","policy_terms"}
    if set(obj)-allowed: raise ParserError("llm_invalid_response","provider returned extra fields")
    if obj.get("intent") not in {"search","clarify","out_of_scope"}: raise ParserError("llm_invalid_response","invalid intent")
    i=Intent(intent=obj.get("intent","search"), parser_mode="llm")
    for p in obj.get("predicates",[]):
        if not isinstance(p,dict) or not {"field","op","values","evidence"}<=set(p): raise ParserError("llm_invalid_response","invalid predicate")
        if p["evidence"] not in query: raise ParserError("llm_invalid_response","predicate evidence is not in query")
        i.predicates.append(Predicate(p["field"],p["op"],p["values"],"explicit",p["evidence"]))
    i.preferences=[Preference(x["code"],x.get("evidence","")) for x in obj.get("preferences",[])]
    i.sort=obj.get("sort") if obj.get("sort")!="unspecified" else None
    for x in obj.get("issues",[]): i.issues.append(x)
    for x in obj.get("policy_terms",[]):
        code=x.get("code"); ev=x.get("evidence","")
        if ev not in query: raise ParserError("llm_invalid_response","policy evidence is not in query")
        if code=="family": i.predicates.append(Predicate("seats","gte",[5],"policy",ev)); i.preferences.append(Preference("family",ev)); i.assumptions.append("Family means at least 5 seats in the demo policy.")
        elif code=="high_safety": i.predicates += [Predicate("adult_safety_stars","gte",[4],"policy",ev),Predicate("child_safety_stars","gte",[4],"policy",ev)]; i.preferences.append(Preference("safety",ev)); i.assumptions.append("High safety means at least 4 adult and 4 child synthetic stars.")
        elif code=="five_star_safety": i.predicates.append(Predicate("adult_safety_stars","eq",[5],"policy",ev)); i.preferences.append(Preference("safety",ev)); i.assumptions.append("5-star safety uses the synthetic adult-star field.")
    return validate_intent(i)


def require_supported_coverage(intent: Intent, query: str) -> Intent:
    """Reject a schema-valid provider answer that drops a deterministic supported constraint."""
    reference = offline_parse(query)
    if reference.issues:
        return intent
    expected = {(p.field, p.op, tuple(p.values)) for p in reference.predicates}
    actual = {(p.field, p.op, tuple(p.values)) for p in intent.predicates}
    if expected and not expected.issubset(actual):
        raise ParserError("llm_invalid_response", "provider omitted a supported query constraint")
    return intent
