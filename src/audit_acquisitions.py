"""Audit steps 1–5 for coverage, duplicate keys, and redundant storage."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable


CANONICAL_EVENTS = Path("data/interim/kaggle_events_2023_2025.csv")
DHL_MANIFEST = Path("metadata/dhl_manifest.json")
FASTF1_MANIFEST = Path("metadata/fastf1_manifest.json")
OPENF1_MANIFEST = Path("metadata/openf1_manifest.json")
OUTPUT = Path("metadata/acquisition_audit.json")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def duplicate_row_count(rows: Iterable[dict[str, Any]]) -> int:
    counts = Counter(json.dumps(row, sort_keys=True) for row in rows)
    return sum(count - 1 for count in counts.values() if count > 1)


def duplicate_key_count(rows: Iterable[dict[str, Any]], keys: tuple[str, ...]) -> int:
    counts = Counter(tuple(str(row.get(key, "")) for key in keys) for row in rows)
    return sum(count - 1 for count in counts.values() if count > 1)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    errors: list[str] = []
    warnings: list[str] = []
    observations: list[str] = []
    canonical = read_csv(CANONICAL_EVENTS)
    canonical_by_id = {row["event_id"]: row for row in canonical}
    canonical_by_date = {(row["year"], row["race_date"]): row for row in canonical}
    canonical_by_year: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in canonical:
        canonical_by_year[row["year"]].append(row)
    canonical_keys = {(int(row["year"]), int(row["round"])) for row in canonical}

    if len(canonical_by_id) != len(canonical):
        errors.append("Canonical event_id values are not unique")

    # DHL coverage and keys
    dhl = read_json(DHL_MANIFEST)
    dhl_keys = {
        (int(profile["year"]), int(profile["round"]))
        for profile in dhl["files"].values()
    }
    if dhl_keys != canonical_keys:
        errors.append(
            f"DHL event-key mismatch: canonical-only={sorted(canonical_keys-dhl_keys)}, "
            f"DHL-only={sorted(dhl_keys-canonical_keys)}"
        )

    # OpenF1 event/date mapping and endpoint keys
    openf1 = read_json(OPENF1_MANIFEST)
    openf1_event_map: dict[str, int] = {}
    unmapped_openf1: list[int] = []
    openf1_result_counts: dict[str, int] = {}
    openf1_pit_counts: dict[str, int] = {}
    openf1_duplicate_counts = Counter()
    openf1_empty_pit_events: list[str] = []

    for session_key_text, profile in openf1["sessions"].items():
        session_key = int(session_key_text)
        metadata = profile["session_metadata"]
        session_date_text = str(metadata["date_start"])[:10]
        year = str(metadata["year"])
        canonical_event = canonical_by_date.get((year, session_date_text))
        if canonical_event is None:
            openf1_date = datetime.fromisoformat(
                str(metadata["date_start"]).replace("Z", "+00:00")
            ).date()
            nearby = [
                row
                for row in canonical_by_year[year]
                if abs((date.fromisoformat(row["race_date"]) - openf1_date).days) <= 1
            ]
            if len(nearby) == 1:
                canonical_event = nearby[0]
        if canonical_event is None:
            unmapped_openf1.append(session_key)
            continue
        event_id = canonical_event["event_id"]
        if event_id in openf1_event_map:
            errors.append(f"Multiple OpenF1 race sessions map to {event_id}")
        openf1_event_map[event_id] = session_key
        directory = Path("data/raw/openf1") / metadata["year"].__str__() / str(session_key)

        endpoint_rows = {
            endpoint: read_json(directory / f"{endpoint}.json")
            for endpoint in (
                "drivers",
                "pit",
                "weather",
                "race_control",
                "session_result",
            )
        }
        openf1_result_counts[event_id] = len(endpoint_rows["session_result"])
        openf1_pit_counts[event_id] = len(endpoint_rows["pit"])
        if not endpoint_rows["pit"]:
            openf1_empty_pit_events.append(event_id)

        openf1_duplicate_counts["drivers_driver_number"] += duplicate_key_count(
            endpoint_rows["drivers"], ("driver_number",)
        )
        openf1_duplicate_counts["results_driver_number"] += duplicate_key_count(
            endpoint_rows["session_result"], ("driver_number",)
        )
        openf1_duplicate_counts["pit_driver_lap"] += duplicate_key_count(
            endpoint_rows["pit"], ("driver_number", "lap_number")
        )
        openf1_duplicate_counts["weather_date"] += duplicate_key_count(
            endpoint_rows["weather"], ("date",)
        )
        for endpoint, rows in endpoint_rows.items():
            openf1_duplicate_counts[f"{endpoint}_exact_rows"] += duplicate_row_count(rows)

    if unmapped_openf1:
        errors.append(f"Unmapped OpenF1 session keys: {unmapped_openf1}")
    missing_openf1_events = sorted(set(canonical_by_id) - set(openf1_event_map))
    if missing_openf1_events:
        errors.append(f"Canonical events missing OpenF1 sessions: {missing_openf1_events}")
    if openf1_duplicate_counts["drivers_driver_number"]:
        errors.append("OpenF1 driver_number is duplicated within one or more races")
    if openf1_duplicate_counts["results_driver_number"]:
        errors.append("OpenF1 session-result driver_number is duplicated within races")
    if openf1_duplicate_counts["weather_date"]:
        errors.append("OpenF1 weather timestamps are duplicated within races")
    if openf1_duplicate_counts["pit_driver_lap"]:
        warnings.append(
            f"OpenF1 has {openf1_duplicate_counts['pit_driver_lap']} extra rows on "
            "driver/lap keys; stop matching will need an occurrence index"
        )

    result_count_differences = []
    for event_id, canonical_event in canonical_by_id.items():
        kaggle_count = int(canonical_event["result_rows"])
        openf1_count = openf1_result_counts.get(event_id, 0)
        if kaggle_count != openf1_count:
            result_count_differences.append(
                {
                    "event_id": event_id,
                    "kaggle_results": kaggle_count,
                    "openf1_results": openf1_count,
                }
            )
    if result_count_differences:
        warnings.append(
            f"Kaggle/OpenF1 result row counts differ for "
            f"{len(result_count_differences)} events"
        )

    # FastF1 exported subset and key checks
    fastf1 = read_json(FASTF1_MANIFEST)
    fastf1_event_ids = set(fastf1["events"])
    invalid_fastf1_events = sorted(fastf1_event_ids - set(canonical_by_id))
    if invalid_fastf1_events:
        errors.append(f"FastF1 exports outside canonical scope: {invalid_fastf1_events}")
    fastf1_duplicate_lap_keys = 0
    fastf1_duplicate_result_drivers = 0
    fastf1_pit_in_counts: dict[str, int] = {}
    for event_id in sorted(fastf1_event_ids):
        year = canonical_by_id[event_id]["year"]
        directory = Path("data/raw/fastf1") / year / event_id
        laps = read_csv(directory / "laps.csv")
        results = read_csv(directory / "results.csv")
        fastf1_duplicate_lap_keys += duplicate_key_count(
            laps, ("DriverNumber", "LapNumber")
        )
        fastf1_duplicate_result_drivers += duplicate_key_count(
            results, ("DriverNumber",)
        )
        fastf1_pit_in_counts[event_id] = sum(bool(row.get("PitInTime")) for row in laps)
    if fastf1_duplicate_lap_keys:
        errors.append(f"FastF1 has {fastf1_duplicate_lap_keys} duplicate driver/lap keys")
    if fastf1_duplicate_result_drivers:
        errors.append(
            f"FastF1 has {fastf1_duplicate_result_drivers} duplicate result-driver keys"
        )
    if len(fastf1_event_ids) < len(canonical):
        warnings.append(
            f"FastF1 selected exports cover only {len(fastf1_event_ids)}/{len(canonical)} events"
        )

    # Redundancy checks for mistakes discovered during implementation.
    redundant_kaggle_directory = Path("data/raw/kaggle").exists()
    redundant_openf1_session_files = sorted(
        str(path) for path in Path("data/raw/openf1").glob("*/*/session.json")
    )
    if redundant_kaggle_directory:
        errors.append("Duplicate Kaggle directory data/raw/kaggle still exists")
    if redundant_openf1_session_files:
        errors.append("OpenF1 session records are duplicated in per-event session.json files")

    # Find identical nonempty endpoint files; empty [] responses are expected.
    hashes: dict[str, list[str]] = defaultdict(list)
    for path in Path("data/raw/openf1").glob("*/*/*.json"):
        if path.stat().st_size > 4:
            hashes[file_hash(path)].append(str(path))
    duplicate_nonempty_openf1_files = [paths for paths in hashes.values() if len(paths) > 1]
    if duplicate_nonempty_openf1_files:
        warnings.append(
            f"Found {len(duplicate_nonempty_openf1_files)} groups of byte-identical "
            "nonempty OpenF1 endpoint files"
        )

    observations.append(
        "FastF1 transport cache and selected CSV exports have different roles; "
        "the cache is ignored and the CSVs are the stable analysis inputs."
    )
    observations.append(
        f"OpenF1 has empty pit responses for {len(openf1_empty_pit_events)} events."
    )

    report = {
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "observations": observations,
        "coverage": {
            "canonical_events": len(canonical),
            "dhl_events": len(dhl_keys),
            "openf1_events": len(openf1_event_map),
            "fastf1_events": len(fastf1_event_ids),
        },
        "openf1": {
            "empty_pit_events": sorted(openf1_empty_pit_events),
            "duplicate_counts": dict(sorted(openf1_duplicate_counts.items())),
            "result_count_differences": result_count_differences,
        },
        "fastf1": {
            "complete_events": sorted(fastf1_event_ids),
            "incomplete_event_count": len(fastf1["incomplete_events"]),
            "pit_in_counts": fastf1_pit_in_counts,
            "duplicate_driver_lap_keys": fastf1_duplicate_lap_keys,
            "duplicate_result_driver_keys": fastf1_duplicate_result_drivers,
        },
        "redundancy": {
            "duplicate_kaggle_directory_exists": redundant_kaggle_directory,
            "per_event_openf1_session_files": redundant_openf1_session_files,
            "duplicate_nonempty_openf1_file_groups": duplicate_nonempty_openf1_files,
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Audit passed: {report['passed']}")
    print(f"Coverage: {report['coverage']}")
    print(f"Errors: {len(errors)}")
    print(f"Warnings: {len(warnings)}")
    for warning in warnings:
        print(f"  WARNING: {warning}")
    print(f"OpenF1 empty pit events: {sorted(openf1_empty_pit_events)}")
    print(f"Result-count differences: {result_count_differences}")
    print(f"Report: {OUTPUT}")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
