"""Acquire selected FastF1 race-session tables for canonical events.

Telemetry is intentionally disabled. For each event the script exports only the
lap, result, and weather columns needed for cross-source joining and later
analysis. FastF1's own cache is a transport cache; the selected CSV exports are
the stable project inputs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import fastf1
import pandas as pd


LAP_COLUMNS = (
    "Driver",
    "DriverNumber",
    "Team",
    "LapNumber",
    "Stint",
    "LapTime",
    "LapStartTime",
    "Time",
    "PitOutTime",
    "PitInTime",
    "Compound",
    "TyreLife",
    "FreshTyre",
    "TrackStatus",
    "IsAccurate",
    "Position",
)
RESULT_COLUMNS = (
    "DriverNumber",
    "BroadcastName",
    "Abbreviation",
    "DriverId",
    "TeamName",
    "TeamColor",
    "FirstName",
    "LastName",
    "FullName",
    "CountryCode",
    "Position",
    "ClassifiedPosition",
    "GridPosition",
    "Status",
    "Points",
    "Laps",
)
WEATHER_COLUMNS = (
    "Time",
    "AirTemp",
    "Humidity",
    "Pressure",
    "Rainfall",
    "TrackTemp",
    "WindDirection",
    "WindSpeed",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--events",
        type=Path,
        default=Path("data/interim/kaggle_events_2023_2025.csv"),
        help="Canonical event table.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/raw/fastf1"),
        help="Selected FastF1 export directory.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("fastf1_cache"),
        help="FastF1 transport cache directory.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("metadata/fastf1_manifest.json"),
        help="Acquisition manifest path.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Reload events that already have all expected exports.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use only FastF1's existing transport cache; make no network calls.",
    )
    return parser.parse_args()


def read_events(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def existing_complete(directory: Path) -> bool:
    return all(
        (directory / name).exists()
        for name in ("laps.csv", "results.csv", "weather.csv", "event.json")
    )


def select_columns(
    frame: pd.DataFrame, requested: tuple[str, ...], table_name: str
) -> tuple[pd.DataFrame, list[str]]:
    available = [column for column in requested if column in frame.columns]
    missing = [column for column in requested if column not in frame.columns]
    if not available:
        raise ValueError(f"FastF1 {table_name} has none of the requested columns")
    return frame.loc[:, available].copy(), missing


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def csv_profile(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        columns = next(reader)
        row_count = sum(1 for _ in reader)
    return {
        "rows": row_count,
        "columns": columns,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def event_profile(directory: Path) -> dict[str, object]:
    event = json.loads((directory / "event.json").read_text(encoding="utf-8"))
    return {
        **event,
        "tables": {
            name.removesuffix(".csv"): csv_profile(directory / name)
            for name in ("laps.csv", "results.csv", "weather.csv")
        },
    }


def main() -> None:
    args = parse_args()
    events = read_events(args.events)
    if not events:
        raise ValueError(f"No canonical events found in {args.events}")

    args.cache_dir.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(args.cache_dir.resolve()))
    if args.offline:
        fastf1.Cache.offline_mode(True)
    fastf1.set_log_level("WARNING")

    failures: dict[str, str] = {}
    for index, event in enumerate(events, start=1):
        event_id = event["event_id"]
        year = int(event["year"])
        round_number = int(event["round"])
        directory = args.output_dir / str(year) / event_id
        if existing_complete(directory) and not args.overwrite:
            print(f"[{index}/{len(events)}] {event_id}: cached export", flush=True)
            continue

        print(f"[{index}/{len(events)}] {event_id}: loading FastF1 race", flush=True)
        try:
            session = fastf1.get_session(year, round_number, "R")
            session.load(
                laps=True,
                telemetry=False,
                weather=True,
                messages=False,
            )
            laps, missing_lap_columns = select_columns(
                session.laps, LAP_COLUMNS, "laps"
            )
            results, missing_result_columns = select_columns(
                session.results, RESULT_COLUMNS, "results"
            )
            weather, missing_weather_columns = select_columns(
                session.weather_data, WEATHER_COLUMNS, "weather"
            )

            directory.mkdir(parents=True, exist_ok=True)
            laps.to_csv(directory / "laps.csv", index=False)
            results.to_csv(directory / "results.csv", index=False)
            weather.to_csv(directory / "weather.csv", index=False)
            event_metadata = {
                "event_id": event_id,
                "year": year,
                "round": round_number,
                "kaggle_raceId": int(event["raceId"]),
                "kaggle_race_name": event["race_name"],
                "fastf1_event_name": str(session.event.get("EventName", "")),
                "fastf1_official_event_name": str(
                    session.event.get("OfficialEventName", "")
                ),
                "fastf1_event_date": str(session.event.get("EventDate", "")),
                "fastf1_location": str(session.event.get("Location", "")),
                "fastf1_country": str(session.event.get("Country", "")),
                "fastf1_round": int(session.event.get("RoundNumber", round_number)),
                "session_name": str(session.name),
                "session_date": str(session.date),
                "fastf1_version": fastf1.__version__,
                "missing_requested_columns": {
                    "laps": missing_lap_columns,
                    "results": missing_result_columns,
                    "weather": missing_weather_columns,
                },
            }
            (directory / "event.json").write_text(
                json.dumps(event_metadata, indent=2) + "\n", encoding="utf-8"
            )
        except Exception as exc:  # continue so the manifest exposes all failures
            failures[event_id] = f"{type(exc).__name__}: {exc}"
            print(f"  FAILED: {failures[event_id]}", flush=True)

    profiles: dict[str, dict[str, object]] = {}
    incomplete_exports: list[str] = []
    for event in events:
        event_id = event["event_id"]
        directory = args.output_dir / event["year"] / event_id
        if existing_complete(directory):
            profiles[event_id] = event_profile(directory)
        else:
            incomplete_exports.append(event_id)

    round_mismatches = sorted(
        event_id
        for event_id, profile in profiles.items()
        if int(profile["round"]) != int(profile["fastf1_round"])
    )
    duplicate_event_ids = len(profiles) != len(set(profiles))
    manifest = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "fastf1_version": fastf1.__version__,
        "canonical_event_file": args.events.as_posix(),
        "selected_output_directory": args.output_dir.as_posix(),
        "transport_cache_directory": args.cache_dir.as_posix(),
        "offline_mode": args.offline,
        "expected_event_count": len(events),
        "complete_event_count": len(profiles),
        "incomplete_events": incomplete_exports,
        "failures": failures,
        "round_mismatches": round_mismatches,
        "duplicate_event_ids": duplicate_event_ids,
        "events": profiles,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"Complete FastF1 exports: {len(profiles)}/{len(events)}")
    print(f"Round mismatches: {len(round_mismatches)}")
    print(f"Incomplete events: {len(incomplete_exports)}")
    print(f"Manifest: {args.manifest}")
    if incomplete_exports:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
