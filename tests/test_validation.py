import pytest

from vehicle_search.domain import Intent, Predicate
from vehicle_search.normalization import money_or_km, validate_intent
from vehicle_search.parsing import ParserError, parse_provider_json


@pytest.mark.parametrize(
    "predicate",
    [
        Predicate("price_inr", "contains_all", ["1500000"], evidence="budget"),
        Predicate("features", "eq", ["isofix"], evidence="isofix"),
        Predicate("price_inr", "lt", [], evidence="budget"),
        Predicate("price_inr", "lt", [1500000, 1600000], evidence="budget"),
    ],
)
def test_validate_intent_rejects_incompatible_predicates(predicate):
    intent = validate_intent(Intent(predicates=[predicate]))
    assert intent.issues


def test_provider_values_are_typed_and_nonempty():
    with pytest.raises(ParserError, match="invalid predicate values"):
        parse_provider_json(
            '{"intent":"search","predicates":[{"field":"body_type","op":"in","values":"suv","evidence":"SUV"}],"preferences":[],"sort":"unspecified","sort_evidence":"","issues":[],"policy_terms":[]}',
            "Show SUV",
        )


@pytest.mark.parametrize(
    ("text", "kind", "expected"),
    [
        ("12.5L", "price_inr", 1_250_000),
        ("1.2 crore", "price_inr", 12_000_000),
        ("80k", "odometer_km", 80_000),
        ("80k km", "odometer_km", 80_000),
    ],
)
def test_quantity_normalization(text, kind, expected):
    assert money_or_km(text, kind) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("15,00,000", 1_500_000), ("1,500,000", 1_500_000), ("12,34,567", 1_234_567)],
)
def test_price_accepts_valid_indian_and_international_grouping(text, expected):
    assert money_or_km(text, "price_inr") == expected


@pytest.mark.parametrize("text", ["1,2,3L", "15,000,00", "1,00,00"])
def test_quantity_rejects_malformed_comma_grouping(text):
    with pytest.raises(ValueError, match="comma grouping"):
        money_or_km(text, "price_inr")


def test_provider_numeric_units_are_normalized():
    intent = parse_provider_json(
        '{"intent":"search","predicates":[{"field":"price_inr","op":"lt","values":["15L"],"evidence":"under 15L"}],"preferences":[],"sort":"unspecified","sort_evidence":"","issues":[],"policy_terms":[]}',
        "SUVs under 15L",
    )
    assert intent.predicates[0].values == [1_500_000]


@pytest.mark.parametrize(
    "predicates",
    [
        [Predicate("price_inr", "gte", [1_000_000]), Predicate("price_inr", "lt", [1_000_000])],
        [Predicate("price_inr", "gt", [1_000_000]), Predicate("price_inr", "lte", [1_000_000])],
        [Predicate("price_inr", "eq", [1_000_000]), Predicate("price_inr", "gt", [1_000_000])],
    ],
)
def test_empty_numeric_intersections_are_contradictory(predicates):
    intent = validate_intent(Intent(predicates=predicates))
    assert any(issue["code"] == "contradictory" for issue in intent.issues)


def test_validation_is_idempotent():
    intent = Intent(predicates=[Predicate("body_type", "in", ["truck"], evidence="truck")])
    validate_intent(intent)
    first = list(intent.issues)
    validate_intent(intent)
    assert intent.issues == first


def test_positive_category_fully_excluded_is_contradictory():
    intent = validate_intent(
        Intent(
            predicates=[
                Predicate("fuel_type", "in", ["diesel"]),
                Predicate("fuel_type", "not_in", ["diesel"]),
            ]
        )
    )
    assert any(issue["code"] == "contradictory" for issue in intent.issues)


@pytest.mark.parametrize(
    "payload",
    [
        "[]",
        '{"intent":"search"}',
        '{"intent":"search","predicates":"bad","preferences":[],"sort":"unspecified","sort_evidence":"","issues":[],"policy_terms":[]}',
    ],
)
def test_provider_rejects_invalid_top_level_shapes(payload):
    with pytest.raises(ParserError, match="invalid"):
        parse_provider_json(payload, "Show SUVs")
