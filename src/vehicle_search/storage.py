from __future__ import annotations

import sqlite3
from pathlib import Path

from .domain import Predicate, Vehicle

SCHEMA_VERSION = "1"
SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS vehicles (
    id TEXT PRIMARY KEY CHECK (id GLOB 'veh_[0-9][0-9][0-9][0-9][0-9][0-9]'),
    make TEXT NOT NULL CHECK (length(make) BETWEEN 1 AND 80),
    model TEXT NOT NULL CHECK (length(model) BETWEEN 1 AND 80),
    variant TEXT NOT NULL CHECK (length(variant) BETWEEN 1 AND 80),
    year INTEGER NOT NULL CHECK (year BETWEEN 1980 AND 2030),
    price_inr INTEGER NOT NULL CHECK (price_inr BETWEEN 1 AND 1000000000),
    odometer_km INTEGER NOT NULL CHECK (odometer_km BETWEEN 0 AND 2000000),
    condition TEXT NOT NULL CHECK (condition IN ('new', 'used')),
    body_type TEXT NOT NULL CHECK (body_type IN ('suv', 'sedan', 'hatchback', 'mpv')),
    fuel_type TEXT NOT NULL CHECK (fuel_type IN ('petrol', 'diesel', 'cng', 'electric', 'hybrid')),
    transmission TEXT NOT NULL CHECK (transmission IN ('manual', 'automatic')),
    seats INTEGER NOT NULL CHECK (seats BETWEEN 1 AND 9),
    city TEXT NOT NULL CHECK (length(city) BETWEEN 1 AND 80),
    adult_safety_stars INTEGER CHECK (adult_safety_stars BETWEEN 0 AND 5),
    child_safety_stars INTEGER CHECK (child_safety_stars BETWEEN 0 AND 5),
    description TEXT NOT NULL CHECK (length(description) <= 500),
    safety_test_year INTEGER CHECK (safety_test_year BETWEEN 1980 AND 2030),
    safety_applicability TEXT NOT NULL CHECK (length(safety_applicability) <= 240),
    CHECK (condition != 'new' OR odometer_km <= 500)
);
CREATE TABLE IF NOT EXISTS vehicle_features (
    vehicle_id TEXT NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    feature TEXT NOT NULL CHECK (feature IN ('isofix', 'esc', 'rear_ac', 'parking_camera', 'cruise_control')),
    PRIMARY KEY (vehicle_id, feature)
);
CREATE TABLE IF NOT EXISTS catalogue_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vehicles_filter
    ON vehicles(body_type, fuel_type, transmission, price_inr, odometer_km);
