"""Build the canonical Kaggle event table for the 2023–2025 analysis scope."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


NULL_TOKEN = r"\N"
DEFAULT_YEARS = (2023, 2024, 2025)
OUTPUT_COLUMNS = (
    "event_id",
    "raceId",
    "year",
    "round",
    "race_name",
    "race_date",
    "race_time",
    "race_url",
    "circuitId",
    "circuit_ref",
    "circuit_name",
    "circuit_location",
    "circuit_country",
    "circuit_latitude",
    "circuit_longitude",
    "circuit_altitude",
    "result_rows",
    "kaggle_pit_stop_rows",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Directory containing Kaggle CSV files (default: data).",
    )
    parser.add_argument(
        "--years",
        type=int,
        nargs="+",
        default=list(DEFAULT_YEARS),
        help="Seasons to include (default: 2023 2024 2025).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/interim/kaggle_events_2023_2025.csv"),
        help="Output CSV path.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("metadata/kaggle_event_table_manifest.json"),
        help="Validation manifest path.",
    )
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def source_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean(value: str | None) -> str:
    if value is None or value == NULL_TOKEN:
        return ""
    return value.strip()


def duplicate_values(values: list[str]) -> list[str]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def main() -> None:
    args = parse_args()
    years = sorted(set(args.years))
    races_path = args.data_dir / "races.csv"
    circuits_path = args.data_dir / "circuits.csv"
    results_path = args.data_dir / "results.csv"
    pit_stops_path = args.data_dir / "pit_stops.csv"

    races = [row for row in read_csv(races_path) if int(row["year"]) in years]
    circuits = read_csv(circuits_path)
    results = read_csv(results_path)
    pit_stops = read_csv(pit_stops_path)

    circuit_by_id = {row["circuitId"]: row for row in circuits}
    if len(circuit_by_id) != len(circuits):
        raise ValueError("circuits.csv contains duplicate circuitId values")

    result_counts = Counter(row["raceId"] for row in results)
    pit_stop_counts = Counter(row["raceId"] for row in pit_stops)
    output_rows: list[dict[str, str | int]] = []
    missing_circuit_ids: list[str] = []

    for race in sorted(races, key=lambda row: (int(row["year"]), int(row["round"]))):
        year = int(race["year"])
        round_number = int(race["round"])
        circuit = circuit_by_id.get(race["circuitId"])
        if circuit is None:
            missing_circuit_ids.append(race["circuitId"])
            continue

        output_rows.append(
            {
                "event_id": f"{year}-{round_number:02d}",
                "raceId": int(race["raceId"]),
                "year": year,
                "round": round_number,
                "race_name": clean(race["name"]),
                "race_date": clean(race["date"]),
                "race_time": clean(race["time"]),
                "race_url": clean(race["url"]),
                "circuitId": int(race["circuitId"]),
                "circuit_ref": clean(circuit["circuitRef"]),
                "circuit_name": clean(circuit["name"]),
                "circuit_location": clean(circuit["location"]),
                "circuit_country": clean(circuit["country"]),
                "circuit_latitude": clean(circuit["lat"]),
                "circuit_longitude": clean(circuit["lng"]),
                "circuit_altitude": clean(circuit["alt"]),
                "result_rows": result_counts[race["raceId"]],
                "kaggle_pit_stop_rows": pit_stop_counts[race["raceId"]],
            }
        )

    if missing_circuit_ids:
        raise ValueError(
            f"Races reference missing circuit IDs: {sorted(set(missing_circuit_ids))}"
        )

    duplicate_event_ids = duplicate_values([str(row["event_id"]) for row in output_rows])
    duplicate_race_ids = duplicate_values([str(row["raceId"]) for row in output_rows])
    if duplicate_event_ids or duplicate_race_ids:
        raise ValueError(
            f"Non-unique event keys: event_id={duplicate_event_ids}, "
            f"raceId={duplicate_race_ids}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(output_rows)

    events_by_year = Counter(int(row["year"]) for row in output_rows)
    missing_race_time = sum(not row["race_time"] for row in output_rows)
    events_without_results = [
        str(row["event_id"]) for row in output_rows if row["result_rows"] == 0
    ]
    events_without_pit_stops = [
        str(row["event_id"])
        for row in output_rows
        if row["kaggle_pit_stop_rows"] == 0
    ]

    manifest = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "years": years,
        "input_directory": args.data_dir.as_posix(),
        "output_file": args.output.as_posix(),
        "source_sha256": {
            "races.csv": source_hash(races_path),
            "circuits.csv": source_hash(circuits_path),
            "results.csv": source_hash(results_path),
            "pit_stops.csv": source_hash(pit_stops_path),
        },
        "event_count": len(output_rows),
        "events_by_year": {
            str(year): events_by_year.get(year, 0) for year in years
        },
        "event_id_unique": not duplicate_event_ids,
        "raceId_unique": not duplicate_race_ids,
        "missing_circuit_joins": len(missing_circuit_ids),
        "events_missing_race_time": missing_race_time,
        "events_without_results": events_without_results,
        "events_without_kaggle_pit_stops": events_without_pit_stops,
        "total_result_rows": sum(int(row["result_rows"]) for row in output_rows),
        "total_kaggle_pit_stop_rows": sum(
            int(row["kaggle_pit_stop_rows"]) for row in output_rows
        ),
        "columns": list(OUTPUT_COLUMNS),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"Built {len(output_rows)} canonical events at {args.output}")
    print(f"Events by year: {dict(sorted(events_by_year.items()))}")
    print(f"Events without results: {len(events_without_results)}")
    print(f"Events without Kaggle pit stops: {len(events_without_pit_stops)}")
    print(f"Missing race times: {missing_race_time}")
    print(f"Manifest: {args.manifest}")


if __name__ == "__main__":
    main()
