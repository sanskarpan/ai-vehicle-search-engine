import hashlib
import json
import sqlite3
import sys

import pytest

from vehicle_search import seed as seed_module
from vehicle_search.seed import build, main, seed_database
from vehicle_search.storage import connect, validate_catalogue


def test_seed_build_is_reproducible():
    first = [v.__dict__ for v in build(300, 42)]
    second = [v.__dict__ for v in build(300, 42)]
    assert first == second
    assert (
        hashlib.sha256(json.dumps(first, sort_keys=True).encode()).hexdigest()
        == "d8ae2d00dfddb9c9490bda231f8d8be95dfca13b8f3303417d0c490da45867d1"
    )


def test_seed_noop_and_reset(tmp_path, monkeypatch, capsys):
    db = tmp_path / "catalogue.db"
    monkeypatch.setattr(
        sys, "argv", ["vehicle-seed", "--count", "8", "--seed", "7", "--db", str(db)]
    )
    main()
    capsys.readouterr()
    monkeypatch.setattr(
        sys, "argv", ["vehicle-seed", "--count", "8", "--seed", "7", "--db", str(db)]
    )
    main()
    assert "already seeded" in capsys.readouterr().out
    monkeypatch.setattr(
        sys, "argv", ["vehicle-seed", "--count", "9", "--seed", "8", "--db", str(db)]
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    monkeypatch.setattr(
        sys, "argv", ["vehicle-seed", "--count", "9", "--seed", "8", "--db", str(db), "--reset"]
    )
    main()
    capsys.readouterr()
    conn = connect(str(db), read_only=True)
    assert conn.execute("SELECT count(*) FROM vehicles").fetchone()[0] == 9
    assert validate_catalogue(conn)["schema_version"] == "1"
    conn.close()


def test_database_constraints_reject_invalid_vehicle(tmp_path):
    db = tmp_path / "catalogue.db"
    seed_database(str(db), count=8, seed=42)
    conn = connect(str(db))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE vehicles SET price_inr = 0 WHERE id = 'veh_000001'")
    conn.close()


def test_default_seed_coverage_and_coherence():
    vehicles = build(300, 42)
    assert {vehicle.body_type for vehicle in vehicles} == {"suv", "sedan", "hatchback", "mpv"}
    assert {vehicle.fuel_type for vehicle in vehicles} >= {"petrol", "diesel", "cng", "electric"}
    assert {vehicle.transmission for vehicle in vehicles} == {"manual", "automatic"}
    assert sum(vehicle.adult_safety_stars is None for vehicle in vehicles) / len(vehicles) > 0.10
    assert sum(vehicle.child_safety_stars is None for vehicle in vehicles) / len(vehicles) > 0.10
    assert all(vehicle.odometer_km <= 500 for vehicle in vehicles if vehicle.condition == "new")
    assert all(
        vehicle.transmission == "automatic"
        for vehicle in vehicles
        if vehicle.fuel_type == "electric"
    )


def test_failed_seed_rolls_back_all_rows(tmp_path, monkeypatch):
    database = tmp_path / "catalogue.db"
    calls = 0
    real_insert = seed_module.insert_vehicle

    def fail_on_third(connection, vehicle):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("simulated failure")
        real_insert(connection, vehicle)

    monkeypatch.setattr("vehicle_search.seed.insert_vehicle", fail_on_third)
    with pytest.raises(RuntimeError, match="simulated failure"):
        seed_database(str(database), count=8, seed=42)
    connection = connect(str(database), read_only=True)
    assert connection.execute("SELECT count(*) FROM vehicles").fetchone()[0] == 0
    connection.close()
