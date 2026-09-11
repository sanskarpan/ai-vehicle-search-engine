import pytest
from fastapi.testclient import TestClient

from vehicle_search.api import create_app
from vehicle_search.domain import Predicate, Preference
from vehicle_search.parsing import ParserError
from vehicle_search.ranking import sort_key
from vehicle_search.seed import seed_database
from vehicle_search.storage import connect, search, search_page


def fixture_db(tmp_path):
    db = tmp_path / "cat.db"
    seed_database(str(db), count=8, seed=42)
    return db


def client(tmp_path, monkeypatch):
    db = fixture_db(tmp_path)
    monkeypatch.setenv("PARSER_MODE", "offline")
    return TestClient(create_app(str(db)))


@pytest.mark.parametrize(
    ("preferences", "sort"),
    [
        ([], None),
        ([Preference("family")], None),
        ([Preference("safety"), Preference("affordability")], None),
        ([Preference("low_odometer")], None),
        ([], "price_asc"),
        ([], "price_desc"),
        ([], "odometer_asc"),
        ([], "year_desc"),
    ],
)
def test_sql_paging_matches_reference_python_order(tmp_path, preferences, sort):
    database = tmp_path / "ranking.db"
    seed_database(str(database), count=300, seed=42)
    connection = connect(str(database), read_only=True)
    predicates = [Predicate("body_type", "in", ["suv", "sedan"])]
    expected = sorted(search(connection, predicates), key=lambda v: sort_key(v, preferences, sort))
    actual, total = search_page(connection, predicates, preferences, sort, 37, 11)
    connection.close()
    assert total == len(expected)
    assert [vehicle.id for vehicle in actual] == [vehicle.id for vehicle in expected[11:48]]


def test_strict_price_boundary(tmp_path, monkeypatch):
    r = client(tmp_path, monkeypatch).post("/api/v1/search", json={"query": "Show SUVs under ₹15L"})
    assert r.status_code == 200
    ids = [x["vehicle"]["id"] for x in r.json()["results"]]
    assert "veh_000002" not in ids
    assert "veh_000001" in ids


def test_inclusive_price_boundary(tmp_path, monkeypatch):
    r = client(tmp_path, monkeypatch).post("/api/v1/search", json={"query": "Show SUVs up to ₹15L"})
    assert r.status_code == 200
    ids = [x["vehicle"]["id"] for x in r.json()["results"]]
    assert "veh_000002" in ids
    assert "veh_000003" not in ids


def test_diesel_automatic_odometer(tmp_path, monkeypatch):
    r = client(tmp_path, monkeypatch).post(
        "/api/v1/search", json={"query": "Diesel automatic cars below 80k km"}
    )
    assert r.status_code == 200
    ids = [x["vehicle"]["id"] for x in r.json()["results"]]
    assert ids == ["veh_000005", "veh_000006", "veh_000001"]


def test_family_safety_and_nulls(tmp_path, monkeypatch):
    r = client(tmp_path, monkeypatch).post(
        "/api/v1/search", json={"query": "Family cars with high safety ratings"}
    )
    assert r.status_code == 200
    ids = {x["vehicle"]["id"] for x in r.json()["results"]}
    assert ids == {"veh_000001", "veh_000002", "veh_000003", "veh_000004", "veh_000006"}


