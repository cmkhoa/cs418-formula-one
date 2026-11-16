"""Build one canonical row per DHL-ranked pit stop and link exact source records."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline_utils import as_float, as_int, normalize, read_csv, read_json, write_csv, write_json


COLUMNS = (
    "stop_id", "event_id", "year", "round", "raceId", "driverId",
    "driver_ref", "canonical_driver_name", "driver_number", "constructorId",
    "constructor_ref", "canonical_team_name", "lap", "dhl_rank",
    "dhl_driver_name", "dhl_team_name", "dhl_stop_seconds", "dhl_points",
    "kaggle_exact_match", "kaggle_stop_number", "kaggle_time_of_day",
    "kaggle_duration_text", "kaggle_duration_seconds", "kaggle_milliseconds",
    "openf1_source_has_pit_rows", "openf1_exact_match", "openf1_date_utc",
    "openf1_lane_duration", "openf1_stop_duration",
    "openf1_lane_duration_under_300_seconds",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--event-bridge", type=Path, default=Path("data/interim/event_bridge.csv"))
    parser.add_argument("--identity-bridge", type=Path, default=Path("data/interim/driver_event_bridge.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/interim/pit_stop_bridge.csv"))
    parser.add_argument("--manifest", type=Path, default=Path("metadata/pit_stop_bridge_manifest.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    events = read_csv(args.event_bridge)
    identities = read_csv(args.identity_bridge)
    event_by_race = {row["raceId"]: row for row in events}

    identity_by_dhl_label: dict[tuple[str, str], dict[str, str]] = {}
    for row in identities:
        for label in row["dhl_driver_name"].split("|"):
            if not label:
                continue
            key = (row["event_id"], normalize(label))
            if key in identity_by_dhl_label:
                raise ValueError(f"Ambiguous DHL identity label: {key}")
            identity_by_dhl_label[key] = row

    kaggle_pits: dict[tuple[str, str, int], list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(args.data_dir / "pit_stops.csv"):
        event = event_by_race.get(row["raceId"])
        if event:
            kaggle_pits[(event["event_id"], row["driverId"], int(row["lap"]))].append(row)

    duplicate_kaggle_keys = [key for key, rows in kaggle_pits.items() if len(rows) != 1]
    if duplicate_kaggle_keys:
        raise ValueError(f"Non-unique Kaggle pit keys: {duplicate_kaggle_keys[:10]}")

    output: list[dict[str, Any]] = []
    source_dhl_rows = 0
    openf1_source_events_with_rows = 0
    for event in events:
        dhl_path = args.data_dir / "raw" / "dhl" / event["dhl_source_path"]
        dhl_rows = [
            {key.strip(): value.strip() for key, value in row.items()}
            for row in read_csv(dhl_path, delimiter="\t")
        ]
        source_dhl_rows += len(dhl_rows)

        openf1_path = (
            args.data_dir / "raw" / "openf1" / event["year"]
            / event["openf1_session_key"] / "pit.json"
        )
        openf1_rows = read_json(openf1_path)
        openf1_source_events_with_rows += bool(openf1_rows)
        if any(
            as_float(row.get("pit_duration")) != as_float(row.get("lane_duration"))
            for row in openf1_rows
        ):
            raise ValueError(
                f"OpenF1 pit_duration no longer duplicates lane_duration in {event['event_id']}; "
                "the omitted field must be reconsidered"
            )
        openf1_by_key: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
        for row in openf1_rows:
            openf1_by_key[(str(row["driver_number"]), int(row["lap_number"]))].append(row)
        duplicate_openf1_keys = [key for key, rows in openf1_by_key.items() if len(rows) != 1]
        if duplicate_openf1_keys:
            raise ValueError(f"Non-unique OpenF1 pit keys for {event['event_id']}: {duplicate_openf1_keys}")

        ranks = [int(row["Pos."]) for row in dhl_rows]
        if len(ranks) != len(set(ranks)):
            raise ValueError(f"Duplicate DHL rank in {event['event_id']}")

        for dhl in sorted(dhl_rows, key=lambda row: int(row["Pos."])):
            identity_key = (event["event_id"], normalize(dhl["Driver"]))
            if identity_key not in identity_by_dhl_label:
                raise ValueError(f"Unmatched DHL driver: {identity_key}")
            identity = identity_by_dhl_label[identity_key]
            lap = int(dhl["Lap"])
            kaggle_matches = kaggle_pits.get((event["event_id"], identity["driverId"], lap), [])
            openf1_matches = openf1_by_key.get((identity["kaggle_driver_number"], lap), [])
            kaggle = kaggle_matches[0] if kaggle_matches else None
            openf1 = openf1_matches[0] if openf1_matches else None
            lane_duration = as_float(openf1.get("lane_duration")) if openf1 else None
            rank = int(dhl["Pos."])
            output.append({
                "stop_id": f"{event['event_id']}-DHL-{rank:03d}",
                "event_id": event["event_id"], "year": int(event["year"]),
                "round": int(event["round"]), "raceId": int(event["raceId"]),
                "driverId": int(identity["driverId"]), "driver_ref": identity["driver_ref"],
                "canonical_driver_name": identity["canonical_full_name"],
                "driver_number": identity["kaggle_driver_number"],
                "constructorId": int(identity["constructorId"]),
                "constructor_ref": identity["constructor_ref"],
                "canonical_team_name": identity["kaggle_team_name"], "lap": lap,
                "dhl_rank": rank, "dhl_driver_name": dhl["Driver"],
                "dhl_team_name": dhl["Team"], "dhl_stop_seconds": float(dhl["Time (sec)"]),
                "dhl_points": as_float(dhl["Points"]) if dhl["Points"] else "",
                "kaggle_exact_match": kaggle is not None,
                "kaggle_stop_number": as_int(kaggle.get("stop")) if kaggle else "",
                "kaggle_time_of_day": kaggle["time"] if kaggle else "",
                "kaggle_duration_text": kaggle["duration"] if kaggle else "",
                "kaggle_duration_seconds": (as_float(kaggle["milliseconds"]) / 1000 if kaggle else ""),
                "kaggle_milliseconds": as_int(kaggle.get("milliseconds")) if kaggle else "",
                "openf1_source_has_pit_rows": bool(openf1_rows),
                "openf1_exact_match": openf1 is not None,
                "openf1_date_utc": openf1.get("date", "") if openf1 else "",
                "openf1_lane_duration": lane_duration if lane_duration is not None else "",
                "openf1_stop_duration": as_float(openf1.get("stop_duration")) if openf1 else "",
                "openf1_lane_duration_under_300_seconds": (lane_duration < 300 if lane_duration is not None else ""),
            })

    if len(output) != source_dhl_rows:
        raise ValueError("DHL row count changed while building pit-stop bridge")
    stop_counts = Counter(row["stop_id"] for row in output)
    if any(count != 1 for count in stop_counts.values()):
        raise ValueError("Duplicate stop_id values")

    write_csv(args.output, COLUMNS, output)
    manifest = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_file": args.output.as_posix(), "primary_unit": "one DHL-ranked pit stop",
        "rows": len(output), "events": len({row["event_id"] for row in output}),
        "unique_stop_ids": len(stop_counts) == len(output),
        "kaggle_exact_matches": sum(row["kaggle_exact_match"] for row in output),
        "kaggle_unmatched": sum(not row["kaggle_exact_match"] for row in output),
        "openf1_source_events_with_pit_rows": openf1_source_events_with_rows,
        "openf1_exact_matches": sum(row["openf1_exact_match"] for row in output),
        "openf1_unmatched": sum(not row["openf1_exact_match"] for row in output),
        "openf1_matched_lane_durations_at_least_300_seconds": sum(
            row["openf1_lane_duration_under_300_seconds"] is False for row in output
        ),
        "matching_rule": "exact event, canonical driver, and lap; no fuzzy or nearest-lap matches",
        "redundant_field_omitted": (
            "OpenF1 pit_duration is identical to lane_duration in every saved raw pit row, "
            "so only lane_duration is carried forward."
        ),
        "columns": list(COLUMNS),
    }
    write_json(args.manifest, manifest)
    print(f"Pit-stop bridge rows: {len(output)}")
    print(f"Kaggle exact matches: {manifest['kaggle_exact_matches']}/{len(output)}")
    print(f"OpenF1 exact matches: {manifest['openf1_exact_matches']}/{len(output)}")


if __name__ == "__main__":
    main()
