from __future__ import annotations

import argparse
import hashlib
import json
import random
from contextlib import closing

from .domain import ALLOWED_FEATURES, Vehicle
from .storage import SCHEMA, SCHEMA_VERSION, connect, insert_vehicle

SEED_VERSION = "synthetic_demo_v1"
REFERENCE_DATE = "2026-01-01"
REFERENCE_DATE_YEAR = 2026

ANCHORS = [
    (
        "Aster",
        "Trail",
        "D AT",
        2023,
        1499999,
        79999,
        "used",
        "suv",
        "diesel",
        "automatic",
        5,
        "pune",
        5,
        4,
        ["isofix", "esc", "rear_ac"],
    ),
    (
        "Aster",
        "Trail",
        "D AT Edge",
        2023,
        1500000,
        80000,
        "used",
        "suv",
        "diesel",
        "automatic",
        5,
        "pune",
        5,
        4,
        ["isofix", "esc", "rear_ac"],
    ),
    (
        "Aster",
        "Trail",
        "D AT Plus",
        2023,
        1500001,
        80001,
        "used",
        "suv",
        "diesel",
        "automatic",
        5,
        "pune",
        5,
        4,
        ["isofix", "esc", "rear_ac"],
    ),
    (
        "Meridian",
        "City",
        "P MT",
        2023,
        900000,
        40000,
        "used",
        "sedan",
        "petrol",
        "manual",
        5,
        "pune",
        4,
        4,
        ["isofix", "esc"],
    ),
    (
        "Meridian",
        "Vista",
        "D AT",
        2023,
        1200000,
        50000,
        "used",
        "suv",
        "diesel",
        "automatic",
        5,
        "pune",
        None,
        None,
        ["rear_ac"],
    ),
    (
        "Cedar",
        "People",
        "D AT",
        2023,
        1400000,
        70000,
        "used",
        "mpv",
        "diesel",
        "automatic",
        7,
        "pune",
        5,
        5,
        ["isofix", "esc", "rear_ac"],
    ),
    (
        "Cedar",
        "Mini",
        "P MT",
        2023,
        600000,
        20000,
        "used",
        "hatchback",
        "petrol",
        "manual",
        4,
        "pune",
        3,
        2,
        [],
    ),
    (
        "Aster",
        "Volt",
        "EV",
        2025,
        1300000,
        100,
        "new",
        "suv",
        "electric",
        "automatic",
        5,
        "bengaluru",
        4,
        3,
        ["isofix", "esc"],
    ),
]
TEMPLATES = [
    ("Aster", "Trail", "suv", ("diesel", "petrol"), 1_200_000, 3_200_000),
    ("Meridian", "City", "sedan", ("petrol", "diesel", "hybrid"), 800_000, 2_200_000),
    ("Cedar", "People", "mpv", ("diesel", "petrol"), 1_100_000, 2_600_000),
    ("Nova", "Swift", "hatchback", ("petrol", "cng"), 550_000, 1_200_000),
    ("Aster", "Volt", "suv", ("electric",), 1_200_000, 2_800_000),
]


