"""Assemble the analysis-ready pit-stop dataset from the verified bridge tables."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline_utils import as_float, as_int, read_csv, write_csv, write_json


RESULT_COLUMNS = (
    "resultId", "race_grid_position", "finish_position", "finish_position_text",
    "finish_position_order", "grid_minus_finish_order", "race_points",
    "race_laps_completed", "race_time", "race_milliseconds", "fastest_lap_number",
    "fastest_lap_rank", "fastest_lap_time", "fastest_lap_speed", "race_status",
)
FASTF1_COLUMNS = (
    "fastf1_lap_exact_match", "fastf1_lap_time", "fastf1_stint",
    "fastf1_compound", "fastf1_tyre_life", "fastf1_fresh_tyre",
    "fastf1_track_status", "fastf1_is_accurate", "fastf1_position_on_lap",
    "fastf1_pit_in_time", "fastf1_pit_out_time",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--event-bridge", type=Path, default=Path("data/interim/event_bridge.csv"))
    parser.add_argument("--pit-bridge", type=Path, default=Path("data/interim/pit_stop_bridge.csv"))
    parser.add_argument("--event-context", type=Path, default=Path("data/interim/event_context.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/pit_stops_2023_2025.csv"))
    parser.add_argument("--manifest", type=Path, default=Path("metadata/final_dataset_manifest.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    events = read_csv(args.event_bridge)
    pit_rows = read_csv(args.pit_bridge)
    context_rows = read_csv(args.event_context)
    context_by_event = {row["event_id"]: row for row in context_rows}
    if len(context_by_event) != len(context_rows):
        raise ValueError("Duplicate event context keys")

    event_by_race = {row["raceId"]: row for row in events}
    selected_results = [
        row for row in read_csv(args.data_dir / "results.csv") if row["raceId"] in event_by_race
    ]
    result_by_key = {(row["raceId"], row["driverId"]): row for row in selected_results}
    if len(result_by_key) != len(selected_results):
        raise ValueError("Duplicate Kaggle race/driver result keys")
    statuses = {row["statusId"]: row["status"] for row in read_csv(args.data_dir / "status.csv")}

    fastf1_laps: dict[tuple[str, str, int], dict[str, str]] = {}
    for event in events:
        if event["fastf1_available"] != "True":
            continue
        for lap in read_csv(Path(event["fastf1_source_directory"]) / "laps.csv"):
            lap_number = as_int(lap.get("LapNumber"))
            if lap_number is None:
                continue
            key = (event["event_id"], lap["DriverNumber"], lap_number)
            if key in fastf1_laps:
                raise ValueError(f"Duplicate FastF1 event/driver/lap key: {key}")
            fastf1_laps[key] = lap

    pit_columns = tuple(pit_rows[0].keys())
    repeated_context = {"event_id", "year", "round", "raceId"}
    context_columns = tuple(key for key in context_rows[0] if key not in repeated_context)
    columns = pit_columns + context_columns + RESULT_COLUMNS + FASTF1_COLUMNS

    output: list[dict[str, Any]] = []
    for pit in pit_rows:
        context = context_by_event.get(pit["event_id"])
        if context is None:
            raise ValueError(f"Missing event context for {pit['event_id']}")
        result = result_by_key.get((pit["raceId"], pit["driverId"]))
        if result is None:
            raise ValueError(f"Missing race result for {pit['stop_id']}")
        grid = as_int(result["grid"])
        finish_order = int(result["positionOrder"])
        lap_key = (pit["event_id"], pit["driver_number"], int(pit["lap"]))
        fastf1 = fastf1_laps.get(lap_key)

        row: dict[str, Any] = dict(pit)
        row.update({key: context[key] for key in context_columns})
        row.update({
            "resultId": int(result["resultId"]),
            "race_grid_position": grid if grid is not None else "",
            "finish_position": as_int(result["position"]),
            "finish_position_text": result["positionText"],
            "finish_position_order": finish_order,
            "grid_minus_finish_order": (
                grid - finish_order if grid is not None and grid > 0 else ""
            ),
            "race_points": float(result["points"]),
            "race_laps_completed": int(result["laps"]),
            "race_time": result["time"] if result["time"] != "\\N" else "",
            "race_milliseconds": as_int(result["milliseconds"]),
            "fastest_lap_number": as_int(result["fastestLap"]),
            "fastest_lap_rank": as_int(result["rank"]),
            "fastest_lap_time": result["fastestLapTime"] if result["fastestLapTime"] != "\\N" else "",
            "fastest_lap_speed": as_float(result["fastestLapSpeed"]),
            "race_status": statuses[result["statusId"]],
            "fastf1_lap_exact_match": fastf1 is not None,
            "fastf1_lap_time": fastf1["LapTime"] if fastf1 else "",
            "fastf1_stint": as_int(fastf1.get("Stint")) if fastf1 else "",
            "fastf1_compound": fastf1["Compound"] if fastf1 else "",
            "fastf1_tyre_life": as_float(fastf1.get("TyreLife")) if fastf1 else "",
            "fastf1_fresh_tyre": fastf1["FreshTyre"] if fastf1 else "",
            "fastf1_track_status": fastf1["TrackStatus"] if fastf1 else "",
            "fastf1_is_accurate": fastf1["IsAccurate"] if fastf1 else "",
            "fastf1_position_on_lap": as_int(fastf1.get("Position")) if fastf1 else "",
            "fastf1_pit_in_time": fastf1["PitInTime"] if fastf1 else "",
            "fastf1_pit_out_time": fastf1["PitOutTime"] if fastf1 else "",
        })
        output.append(row)

    if len(output) != len(pit_rows):
        raise ValueError("Final join changed the number of pit-stop rows")
    if len({row["stop_id"] for row in output}) != len(output):
        raise ValueError("Final dataset has duplicate stop IDs")

    write_csv(args.output, columns, output)
    manifest = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_file": args.output.as_posix(), "primary_unit": "one DHL-ranked pit stop",
        "rows": len(output), "columns": len(columns),
        "events": len({row["event_id"] for row in output}),
        "drivers": len({row["driverId"] for row in output}),
        "constructors": len({row["constructorId"] for row in output}),
        "year_rows": dict(sorted(Counter(row["year"] for row in output).items())),
        "unique_stop_ids": True, "race_result_matches": len(output),
        "event_context_matches": len(output),
        "fastf1_lap_exact_matches": sum(row["fastf1_lap_exact_match"] for row in output),
        "fastf1_rows_with_pit_in_marker": sum(bool(row["fastf1_pit_in_time"]) for row in output),
        "field_count": len(columns), "column_names": list(columns),
    }
    write_json(args.manifest, manifest)
    print(f"Final dataset rows: {len(output)}")
    print(f"Final dataset columns: {len(columns)}")
    print(f"FastF1 exact lap matches: {manifest['fastf1_lap_exact_matches']}")


if __name__ == "__main__":
    main()
