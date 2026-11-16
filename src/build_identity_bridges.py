"""Build event-specific driver and team identity bridges for 2023–2025."""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DRIVER_COLUMNS = (
    "event_id",
    "year",
    "round",
    "raceId",
    "driverId",
    "driver_ref",
    "forename",
    "surname",
    "canonical_full_name",
    "kaggle_driver_number",
    "constructorId",
    "constructor_ref",
    "kaggle_team_name",
    "openf1_available",
    "openf1_driver_number",
    "openf1_name_acronym",
    "openf1_first_name",
    "openf1_last_name",
    "openf1_full_name",
    "openf1_team_name",
    "dhl_available",
    "dhl_driver_name",
    "dhl_team_name",
    "dhl_stop_rows",
    "fastf1_available",
    "fastf1_driver_number",
    "fastf1_abbreviation",
    "fastf1_full_name",
    "fastf1_team_name",
)

TEAM_COLUMNS = (
    "event_id",
    "year",
    "round",
    "raceId",
    "constructorId",
    "constructor_ref",
    "canonical_team_name",
    "constructor_nationality",
    "driver_count",
    "driverIds",
    "driver_numbers",
    "openf1_available",
    "openf1_team_names",
    "dhl_available",
    "dhl_team_names",
    "dhl_stop_rows",
    "fastf1_available",
    "fastf1_team_names",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--event-bridge",
        type=Path,
        default=Path("data/interim/event_bridge.csv"),
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument(
        "--exceptions",
        type=Path,
        default=Path("metadata/identity_bridge_exceptions.json"),
    )
    parser.add_argument(
        "--driver-output",
        type=Path,
        default=Path("data/interim/driver_event_bridge.csv"),
    )
    parser.add_argument(
        "--team-output",
        type=Path,
        default=Path("data/interim/team_event_bridge.csv"),
    )
    parser.add_argument(
        "--review-output",
        type=Path,
        default=Path("data/interim/identity_bridge_review.csv"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("metadata/identity_bridge_manifest.json"),
    )
    return parser.parse_args()


def read_csv(path: Path, delimiter: str = ",") -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file, delimiter=delimiter))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(character for character in value if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def joined(values: set[str]) -> str:
    return "|".join(sorted(value for value in values if value))


def write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    events = read_csv(args.event_bridge)
    event_by_race = {row["raceId"]: row for row in events}
    event_by_id = {row["event_id"]: row for row in events}
    drivers = {row["driverId"]: row for row in read_csv(args.data_dir / "drivers.csv")}
    constructors = {
        row["constructorId"]: row for row in read_csv(args.data_dir / "constructors.csv")
    }
    results = [
        row
        for row in read_csv(args.data_dir / "results.csv")
        if row["raceId"] in event_by_race
    ]
    exceptions = read_json(args.exceptions)
    expected_openf1_missing = exceptions.get(
        "expected_openf1_missing_driver_keys", {}
    )

    result_key_counts = Counter((row["raceId"], row["driverId"]) for row in results)
    duplicate_result_keys = [key for key, count in result_key_counts.items() if count > 1]
    if duplicate_result_keys:
        raise ValueError(f"Duplicate Kaggle race/driver result keys: {duplicate_result_keys}")

    result_number_counts = Counter((row["raceId"], row["number"]) for row in results)
    duplicate_event_numbers = [
        key for key, count in result_number_counts.items() if count > 1
    ]
    if duplicate_event_numbers:
        raise ValueError(f"Duplicate Kaggle race/car-number keys: {duplicate_event_numbers}")

    results_by_race: dict[str, list[dict[str, str]]] = defaultdict(list)
    for result in results:
        results_by_race[result["raceId"]].append(result)

    driver_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, str]] = []
    used_expected_missing: set[str] = set()
    unexpected_openf1_missing: list[str] = []
    openf1_name_disagreements: list[str] = []
    fastf1_name_disagreements: list[str] = []
    unmatched_dhl_rows: list[dict[str, str]] = []
    ambiguous_dhl_rows: list[dict[str, str]] = []

    for event in events:
        event_id = event["event_id"]
        race_results = results_by_race[event["raceId"]]
        result_by_number = {row["number"]: row for row in race_results}
        result_by_normalized_surname: dict[str, list[dict[str, str]]] = defaultdict(list)
        for result in race_results:
            result_by_normalized_surname[
                normalize(drivers[result["driverId"]]["surname"])
            ].append(result)

        openf1_path = (
            args.data_dir
            / "raw"
            / "openf1"
            / event["year"]
            / event["openf1_session_key"]
            / "drivers.json"
        )
        openf1_drivers = read_json(openf1_path)
        openf1_by_number: dict[str, dict[str, Any]] = {}
        for row in openf1_drivers:
            number = str(row["driver_number"])
            if number in openf1_by_number:
                raise ValueError(f"Duplicate OpenF1 car number {event_id}:{number}")
            openf1_by_number[number] = row

        dhl_path = args.data_dir / "raw" / "dhl" / event["dhl_source_path"]
        dhl_records = [
            {key.strip(): value.strip() for key, value in row.items()}
            for row in read_csv(dhl_path, delimiter="\t")
        ]
        dhl_by_driver_id: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in dhl_records:
            candidates = result_by_normalized_surname.get(normalize(row["Driver"]), [])
            if not candidates:
                unmatched_dhl_rows.append(
                    {"event_id": event_id, "driver": row["Driver"], "team": row["Team"]}
                )
                continue
            if len(candidates) > 1:
                ambiguous_dhl_rows.append(
                    {"event_id": event_id, "driver": row["Driver"], "team": row["Team"]}
                )
                continue
            dhl_by_driver_id[candidates[0]["driverId"]].append(row)

        fastf1_by_number: dict[str, dict[str, str]] = {}
        if event["fastf1_available"] == "True":
            fastf1_results = read_csv(
                Path(event["fastf1_source_directory"]) / "results.csv"
            )
            for row in fastf1_results:
                number = row["DriverNumber"]
                if number in fastf1_by_number:
                    raise ValueError(f"Duplicate FastF1 car number {event_id}:{number}")
                fastf1_by_number[number] = row

        for result in sorted(race_results, key=lambda row: int(row["positionOrder"])):
            driver = drivers[result["driverId"]]
            constructor = constructors[result["constructorId"]]
            number = result["number"]
            identity_key = f"{event_id}:{number}"
            openf1 = openf1_by_number.get(number)
            if openf1 is None:
                if identity_key in expected_openf1_missing:
                    used_expected_missing.add(identity_key)
                    review_rows.append(
                        {
                            "identity_key": identity_key,
                            "source": "OpenF1",
                            "review_status": "approved_missing",
                            "reason": expected_openf1_missing[identity_key],
                        }
                    )
                else:
                    unexpected_openf1_missing.append(identity_key)
            elif normalize(driver["surname"]) not in normalize(
                str(openf1.get("full_name", ""))
            ):
                openf1_name_disagreements.append(identity_key)

            dhl_rows = dhl_by_driver_id.get(result["driverId"], [])
            dhl_driver_names = {row["Driver"] for row in dhl_rows}
            dhl_team_names = {row["Team"] for row in dhl_rows}
            fastf1 = fastf1_by_number.get(number)
            if fastf1 is not None and normalize(driver["surname"]) not in normalize(
                fastf1.get("FullName", "")
            ):
                fastf1_name_disagreements.append(identity_key)

            driver_rows.append(
                {
                    "event_id": event_id,
                    "year": int(event["year"]),
                    "round": int(event["round"]),
                    "raceId": int(event["raceId"]),
                    "driverId": int(result["driverId"]),
                    "driver_ref": driver["driverRef"],
                    "forename": driver["forename"],
                    "surname": driver["surname"],
                    "canonical_full_name": f"{driver['forename']} {driver['surname']}",
                    "kaggle_driver_number": number,
                    "constructorId": int(result["constructorId"]),
                    "constructor_ref": constructor["constructorRef"],
                    "kaggle_team_name": constructor["name"],
                    "openf1_available": openf1 is not None,
                    "openf1_driver_number": openf1["driver_number"] if openf1 else "",
                    "openf1_name_acronym": openf1["name_acronym"] if openf1 else "",
                    "openf1_first_name": openf1["first_name"] if openf1 else "",
                    "openf1_last_name": openf1["last_name"] if openf1 else "",
                    "openf1_full_name": openf1["full_name"] if openf1 else "",
                    "openf1_team_name": openf1["team_name"] if openf1 else "",
                    "dhl_available": bool(dhl_rows),
                    "dhl_driver_name": joined(dhl_driver_names),
                    "dhl_team_name": joined(dhl_team_names),
                    "dhl_stop_rows": len(dhl_rows),
                    "fastf1_available": fastf1 is not None,
                    "fastf1_driver_number": fastf1["DriverNumber"] if fastf1 else "",
                    "fastf1_abbreviation": fastf1["Abbreviation"] if fastf1 else "",
                    "fastf1_full_name": fastf1["FullName"] if fastf1 else "",
                    "fastf1_team_name": fastf1["TeamName"] if fastf1 else "",
                }
            )

    unused_expected_missing = sorted(set(expected_openf1_missing) - used_expected_missing)
    if unused_expected_missing:
        raise ValueError(f"Unused expected OpenF1 missing keys: {unused_expected_missing}")
    if unexpected_openf1_missing:
        raise ValueError(
            f"Unexpected missing OpenF1 driver matches: {unexpected_openf1_missing}"
        )
    if openf1_name_disagreements:
        raise ValueError(
            f"OpenF1/Kaggle driver-name disagreements: {openf1_name_disagreements}"
        )
    if fastf1_name_disagreements:
        raise ValueError(
            f"FastF1/Kaggle driver-name disagreements: {fastf1_name_disagreements}"
        )
    if unmatched_dhl_rows or ambiguous_dhl_rows:
        raise ValueError(
            f"DHL driver matching failed: unmatched={unmatched_dhl_rows}, "
            f"ambiguous={ambiguous_dhl_rows}"
        )

    driver_key_counts = Counter(
        (row["event_id"], row["driverId"]) for row in driver_rows
    )
    duplicate_driver_keys = [
        key for key, count in driver_key_counts.items() if count > 1
    ]
    if duplicate_driver_keys:
        raise ValueError(f"Duplicate driver bridge keys: {duplicate_driver_keys}")

    # Team identities are derived through the already verified event-driver rows,
    # never by directly equating free-text team names.
    team_groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in driver_rows:
        team_groups[(row["event_id"], row["constructorId"])].append(row)

    team_rows: list[dict[str, Any]] = []
    for (event_id, constructor_id), group in sorted(team_groups.items()):
        event = event_by_id[event_id]
        constructor = constructors[str(constructor_id)]
        dhl_team_names = {
            name
            for row in group
            for name in row["dhl_team_name"].split("|")
            if name
        }
        openf1_team_names = {
            row["openf1_team_name"] for row in group if row["openf1_team_name"]
        }
        fastf1_team_names = {
            row["fastf1_team_name"] for row in group if row["fastf1_team_name"]
        }
        team_rows.append(
            {
                "event_id": event_id,
                "year": int(event["year"]),
                "round": int(event["round"]),
                "raceId": int(event["raceId"]),
                "constructorId": constructor_id,
                "constructor_ref": constructor["constructorRef"],
                "canonical_team_name": constructor["name"],
                "constructor_nationality": constructor["nationality"],
                "driver_count": len(group),
                "driverIds": joined({str(row["driverId"]) for row in group}),
                "driver_numbers": joined(
                    {str(row["kaggle_driver_number"]) for row in group}
                ),
                "openf1_available": bool(openf1_team_names),
                "openf1_team_names": joined(openf1_team_names),
                "dhl_available": bool(dhl_team_names),
                "dhl_team_names": joined(dhl_team_names),
                "dhl_stop_rows": sum(int(row["dhl_stop_rows"]) for row in group),
                "fastf1_available": bool(fastf1_team_names),
                "fastf1_team_names": joined(fastf1_team_names),
            }
        )

    # A free-text DHL team label must not resolve to multiple constructors in the
    # same event after driver-based mapping.
    dhl_label_targets: dict[tuple[str, str], set[int]] = defaultdict(set)
    for row in team_rows:
        for name in row["dhl_team_names"].split("|"):
            if name:
                dhl_label_targets[(row["event_id"], name)].add(row["constructorId"])
    dhl_team_to_constructor_conflicts = [
        f"{event_id}:{name}"
        for (event_id, name), targets in dhl_label_targets.items()
        if len(targets) > 1
    ]
    if dhl_team_to_constructor_conflicts:
        raise ValueError(
            "DHL team labels map to multiple constructors in an event: "
            f"{dhl_team_to_constructor_conflicts}"
        )

    write_csv(args.driver_output, DRIVER_COLUMNS, driver_rows)
    write_csv(args.team_output, TEAM_COLUMNS, team_rows)
    write_csv(
        args.review_output,
        ("identity_key", "source", "review_status", "reason"),
        review_rows,
    )

    manifest = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "driver_output": args.driver_output.as_posix(),
        "team_output": args.team_output.as_posix(),
        "review_output": args.review_output.as_posix(),
        "driver_event_rows": len(driver_rows),
        "team_event_rows": len(team_rows),
        "unique_driver_event_keys": not duplicate_driver_keys,
        "openf1_driver_matches": sum(
            bool(row["openf1_available"]) for row in driver_rows
        ),
        "openf1_expected_missing": sorted(used_expected_missing),
        "openf1_unexpected_missing": unexpected_openf1_missing,
        "dhl_stop_rows": sum(int(row["dhl_stop_rows"]) for row in driver_rows),
        "dhl_unmatched_stop_rows": len(unmatched_dhl_rows),
        "dhl_ambiguous_stop_rows": len(ambiguous_dhl_rows),
        "fastf1_driver_matches": sum(
            bool(row["fastf1_available"]) for row in driver_rows
        ),
        "driver_name_disagreements": {
            "openf1": openf1_name_disagreements,
            "fastf1": fastf1_name_disagreements,
        },
        "team_driver_count_distribution": dict(
            sorted(Counter(row["driver_count"] for row in team_rows).items())
        ),
        "dhl_team_to_constructor_conflicts": dhl_team_to_constructor_conflicts,
        "review_rows": len(review_rows),
        "driver_columns": list(DRIVER_COLUMNS),
        "team_columns": list(TEAM_COLUMNS),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"Driver-event bridge rows: {len(driver_rows)}")
    print(f"Team-event bridge rows: {len(team_rows)}")
    print(
        f"OpenF1 driver matches: {manifest['openf1_driver_matches']}/{len(driver_rows)}"
    )
    print(f"DHL stop rows matched to drivers: {manifest['dhl_stop_rows']}")
    print(
        f"FastF1 driver matches: {manifest['fastf1_driver_matches']}/{len(driver_rows)}"
    )
    print(f"Approved identity exceptions: {len(review_rows)}")
    print(f"Manifest: {args.manifest}")


if __name__ == "__main__":
    main()