def build(count: int = 300, seed: int = 42) -> list[Vehicle]:
    if count < len(ANCHORS):
        raise ValueError(f"count must be at least {len(ANCHORS)}")
    rng = random.Random(seed)
    vehicles: list[Vehicle] = []
    for number, anchor in enumerate(ANCHORS, 1):
        (
            make,
            model,
            variant,
            year,
            price,
            odometer,
            condition,
            body,
            fuel,
            transmission,
            seats,
            city,
            adult,
            child,
            features,
        ) = anchor
        vehicles.append(
            Vehicle(
                f"veh_{number:06d}",
                make,
                model,
                variant,
                year,
                price,
                odometer,
                condition,
                body,
                fuel,
                transmission,
                seats,
                city,
                features,
                adult,
                child,
                f"Synthetic {seats}-seat {fuel} {transmission} {body}.",
                True,
                "synthetic_demo_v1",
                "demo_v1",
                year if adult is not None else None,
                None,
                f"{make} {model} {variant} {year}",
            )
        )
    while len(vehicles) < count:
        index = len(vehicles) + 1
        make, model, body, fuels, minimum_price, maximum_price = rng.choice(TEMPLATES)
        fuel = rng.choice(fuels)
        transmission = (
            "automatic" if fuel in {"electric", "hybrid"} or rng.random() < 0.45 else "manual"
        )
        seats = (
            7
            if body == "mpv"
            else rng.choice([5, 7])
            if body == "suv"
            else 5
            if rng.random() < 0.8
            else 4
        )
        year = rng.randint(2018, 2026)
        condition = "new" if year >= 2025 and rng.random() < 0.5 else "used"
        odometer = rng.randint(0, 500) if condition == "new" else rng.randint(1000, 160000)
        new_price = rng.randint(minimum_price, maximum_price)
        age = max(0, REFERENCE_DATE_YEAR - year)
        depreciation = min(0.45, age * 0.055) if condition == "used" else 0
        price = max(1, round(new_price * (1 - depreciation)))
        adult = None if rng.random() < 0.12 else rng.randint(2, 5)
        child = None if rng.random() < 0.12 else rng.randint(2, 5)
        city = rng.choice(["pune", "mumbai", "delhi", "hyderabad", "chennai", "bengaluru"])
        features = rng.sample(sorted(ALLOWED_FEATURES), rng.randint(0, 3))
        variant = f"V{index % 4 + 1}"
        vehicles.append(
            Vehicle(
                f"veh_{index:06d}",
                make,
                model,
                variant,
                year,
                price,
                odometer,
                condition,
                body,
                fuel,
                transmission,
                seats,
                city,
                features,
                adult,
                child,
                f"Synthetic {seats}-seat {fuel} {transmission} {body} listing.",
                True,
                "synthetic_demo_v1",
                "demo_v1",
                year if adult is not None else None,
                None,
                f"{make} {model} {variant} {year}",
            )
        )
    return vehicles


def _payload(vehicles: list[Vehicle]) -> str:
    return json.dumps(
        [vehicle.__dict__ for vehicle in vehicles], sort_keys=True, separators=(",", ":")
    )


def _validate(vehicles: list[Vehicle]) -> None:
    ids = [vehicle.id for vehicle in vehicles]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate vehicle IDs")
    if not all(vehicle.is_synthetic for vehicle in vehicles):
        raise ValueError("seed must contain only synthetic vehicles")
    if any(len(vehicle.features) != len(set(vehicle.features)) for vehicle in vehicles):
        raise ValueError("duplicate feature on a vehicle")
    if any(not set(vehicle.features) <= ALLOWED_FEATURES for vehicle in vehicles):
        raise ValueError("unsupported feature in seed")


def seed_database(
    path: str, count: int = 300, seed: int = 42, reset: bool = False
) -> tuple[bool, str]:
    vehicles = build(count, seed)
    _validate(vehicles)
    payload = _payload(vehicles)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    version = f"seed-{seed}-{digest[:12]}"

    with closing(connect(path)) as connection:
        if reset:
            connection.executescript(
                "DROP TABLE IF EXISTS vehicle_features;"
                "DROP TABLE IF EXISTS vehicles;"
                "DROP TABLE IF EXISTS catalogue_metadata;"
            )
            connection.executescript(SCHEMA)
        existing_count = connection.execute("SELECT count(*) FROM vehicles").fetchone()[0]
        if existing_count:
            metadata = dict(connection.execute("SELECT key, value FROM catalogue_metadata"))
            if metadata.get("catalogue_version") == version and existing_count == count:
                return False, version
            raise ValueError("catalogue already contains different seed data; use --reset")
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "seed_version": SEED_VERSION,
            "seed_number": str(seed),
            "reference_date": REFERENCE_DATE,
            "record_count": str(count),
            "data_hash": digest,
            "catalogue_version": version,
        }
        try:
            connection.execute("BEGIN")
            for vehicle in vehicles:
                insert_vehicle(connection, vehicle)
            connection.executemany(
                "INSERT INTO catalogue_metadata(key, value) VALUES (?, ?)", metadata.items()
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return True, version


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--db", default="./data/catalogue.db")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    try:
        created, version = seed_database(args.db, args.count, args.seed, args.reset)
    except ValueError as exc:
        parser.error(str(exc))
    if created:
        print(f"seeded {args.count} vehicles; version {version}")
    else:
        print(f"catalogue already seeded; version {version}")


if __name__ == "__main__":
    main()
