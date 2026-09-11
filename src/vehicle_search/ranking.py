from .domain import Preference, Vehicle


def score(v: Vehicle, prefs: list[Preference]) -> float:
    vals = []
    for p in {x.code for x in prefs}:
        if p == "family":
            vals.append(
                0.5 * min(v.seats / 7, 1)
                + 0.25 * ("isofix" in v.features)
                + 0.25 * ("rear_ac" in v.features)
            )
        elif p == "safety":
            vals.append(((v.adult_safety_stars or 0) + (v.child_safety_stars or 0)) / 10)
        elif p == "affordability":
            vals.append(1 - min(v.price_inr / 5_000_000, 1))
        elif p == "low_odometer":
            vals.append(1 - min(v.odometer_km / 200_000, 1))
    return sum(vals) / len(vals) if vals else 0.0


def sort_key(v: Vehicle, prefs: list[Preference], sort: str | None):
    s = score(v, prefs)
    if sort == "price_desc":
        return (-v.price_inr, v.id)
    if sort == "odometer_asc":
        return (v.odometer_km, v.id)
    if sort == "year_desc":
        return (-v.year, v.id)
    if sort == "price_asc":
        return (v.price_inr, v.id)
    return (-s, v.price_inr, v.id)
