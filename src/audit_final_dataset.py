"""Independently audit the final pit-stop dataset and fail on integrity errors."""

from __future__ import annotations

import argparse
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline_utils import read_csv, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--final", type=Path, default=Path("data/processed/pit_stops_2023_2025.csv"))
    parser.add_argument("--pit-bridge", type=Path, default=Path("data/interim/pit_stop_bridge.csv"))
    parser.add_argument("--event-bridge", type=Path, default=Path("data/interim/event_bridge.csv"))
    parser.add_argument("--identity-bridge", type=Path, default=Path("data/interim/driver_event_bridge.csv"))
    parser.add_argument("--event-context", type=Path, default=Path("data/interim/event_context.csv"))
    parser.add_argument("--output", type=Path, default=Path("metadata/final_dataset_audit.json"))
    return parser.parse_args()


def add_check(checks: dict[str, bool], errors: list[str], name: str, passed: bool, detail: str) -> None:
    checks[name] = passed
    if not passed:
        errors.append(f"{name}: {detail}")


def main() -> None:
    args = parse_args()
    rows = read_csv(args.final)
    pit_rows = read_csv(args.pit_bridge)
    events = read_csv(args.event_bridge)
    identities = read_csv(args.identity_bridge)
    contexts = read_csv(args.event_context)
    errors: list[str] = []
    checks: dict[str, bool] = {}

    stop_ids = [row["stop_id"] for row in rows]
    add_check(checks, errors, "row_count_preserved", len(rows) == len(pit_rows) == 2225,
              f"final={len(rows)}, bridge={len(pit_rows)}")
    add_check(checks, errors, "stop_id_unique", len(stop_ids) == len(set(stop_ids)),
              "duplicate stop IDs found")
    add_check(checks, errors, "all_70_events_present", len({row["event_id"] for row in rows}) == len(events) == 70,
              "event coverage differs from event bridge")
    add_check(checks, errors, "years_are_2023_to_2025", {row["year"] for row in rows} == {"2023", "2024", "2025"},
              "unexpected year coverage")

    pit_by_id = {row["stop_id"]: row for row in pit_rows}
    shared_pit_columns = list(pit_rows[0])
    add_check(checks, errors, "pit_bridge_keys_preserved", set(stop_ids) == set(pit_by_id),
              "final and pit bridge keys differ")
    core_mismatches = sum(
        any(row[column] != pit_by_id[row["stop_id"]][column] for column in shared_pit_columns)
        for row in rows if row["stop_id"] in pit_by_id
    )
    add_check(checks, errors, "pit_bridge_values_preserved", core_mismatches == 0,
              f"{core_mismatches} final rows differ from pit bridge")

    identity_by_key = {(row["event_id"], row["driverId"]): row for row in identities}
    identity_mismatches = 0
    for row in rows:
        identity = identity_by_key.get((row["event_id"], row["driverId"]))
        if identity is None or any((
            row["driver_number"] != identity["kaggle_driver_number"],
            row["constructorId"] != identity["constructorId"],
            row["canonical_driver_name"] != identity["canonical_full_name"],
            row["canonical_team_name"] != identity["kaggle_team_name"],
        )):
            identity_mismatches += 1
    add_check(checks, errors, "identity_bridge_consistent", identity_mismatches == 0,
              f"{identity_mismatches} rows disagree with identity bridge")

    context_by_event = {row["event_id"]: row for row in contexts}
    context_fields = ["race_name", "race_date", "circuitId", "openf1_session_key"]
    context_mismatches = sum(
        any(row[field] != context_by_event[row["event_id"]][field] for field in context_fields)
        for row in rows
    )
    add_check(checks, errors, "event_context_consistent", context_mismatches == 0,
              f"{context_mismatches} rows disagree with event context")

    by_event: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_event[row["event_id"]].append(row)
    rank_errors = [
        event_id for event_id, group in by_event.items()
        if sorted(int(row["dhl_rank"]) for row in group) != list(range(1, len(group) + 1))
    ]
    add_check(checks, errors, "dhl_ranks_complete_within_event", not rank_errors,
              f"bad rank sequences: {rank_errors}")
    numeric_errors = sum(
        float(row["dhl_stop_seconds"]) <= 0 or int(row["lap"]) < 0 or int(row["dhl_rank"]) <= 0
        for row in rows
    )
    add_check(checks, errors, "primary_numeric_ranges_valid", numeric_errors == 0,
              f"{numeric_errors} invalid primary values")
    add_check(checks, errors, "all_race_results_joined",
              all(row["resultId"] and row["race_status"] and row["finish_position_order"] for row in rows),
              "missing required result fields")

    kaggle_unit_errors = sum(
        abs(float(row["kaggle_duration_seconds"]) * 1000 - int(row["kaggle_milliseconds"])) > 1e-9
        for row in rows if row["kaggle_exact_match"] == "True"
    )
    add_check(checks, errors, "kaggle_duration_units_consistent", kaggle_unit_errors == 0,
              f"{kaggle_unit_errors} millisecond conversions disagree")
    openf1_flag_errors = sum(
        (row["openf1_exact_match"] == "True") != bool(row["openf1_date_utc"])
        for row in rows
    )
    add_check(checks, errors, "openf1_match_flags_consistent", openf1_flag_errors == 0,
              f"{openf1_flag_errors} OpenF1 flags disagree with linked values")
    fastf1_flag_errors = sum(
        (row["fastf1_lap_exact_match"] == "True") != bool(row["fastf1_pit_in_time"])
        for row in rows
    )
    add_check(checks, errors, "fastf1_match_flags_consistent", fastf1_flag_errors == 0,
              f"{fastf1_flag_errors} FastF1 flags disagree with pit-in markers")

    # Detect accidental duplicate columns using their full value vectors. Constant
    # columns are ignored because different metadata fields can be constant by chance.
    vectors: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for column in rows[0]:
        vector = tuple(row[column] for row in rows)
        if len(set(vector)) > 1:
            vectors[vector].append(column)
    duplicate_column_groups = [columns for columns in vectors.values() if len(columns) > 1]
    add_check(checks, errors, "no_duplicate_data_columns", not duplicate_column_groups,
              f"identical columns: {duplicate_column_groups}")

    nonfinite_values = 0
    numeric_columns = (
        "dhl_stop_seconds", "kaggle_duration_seconds", "openf1_lane_duration",
        "openf1_stop_duration", "race_points", "fastest_lap_speed",
    )
    for row in rows:
        for column in numeric_columns:
            if row[column] and not math.isfinite(float(row[column])):
                nonfinite_values += 1
    add_check(checks, errors, "no_nonfinite_numeric_values", nonfinite_values == 0,
              f"{nonfinite_values} NaN or infinite values")
    sentinel_values = sum(value == "\\N" for row in rows for value in row.values())
    add_check(checks, errors, "source_missing_sentinels_normalized", sentinel_values == 0,
              f"{sentinel_values} source \\N sentinels remain")

    # Re-read raw DHL rows and compare the primary values independently.
    event_lookup = {row["event_id"]: row for row in events}
    raw_primary: dict[str, tuple[str, str, str, str, str]] = {}
    for event_id, event in event_lookup.items():
        raw_path = args.data_dir / "raw" / "dhl" / event["dhl_source_path"]
        for raw0 in read_csv(raw_path, delimiter="\t"):
            raw = {key.strip(): value.strip() for key, value in raw0.items()}
            stop_id = f"{event_id}-DHL-{int(raw['Pos.']):03d}"
            raw_primary[stop_id] = (
                raw["Driver"], raw["Team"], raw["Lap"], raw["Time (sec)"], raw["Points"]
            )
    raw_mismatches = 0
    for row in rows:
        expected = raw_primary.get(row["stop_id"])
        actual = (
            row["dhl_driver_name"], row["dhl_team_name"], row["lap"],
            f"{float(row['dhl_stop_seconds']):.2f}", row["dhl_points"],
        )
        normalized_expected = None if expected is None else (
            expected[0], expected[1], str(int(expected[2])), f"{float(expected[3]):.2f}",
            "" if expected[4] == "" else str(float(expected[4])),
        )
        normalized_actual = (
            actual[0], actual[1], str(int(actual[2])), actual[3],
            "" if actual[4] == "" else str(float(actual[4])),
        )
        if normalized_expected != normalized_actual:
            raw_mismatches += 1
    add_check(checks, errors, "raw_dhl_values_preserved", raw_mismatches == 0,
              f"{raw_mismatches} rows differ from raw DHL files")

    warnings: list[dict[str, Any]] = []
    def warn(code: str, count: int, explanation: str) -> None:
        if count:
            warnings.append({"code": code, "count": count, "explanation": explanation})

    warn("missing_dhl_points", sum(not row["dhl_points"] for row in rows),
         "The publisher left these award-points cells blank; they remain missing.")
    warn("lap_zero", sum(row["lap"] == "0" for row in rows),
         "DHL supplied lap 0; its meaning is not reinterpreted.")
    warn("no_exact_kaggle_stop", sum(row["kaggle_exact_match"] == "False" for row in rows),
         "No record shared the exact event, driver, and lap key; no nearest-lap guess was made.")
    warn("no_exact_openf1_stop", sum(row["openf1_exact_match"] == "False" for row in rows),
         "This includes races whose saved OpenF1 pit response is empty.")
    warn("openf1_lane_duration_at_least_300_seconds",
         sum(row["openf1_lane_duration_under_300_seconds"] == "False" for row in rows),
         "Retained and flagged as published; excluded from no rows automatically.")
    warn("openf1_stop_duration_missing", sum(not row["openf1_stop_duration"] for row in rows),
         "OpenF1 does not provide stationary stop_duration consistently across these years.")
    warn("fastf1_lap_unavailable", sum(row["fastf1_lap_exact_match"] == "False" for row in rows),
         "FastF1 raw sessions are saved for only three races.")
    warn("race_grid_missing", sum(not row["race_grid_position"] for row in rows),
         "The Kaggle results source codes these grid values as missing.")
    warn("finish_position_missing", sum(not row["finish_position"] for row in rows),
         "The Kaggle results source has no numeric classified position for these results.")

    report = {
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": args.final.as_posix(), "status": "PASS" if not errors else "FAIL",
        "rows": len(rows), "columns": len(rows[0]), "events": len(by_event),
        "checks_passed": sum(checks.values()), "checks_total": len(checks),
        "checks": checks, "errors": errors, "warnings": warnings,
        "match_counts": {
            "kaggle_exact": sum(row["kaggle_exact_match"] == "True" for row in rows),
            "openf1_exact": sum(row["openf1_exact_match"] == "True" for row in rows),
            "fastf1_lap_exact": sum(row["fastf1_lap_exact_match"] == "True" for row in rows),
        },
        "year_rows": dict(sorted(Counter(row["year"] for row in rows).items())),
    }
    write_json(args.output, report)
    print(f"Final dataset audit: {report['status']}")
    print(f"Checks passed: {report['checks_passed']}/{report['checks_total']}")
    print(f"Warnings documented: {len(warnings)}")
    if errors:
        raise SystemExit("Final dataset audit failed: " + "; ".join(errors))


if __name__ == "__main__":
    main()
