"""Build and validate the cross-source event bridge for 2023–2025."""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OUTPUT_COLUMNS = (
    "event_id",
    "year",
    "round",
    "raceId",
    "race_name",
    "race_date",
    "circuitId",
    "circuit_ref",
    "circuit_name",
    "circuit_location",
    "circuit_country",
    "dhl_available",
    "dhl_source_path",
    "dhl_stop_rows",
    "openf1_available",
    "openf1_match_method",
    "openf1_meeting_key",
    "openf1_session_key",
    "openf1_date_start_utc",
    "openf1_circuit_key",
    "openf1_circuit_name",
    "openf1_location",
    "openf1_country_code",
    "openf1_country_name",
    "fastf1_available",
    "fastf1_event_name",
    "fastf1_event_date",
    "fastf1_location",
    "fastf1_country",
    "fastf1_source_directory",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--canonical-events",
        type=Path,
        default=Path("data/interim/kaggle_events_2023_2025.csv"),
    )
    parser.add_argument(
        "--dhl-manifest",
        type=Path,
        default=Path("metadata/dhl_manifest.json"),
    )
    parser.add_argument(
        "--openf1-manifest",
        type=Path,
        default=Path("metadata/openf1_manifest.json"),
    )
    parser.add_argument(
        "--fastf1-manifest",
        type=Path,
        default=Path("metadata/fastf1_manifest.json"),
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        default=Path("metadata/event_bridge_overrides.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/interim/event_bridge.csv"),
    )
    parser.add_argument(
        "--review-output",
        type=Path,
        default=Path("data/interim/event_bridge_review.csv"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("metadata/event_bridge_manifest.json"),
    )
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(character for character in value if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def duplicate_values(values: list[str]) -> list[str]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def main() -> None:
    args = parse_args()
    canonical = read_csv(args.canonical_events)
    dhl_manifest = read_json(args.dhl_manifest)
    openf1_manifest = read_json(args.openf1_manifest)
    fastf1_manifest = read_json(args.fastf1_manifest)
    override_config = read_json(args.overrides)
    overrides = override_config.get("openf1_session_overrides", {})
    approved_name_differences = override_config.get("approved_name_differences", {})

    canonical_by_id = {row["event_id"]: row for row in canonical}
    if len(canonical_by_id) != len(canonical):
        raise ValueError("Canonical event_id values are not unique")

    dhl_by_event: dict[str, dict[str, Any]] = {}
    for profile in dhl_manifest["files"].values():
        event_id = f"{int(profile['year'])}-{int(profile['round']):02d}"
        if event_id in dhl_by_event:
            raise ValueError(f"Multiple DHL files map to {event_id}")
        dhl_by_event[event_id] = profile

    openf1_by_event: dict[str, dict[str, Any]] = {}
    openf1_match_method: dict[str, str] = {}
    used_override_keys: set[str] = set()
    unmatched_openf1: list[dict[str, Any]] = []
    canonical_by_exact_date = {
        (row["year"], row["race_date"]): row for row in canonical
    }
    for session_key, profile in openf1_manifest["sessions"].items():
        session = profile["session_metadata"]
        exact_key = (str(session["year"]), str(session["date_start"])[:10])
        event = canonical_by_exact_date.get(exact_key)
        method = "exact_date"
        if event is None:
            override = overrides.get(str(session_key))
            if override is not None:
                event = canonical_by_id.get(override["event_id"])
                if event is None:
                    raise ValueError(
                        f"Override for OpenF1 session {session_key} references unknown "
                        f"event {override['event_id']}"
                    )
                if int(event["year"]) != int(session["year"]):
                    raise ValueError(
                        f"Override year mismatch for OpenF1 session {session_key}"
                    )
                used_override_keys.add(str(session_key))
                method = "manual_override"
            else:
                unmatched_openf1.append(session)
                continue

        event_id = event["event_id"]
        if event_id in openf1_by_event:
            raise ValueError(f"Multiple OpenF1 race sessions map to {event_id}")
        openf1_by_event[event_id] = session
        openf1_match_method[event_id] = method

    unused_override_keys = sorted(set(overrides) - used_override_keys)
    if unused_override_keys:
        raise ValueError(f"Unused OpenF1 event overrides: {unused_override_keys}")
    if unmatched_openf1:
        raise ValueError(
            "OpenF1 sessions require manual review: "
            + ", ".join(str(row["session_key"]) for row in unmatched_openf1)
        )

    fastf1_by_event = fastf1_manifest["events"]
    rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, str]] = []
    for event in canonical:
        event_id = event["event_id"]
        dhl = dhl_by_event.get(event_id)
        openf1 = openf1_by_event.get(event_id)
        fastf1 = fastf1_by_event.get(event_id)
        if openf1 is None:
            raise ValueError(f"Canonical event has no OpenF1 mapping: {event_id}")

        match_method = openf1_match_method[event_id]
        if match_method == "manual_override":
            override = overrides[str(openf1["session_key"])]
            review_rows.append(
                {
                    "event_id": event_id,
                    "source": "OpenF1",
                    "source_key": str(openf1["session_key"]),
                    "review_status": "approved",
                    "reason": override["reason"],
                }
            )

        rows.append(
            {
                "event_id": event_id,
                "year": int(event["year"]),
                "round": int(event["round"]),
                "raceId": int(event["raceId"]),
                "race_name": event["race_name"],
                "race_date": event["race_date"],
                "circuitId": int(event["circuitId"]),
                "circuit_ref": event["circuit_ref"],
                "circuit_name": event["circuit_name"],
                "circuit_location": event["circuit_location"],
                "circuit_country": event["circuit_country"],
                "dhl_available": dhl is not None,
                "dhl_source_path": dhl["source_path"] if dhl else "",
                "dhl_stop_rows": dhl["rows"] if dhl else 0,
                "openf1_available": True,
                "openf1_match_method": match_method,
                "openf1_meeting_key": openf1["meeting_key"],
                "openf1_session_key": openf1["session_key"],
                "openf1_date_start_utc": openf1["date_start"],
                "openf1_circuit_key": openf1["circuit_key"],
                "openf1_circuit_name": openf1["circuit_short_name"],
                "openf1_location": openf1["location"],
                "openf1_country_code": openf1["country_code"],
                "openf1_country_name": openf1["country_name"],
                "fastf1_available": fastf1 is not None,
                "fastf1_event_name": fastf1["fastf1_event_name"] if fastf1 else "",
                "fastf1_event_date": fastf1["fastf1_event_date"] if fastf1 else "",
                "fastf1_location": fastf1["fastf1_location"] if fastf1 else "",
                "fastf1_country": fastf1["fastf1_country"] if fastf1 else "",
                "fastf1_source_directory": (
                    f"data/raw/fastf1/{event['year']}/{event_id}" if fastf1 else ""
                ),
            }
        )

    # Chronological OpenF1 race order must agree with the canonical round.
    chronology_mismatches: list[str] = []
    for year in sorted({int(row["year"]) for row in rows}):
        year_rows = [row for row in rows if int(row["year"]) == year]
        ordered = sorted(year_rows, key=lambda row: row["openf1_date_start_utc"])
        for chronological_round, row in enumerate(ordered, start=1):
            if int(row["round"]) != chronological_round:
                chronology_mismatches.append(row["event_id"])
    if chronology_mismatches:
        raise ValueError(
            f"OpenF1 chronological order disagrees with rounds: {chronology_mismatches}"
        )

    duplicate_event_ids = duplicate_values([row["event_id"] for row in rows])
    duplicate_race_ids = duplicate_values([str(row["raceId"]) for row in rows])
    duplicate_session_keys = duplicate_values(
        [str(row["openf1_session_key"]) for row in rows]
    )
    duplicate_meeting_keys = duplicate_values(
        [str(row["openf1_meeting_key"]) for row in rows]
    )
    if any(
        (duplicate_event_ids, duplicate_race_ids, duplicate_session_keys, duplicate_meeting_keys)
    ):
        raise ValueError(
            "Duplicate bridge keys: "
            f"event_id={duplicate_event_ids}, raceId={duplicate_race_ids}, "
            f"session_key={duplicate_session_keys}, meeting_key={duplicate_meeting_keys}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    name_disagreements = []
    for row in rows:
        canonical_tokens = {
            normalized(row["race_name"].replace("Grand Prix", "")),
            normalized(row["circuit_location"]),
            normalized(row["circuit_ref"]),
        }
        openf1_tokens = {
            normalized(row["openf1_circuit_name"]),
            normalized(row["openf1_location"]),
        }
        if not any(
            token and (token in other or other in token)
            for token in canonical_tokens
            for other in openf1_tokens
        ):
            name_disagreements.append(row["event_id"])

    unresolved_name_disagreements = sorted(
        set(name_disagreements) - set(approved_name_differences)
    )
    unused_name_approvals = sorted(
        set(approved_name_differences) - set(name_disagreements)
    )
    if unresolved_name_disagreements:
        raise ValueError(
            "Cross-source event names require manual review: "
            f"{unresolved_name_disagreements}"
        )
    if unused_name_approvals:
        raise ValueError(
            f"Unused approved event-name differences: {unused_name_approvals}"
        )
    row_by_event = {row["event_id"]: row for row in rows}
    for event_id in sorted(name_disagreements):
        review_rows.append(
            {
                "event_id": event_id,
                "source": "Kaggle/OpenF1 names",
                "source_key": str(row_by_event[event_id]["openf1_session_key"]),
                "review_status": "approved",
                "reason": approved_name_differences[event_id],
            }
        )

    review_columns = ("event_id", "source", "source_key", "review_status", "reason")
    with args.review_output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=review_columns)
        writer.writeheader()
        writer.writerows(review_rows)

    match_counts = Counter(row["openf1_match_method"] for row in rows)
    availability = {
        "kaggle": len(rows),
        "dhl": sum(bool(row["dhl_available"]) for row in rows),
        "openf1": sum(bool(row["openf1_available"]) for row in rows),
        "fastf1": sum(bool(row["fastf1_available"]) for row in rows),
    }
    manifest = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_file": args.output.as_posix(),
        "review_file": args.review_output.as_posix(),
        "event_count": len(rows),
        "availability": availability,
        "openf1_match_methods": dict(sorted(match_counts.items())),
        "manual_review_rows": len(review_rows),
        "all_manual_reviews_approved": all(
            row["review_status"] == "approved" for row in review_rows
        ),
        "approved_name_disagreement_events": sorted(name_disagreements),
        "unresolved_name_disagreement_events": unresolved_name_disagreements,
        "chronology_mismatches": chronology_mismatches,
        "unique_keys": {
            "event_id": not duplicate_event_ids,
            "raceId": not duplicate_race_ids,
            "openf1_session_key": not duplicate_session_keys,
            "openf1_meeting_key": not duplicate_meeting_keys,
        },
        "columns": list(OUTPUT_COLUMNS),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"Built event bridge: {len(rows)} rows")
    print(f"Availability: {availability}")
    print(f"OpenF1 match methods: {dict(sorted(match_counts.items()))}")
    print(f"Approved manual reviews: {len(review_rows)}")
    print(f"Approved event-name differences: {len(name_disagreements)}")
    print(f"Output: {args.output}")
    print(f"Manifest: {args.manifest}")


if __name__ == "__main__":
    main()