def test_clarification_and_zero_results(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    assert (
        c.post("/api/v1/search", json={"query": "Low mileage cars"}).json()["status"]
        == "needs_clarification"
    )
    r = c.post("/api/v1/search", json={"query": "SUVs under ₹1L"}).json()
    assert r["status"] == "ok" and r["total"] == 0


def test_pagination(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    a = c.post("/api/v1/search", json={"query": "Show cars", "limit": 3}).json()
    b = c.post("/api/v1/search", json={"query": "Show cars", "limit": 3, "offset": 3}).json()
    assert (
        a["total"] == 8
        and b["total"] == 8
        and not (
            {x["vehicle"]["id"] for x in a["results"]} & {x["vehicle"]["id"] for x in b["results"]}
        )
    )


def test_validation_rejects_extra_and_empty(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    for payload in (
        {"query": " ", "x": 1},
        {"query": "Show cars", "sort": "random"},
        {"query": "Show cars", "limit": True},
    ):
        response = c.post("/api/v1/search", json=payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_request"
        assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_frontend_is_served(tmp_path, monkeypatch):
    response = client(tmp_path, monkeypatch).get("/")
    assert response.status_code == 200
    assert 'aria-label="Vehicle search query"' in response.text
    assert 'role="status"' in response.text
    assert not any(symbol in response.text for symbol in ("⌕", "↗", "✦", "◌", "←", "→", "★", "×"))
    assert '<svg class="icon icon-search"' in response.text


def test_detail_and_missing_detail_are_stable(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    assert c.get("/api/v1/vehicles/veh_000001").status_code == 200
    missing = c.get("/api/v1/vehicles/does-not-exist")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"


def test_large_request_and_unseeded_readiness(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    assert (
        c.post(
            "/api/v1/search",
            content='{"query":"x"}',
            headers={"content-type": "application/json", "content-length": "9000"},
        ).status_code
        == 413
    )
    unseeded = tmp_path / "missing.db"
    empty_client = TestClient(create_app(str(unseeded)))
    assert empty_client.get("/health/ready").status_code == 503
    assert empty_client.get("/api/v1/vehicles/veh_000001").status_code == 503


def test_request_id_and_openapi_contract(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    response = c.post("/api/v1/search", json={"query": "Show cars"})
    body = response.json()
    assert response.headers["X-Request-ID"] == body["request_id"]
    assert body["meta"]["parser_mode"] == "offline"
    operation = c.get("/openapi.json").json()["paths"]["/api/v1/search"]["post"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert operation["responses"]["422"]["content"]["application/json"]["schema"]


def test_offset_beyond_results_returns_empty_page(tmp_path, monkeypatch):
    response = client(tmp_path, monkeypatch).post(
        "/api/v1/search", json={"query": "Show cars", "offset": 10000}
    )
    body = response.json()
    assert (
        response.status_code == 200
        and body["total"] == 8
        and body["results"] == []
        and body["has_more"] is False
    )


def test_budget_shorthand_is_not_partially_matched(tmp_path, monkeypatch):
    body = (
        client(tmp_path, monkeypatch)
        .post("/api/v1/search", json={"query": "SUVs under ₹1k"})
        .json()
    )
    assert body["status"] == "needs_clarification"


def test_unknown_feature_does_not_match_every_vehicle(tmp_path, monkeypatch):
    body = (
        client(tmp_path, monkeypatch)
        .post("/api/v1/search", json={"query": "cars with an unknown feature xyz"})
        .json()
    )
    assert body["status"] == "needs_clarification" and body["results"] == []


@pytest.mark.parametrize(
    "query",
    [
        "luxury cars",
        "SUVs with sunroof",
        "red automatic cars",
        "cheap but spacious cars",
        "cars near me",
    ],
)
def test_offline_parser_does_not_drop_residual_requirements(tmp_path, monkeypatch, query):
    body = client(tmp_path, monkeypatch).post("/api/v1/search", json={"query": query}).json()
    assert body["status"] == "needs_clarification" and body["results"] == []


def test_invalid_provider_output_never_uses_degraded_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("PARSER_MODE", "llm")
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_MODEL", "openrouter/free")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("ALLOW_OFFLINE_FALLBACK", "true")

    class BrokenParser:
        def parse(self, query):
            raise ParserError("llm_invalid_response", "bad structured output")

    monkeypatch.setattr("vehicle_search.api.build_parser", lambda *args, **kwargs: BrokenParser())
    response = TestClient(create_app(str(fixture_db(tmp_path)))).post(
        "/api/v1/search", json={"query": "Show SUVs"}
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "llm_invalid_response"


def test_transient_provider_failure_uses_explicit_degraded_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("PARSER_MODE", "llm")
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_MODEL", "openrouter/free")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("ALLOW_OFFLINE_FALLBACK", "true")

    class UnavailableParser:
        def parse(self, query):
            raise ParserError("llm_unavailable", "provider unavailable")

    monkeypatch.setattr(
        "vehicle_search.api.build_parser", lambda *args, **kwargs: UnavailableParser()
    )
    response = TestClient(create_app(str(fixture_db(tmp_path)))).post(
        "/api/v1/search", json={"query": "Show SUVs"}
    )
    body = response.json()
    assert response.status_code == 200 and body["status"] == "ok"
    assert body["meta"]["degraded"] is True and body["meta"]["parser_mode"] == "offline"


def test_transient_fallback_does_not_partially_answer_unsupported_query(tmp_path, monkeypatch):
    monkeypatch.setenv("PARSER_MODE", "llm")
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_MODEL", "openrouter/free")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("ALLOW_OFFLINE_FALLBACK", "true")

    class UnavailableParser:
        def parse(self, query):
            raise ParserError("llm_unavailable", "provider unavailable")

    monkeypatch.setattr(
        "vehicle_search.api.build_parser", lambda *args, **kwargs: UnavailableParser()
    )
    response = TestClient(create_app(str(fixture_db(tmp_path)))).post(
        "/api/v1/search", json={"query": "Low mileage cars"}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "llm_unavailable"


def test_unknown_issue_codes_are_normalized(tmp_path, monkeypatch):
    from vehicle_search.domain import Intent
    from vehicle_search.service import execute

    conn = connect(str(fixture_db(tmp_path)), read_only=True)
    body = execute(
        Intent(issues=[{"code": "PARAMETER_MISSING", "evidence": "budget"}]), conn, "query", 10, 0
    )
    conn.close()
    assert body["clarification"]["code"] == "unsupported_query"


@pytest.mark.parametrize(
    ("code", "status", "retryable"),
    [
        ("llm_timeout", 504, True),
        ("llm_unavailable", 503, True),
        ("llm_configuration_error", 503, False),
        ("llm_invalid_response", 502, False),
    ],
)
def test_provider_errors_use_stable_http_envelope(tmp_path, monkeypatch, code, status, retryable):
    monkeypatch.setenv("PARSER_MODE", "llm")
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_MODEL", "openrouter/free")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    class FailedParser:
        def parse(self, query):
            raise ParserError(code, "safe provider error")

    monkeypatch.setattr("vehicle_search.api.build_parser", lambda *args, **kwargs: FailedParser())
    response = TestClient(create_app(str(fixture_db(tmp_path)))).post(
        "/api/v1/search", json={"query": "Show SUVs"}
    )
    body = response.json()
    assert response.status_code == status
    assert body["error"] == {"code": code, "message": "safe provider error", "retryable": retryable}
    assert response.headers["X-Request-ID"] == body["request_id"]


def test_invalid_runtime_configuration_fails_readiness_and_search(tmp_path, monkeypatch):
    monkeypatch.setenv("PARSER_MODE", "invalid")
    app = TestClient(create_app(str(fixture_db(tmp_path))))
    assert app.get("/health/ready").status_code == 503
    response = app.post("/api/v1/search", json={"query": "Show cars"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "llm_configuration_error"


def test_unknown_route_uses_stable_error_envelope(tmp_path, monkeypatch):
    response = client(tmp_path, monkeypatch).get("/api/v1/unknown")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"
    assert response.headers["X-Request-ID"] == response.json()["request_id"]
