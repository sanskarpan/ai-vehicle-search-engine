from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

FIELDS = {
    "price_inr",
    "odometer_km",
    "year",
    "seats",
    "adult_safety_stars",
    "child_safety_stars",
    "body_type",
    "fuel_type",
    "transmission",
    "make",
    "model",
    "city",
    "condition",
    "features",
}
NUMERIC_FIELDS = {
    "price_inr",
    "odometer_km",
    "year",
    "seats",
    "adult_safety_stars",
    "child_safety_stars",
}
CATEGORY_FIELDS = {"body_type", "fuel_type", "transmission", "make", "model", "city", "condition"}
ALLOWED_FEATURES = {"isofix", "esc", "rear_ac", "parking_camera", "cruise_control"}


@dataclass
class Predicate:
    field: str
    op: str
    values: list[Any]
    source: str = "explicit"
    evidence: str = ""


@dataclass
class Preference:
    code: str
    evidence: str = ""


@dataclass
class Intent:
    intent: str = "search"
    predicates: list[Predicate] = field(default_factory=list)
    preferences: list[Preference] = field(default_factory=list)
    sort: str | None = None
    issues: list[dict[str, str]] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    parser_mode: str = "offline"


@dataclass
class Vehicle:
    id: str
    make: str
    model: str
    variant: str
    year: int
    price_inr: int
    odometer_km: int
    condition: str
    body_type: str
    fuel_type: str
    transmission: str
    seats: int
    city: str
    features: list[str]
    adult_safety_stars: int | None
    child_safety_stars: int | None
    description: str
    is_synthetic: bool = True
    safety_scheme: str = "synthetic_demo_v1"
    safety_protocol: str = "demo_v1"
    safety_test_year: int | None = None
    safety_source_url: str | None = None
    safety_applicability: str = ""


def vehicle_json(v: Vehicle) -> dict[str, Any]:
    return {
        "id": v.id,
        "make": v.make,
        "model": v.model,
        "variant": v.variant,
        "year": v.year,
        "price_inr": v.price_inr,
        "odometer_km": v.odometer_km,
        "condition": v.condition,
        "body_type": v.body_type,
        "fuel_type": v.fuel_type,
        "transmission": v.transmission,
        "seats": v.seats,
        "city": v.city,
        "features": v.features,
        "safety": {
            "scheme": v.safety_scheme,
            "protocol": v.safety_protocol,
            "test_year": v.safety_test_year,
            "adult_stars": v.adult_safety_stars,
            "child_stars": v.child_safety_stars,
            "source_url": v.safety_source_url,
            "applicability": v.safety_applicability,
            "is_synthetic": v.is_synthetic,
        },
        "description": v.description,
        "is_synthetic": v.is_synthetic,
    }
