import csv
import math
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 20261201
SEEDS_DIR = Path(__file__).parent / "dbt" / "seeds"
START = date(2025, 11, 1)
END = date(2026, 10, 31)

STORES = [
    ("OR-PDX-01", "Pearl District", "Portland", "Oregon", "2019-03-04"),
    ("OR-PDX-02", "Hawthorne", "Portland", "Oregon", "2020-06-15"),
    ("OR-EUG-01", "Fifth Street", "Eugene", "Oregon", "2021-02-01"),
    ("OR-SLM-01", "Court Street", "Salem", "Oregon", "2022-09-12"),
    ("OR-BND-01", "Old Mill", "Bend", "Oregon", "2023-05-20"),
    ("WA-SEA-01", "Capitol Hill", "Seattle", "Washington", "2018-11-01"),
    ("WA-SEA-02", "Ballard", "Seattle", "Washington", "2019-08-19"),
    ("WA-SEA-03", "Fremont", "Seattle", "Washington", "2021-04-05"),
    ("WA-TAC-01", "Stadium District", "Tacoma", "Washington", "2022-01-10"),
    ("WA-SPO-01", "Riverfront", "Spokane", "Washington", "2023-03-27"),
    ("WA-OLY-01", "Capitol Way", "Olympia", "Washington", "2024-07-08"),
    ("CA-SFO-01", "Mission", "San Francisco", "California", "2020-10-05"),
    ("CA-OAK-01", "Temescal", "Oakland", "California", "2021-11-15"),
    ("CA-SAC-01", "Midtown", "Sacramento", "California", "2023-02-13"),
    ("CA-ARC-01", "Plaza", "Arcata", "California", "2024-04-22"),
]

# October 2026 targets match the post: Emma's Oregon is $680,000, the company
# total is $2.70M, so Washington plus California is $2,020,000.
OCTOBER_TARGETS = {"Oregon": 680_000, "Washington": 1_150_000, "California": 870_000}

REGION_ACCESS = [
    ("emma", "Oregon"),
    ("jake", "Oregon"),
    ("jake", "Washington"),
    ("jake", "California"),
    ("dana", "Washington"),
    ("dana", "California"),
]

WEEKDAY_FACTOR = [0.92, 0.95, 0.97, 1.0, 1.06, 1.12, 0.98]


def seasonal(day: date) -> float:
    return 1 + 0.12 * math.cos(2 * math.pi * (day.timetuple().tm_yday - 15) / 365)


def allocate_cents(raw: list[float], target_cents: int) -> list[int]:
    scale = target_cents / sum(raw)
    scaled = [r * scale for r in raw]
    floors = [math.floor(s) for s in scaled]
    remainder = target_cents - sum(floors)
    order = sorted(range(len(raw)), key=lambda i: scaled[i] - floors[i], reverse=True)
    for i in order[:remainder]:
        floors[i] += 1
    return floors


def days() -> list[date]:
    return [START + timedelta(n) for n in range((END - START).days + 1)]


def generate_sales(rng: random.Random) -> list[dict]:
    stores_in = {r: [s for s in STORES if s[3] == r] for r in OCTOBER_TARGETS}
    rows = []
    for region, stores in stores_in.items():
        base = OCTOBER_TARGETS[region] / 31 / len(stores)
        store_weight = {s[0]: rng.uniform(0.8, 1.2) for s in stores}
        region_rows = []
        for day in days():
            for store in stores:
                raw = (
                    base
                    * store_weight[store[0]]
                    * WEEKDAY_FACTOR[day.weekday()]
                    * seasonal(day)
                    * rng.uniform(0.9, 1.1)
                )
                region_rows.append({"sale_date": day, "store_id": store[0], "raw": raw})
        october = [
            r
            for r in region_rows
            if (r["sale_date"].year, r["sale_date"].month) == (2026, 10)
        ]
        cents = allocate_cents(
            [r["raw"] for r in october], OCTOBER_TARGETS[region] * 100
        )
        for row, c in zip(october, cents, strict=True):
            row["cents"] = c
        for row in region_rows:
            cents_value = row.get("cents", round(row["raw"] * 100))
            ticket = rng.uniform(6.8, 8.2)
            rows.append(
                {
                    "sale_date": row["sale_date"].isoformat(),
                    "store_id": row["store_id"],
                    "revenue_usd": f"{cents_value / 100:.2f}",
                    "transactions": max(1, round(cents_value / 100 / ticket)),
                }
            )
    return sorted(rows, key=lambda r: (r["sale_date"], r["store_id"]))


def write_csv(name: str, header: list[str], rows: list) -> None:
    with (SEEDS_DIR / name).open("w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow([row[h] for h in header] if isinstance(row, dict) else row)


def main() -> None:
    rng = random.Random(SEED)
    SEEDS_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(
        "raw_stores.csv",
        ["store_id", "store_name", "city", "region", "opened_on"],
        STORES,
    )
    write_csv(
        "raw_store_sales.csv",
        ["sale_date", "store_id", "revenue_usd", "transactions"],
        generate_sales(rng),
    )
    write_csv("raw_region_access.csv", ["user_name", "region"], REGION_ACCESS)


if __name__ == "__main__":
    main()