CREATE INDEX IF NOT EXISTS idx_vehicles_city ON vehicles(city);
CREATE INDEX IF NOT EXISTS idx_vehicle_features_feature ON vehicle_features(feature, vehicle_id);
"""


def connect(path: str, read_only: bool = False) -> sqlite3.Connection:
    database = Path(path)
    if read_only:
        if not database.is_file():
            raise FileNotFoundError(path)
        connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True, timeout=5)
        connection.execute("PRAGMA query_only = ON")
    else:
        database.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(database, timeout=5)
        connection.executescript(SCHEMA)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def insert_vehicle(connection: sqlite3.Connection, vehicle: Vehicle) -> None:
    connection.execute(
        "INSERT INTO vehicles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            vehicle.id,
            vehicle.make,
            vehicle.model,
            vehicle.variant,
            vehicle.year,
            vehicle.price_inr,
            vehicle.odometer_km,
            vehicle.condition,
            vehicle.body_type,
            vehicle.fuel_type,
            vehicle.transmission,
            vehicle.seats,
            vehicle.city,
            vehicle.adult_safety_stars,
            vehicle.child_safety_stars,
            vehicle.description,
            vehicle.safety_test_year,
            vehicle.safety_applicability,
        ),
    )
    connection.executemany(
        "INSERT INTO vehicle_features VALUES (?,?)",
        [(vehicle.id, feature) for feature in vehicle.features],
    )


def _row_vehicle(row: tuple, features: list[str]) -> Vehicle:
    return Vehicle(
        *row[:13],
        features,
        row[13],
        row[14],
        row[15],
        True,
        "synthetic_demo_v1",
        "demo_v1",
        row[16],
        None,
        row[17],
    )


def _feature_map(connection: sqlite3.Connection, ids: list[str]) -> dict[str, list[str]]:
    features = {vehicle_id: [] for vehicle_id in ids}
    for start in range(0, len(ids), 500):
        chunk = ids[start : start + 500]
        placeholders = ",".join("?" for _ in chunk)
        rows = connection.execute(
            f"SELECT vehicle_id, feature FROM vehicle_features "
            f"WHERE vehicle_id IN ({placeholders}) ORDER BY vehicle_id, feature",
            chunk,
        )
        for vehicle_id, feature in rows:
            features[vehicle_id].append(feature)
    return features


def search(connection: sqlite3.Connection, predicates: list[Predicate]) -> list[Vehicle]:
    where: list[str] = []
    arguments: list[object] = []
    features: list[str] = []
    columns = {
        "price_inr": "price_inr",
        "odometer_km": "odometer_km",
        "year": "year",
        "seats": "seats",
        "adult_safety_stars": "adult_safety_stars",
        "child_safety_stars": "child_safety_stars",
        "body_type": "body_type",
        "fuel_type": "fuel_type",
        "transmission": "transmission",
        "make": "lower(make)",
        "model": "lower(model)",
        "city": "lower(city)",
        "condition": "condition",
    }
    operators = {
        "eq": "=",
        "lt": "<",
        "lte": "<=",
        "gt": ">",
        "gte": ">=",
        "in": "IN",
        "not_in": "NOT IN",
    }
    for predicate in predicates:
        if predicate.field == "features":
            features.extend(predicate.values)
            continue
        if predicate.field not in columns or predicate.op not in operators:
            raise ValueError("unsupported predicate")
        column = columns[predicate.field]
        values = predicate.values
        if predicate.op in {"in", "not_in"}:
            if not values:
                raise ValueError("empty predicate")
            placeholders = ",".join("?" for _ in values)
            where.append(f"{column} {operators[predicate.op]} ({placeholders})")
            arguments.extend(
                str(value).lower() if predicate.field in {"make", "model", "city"} else value
                for value in values
            )
        else:
            where.append(f"{column} {operators[predicate.op]} ?")
            arguments.append(values[0])
    for feature in features:
        where.append(
            "EXISTS (SELECT 1 FROM vehicle_features vf "
            "WHERE vf.vehicle_id = v.id AND vf.feature = ?)"
        )
        arguments.append(feature)
    sql = (
        "SELECT v.id,v.make,v.model,v.variant,v.year,v.price_inr,v.odometer_km,"
        "v.condition,v.body_type,v.fuel_type,v.transmission,v.seats,v.city,"
        "v.adult_safety_stars,v.child_safety_stars,v.description,v.safety_test_year,"
        "v.safety_applicability FROM vehicles v"
        + (" WHERE " + " AND ".join(where) if where else "")
        + " ORDER BY v.id"
    )
    rows = connection.execute(sql, arguments).fetchall()
    feature_map = _feature_map(connection, [row[0] for row in rows])
    return [_row_vehicle(row, feature_map[row[0]]) for row in rows]


def get(connection: sqlite3.Connection, vehicle_id: str) -> Vehicle | None:
    row = connection.execute(
        "SELECT id,make,model,variant,year,price_inr,odometer_km,condition,body_type,"
        "fuel_type,transmission,seats,city,adult_safety_stars,child_safety_stars,"
        "description,safety_test_year,safety_applicability FROM vehicles WHERE id=?",
        (vehicle_id,),
    ).fetchone()
    if row is None:
        return None
    features = [
        item[0]
        for item in connection.execute(
            "SELECT feature FROM vehicle_features WHERE vehicle_id=? ORDER BY feature",
            (vehicle_id,),
        )
    ]
    return _row_vehicle(row, features)


def validate_catalogue(connection: sqlite3.Connection) -> dict[str, str]:
    required = {
        "schema_version",
        "seed_version",
        "seed_number",
        "reference_date",
        "record_count",
        "data_hash",
        "catalogue_version",
    }
    metadata = dict(connection.execute("SELECT key, value FROM catalogue_metadata"))
    if not required <= metadata.keys() or metadata["schema_version"] != SCHEMA_VERSION:
        raise sqlite3.DatabaseError("catalogue metadata or schema version is invalid")
    count = connection.execute("SELECT count(*) FROM vehicles").fetchone()[0]
    if count <= 0 or count != int(metadata["record_count"]):
        raise sqlite3.DatabaseError("catalogue record count does not match metadata")
    if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise sqlite3.DatabaseError("catalogue integrity check failed")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise sqlite3.DatabaseError("catalogue foreign-key check failed")
    return metadata
