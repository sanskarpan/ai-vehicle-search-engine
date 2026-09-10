import pytest

from vehicle_search.domain import Intent, Predicate
from vehicle_search.normalization import validate_intent
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
