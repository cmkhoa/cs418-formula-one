"""Acquire and profile DHL pit-stop race files from the GitHub mirror.

The downloader resolves the current ``main`` branch to an immutable commit SHA,
downloads race CSV files for the requested complete seasons, and records file
hashes and parsing diagnostics in a tracked manifest. The upstream files use
tab separators even though their extension is ``.csv``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


REPOSITORY = "Jordan-Soria/PitStops"
API_ROOT = f"https://api.github.com/repos/{REPOSITORY}"
RAW_ROOT = f"https://raw.githubusercontent.com/{REPOSITORY}"
DEFAULT_YEARS = (2023, 2024, 2025)
EXPECTED_COLUMNS = ("Pos.", "Team", "Driver", "Time (sec)", "Lap", "Points")
RACE_FILE = re.compile(r"^(?P<round>\d+).*\.csv$", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--years",
        type=int,
        nargs="+",
        default=list(DEFAULT_YEARS),
        help="Seasons to acquire (default: 2023 2024 2025).",
    )
    parser.add_argument(
        "--commit",
        help="Immutable mirror commit SHA. Defaults to resolving main.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/raw/dhl"),
        help="Raw output directory (default: data/raw/dhl).",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("metadata/dhl_manifest.json"),
        help="Manifest path (default: metadata/dhl_manifest.json).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP request timeout in seconds (default: 30).",
    )
    return parser.parse_args()


def github_get(session: requests.Session, url: str, timeout: float) -> Any:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def resolve_commit(
    session: requests.Session, requested_commit: str | None, timeout: float
) -> tuple[str, str | None]:
    ref = requested_commit or "main"
    commit = github_get(session, f"{API_ROOT}/commits/{ref}", timeout)
    return commit["sha"], commit.get("commit", {}).get("committer", {}).get("date")


def repository_tree(
    session: requests.Session, commit: str, timeout: float
) -> list[dict[str, Any]]:
    tree = github_get(
        session,
        f"{API_ROOT}/git/trees/{commit}?recursive=1",
        timeout,
    )
    if tree.get("truncated"):
        raise RuntimeError("GitHub returned a truncated repository tree")
    return tree["tree"]


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def parse_tsv(content: bytes, source_path: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    text = content.decode("utf-8-sig")
    rows = list(csv.reader(text.splitlines(), delimiter="\t"))
    if not rows:
        raise ValueError(f"Empty file with no header: {source_path}")

    header = [value.strip() for value in rows[0]]
    data_rows = rows[1:]
    malformed_lines = [
        index + 2 for index, row in enumerate(data_rows) if len(row) != len(header)
    ]
    valid_rows = [row for row in data_rows if len(row) == len(header)]
    records = [
        {column: value.strip() for column, value in zip(header, row, strict=True)}
        for row in valid_rows
    ]
    missing_by_column = {
        column: sum(not record[column] for record in records) for column in header
    }
    required_missing = sorted(set(EXPECTED_COLUMNS) - set(header))

    profile = {
        "rows": len(records),
        "columns": header,
        "column_count": len(header),
        "header_only": len(records) == 0,
        "malformed_line_numbers": malformed_lines,
        "missing_by_column": missing_by_column,
        "missing_required_columns": required_missing,
    }
    return profile, records


def main() -> None:
    args = parse_args()
    years = sorted(set(args.years))
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/vnd.github+json",
            "User-Agent": "cs418-formula-one-data-acquisition",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )

    commit, commit_date = resolve_commit(session, args.commit, args.timeout)
    tree = repository_tree(session, commit, args.timeout)
    blobs = {item["path"]: item for item in tree if item["type"] == "blob"}

    selected: list[tuple[int, int, str]] = []
    skipped_csvs: list[str] = []
    for path in sorted(blobs):
        parts = Path(path).parts
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        year = int(parts[0])
        if year not in years or not path.lower().endswith(".csv"):
            continue
        match = RACE_FILE.match(parts[1])
        if match is None:
            skipped_csvs.append(path)
            continue
        selected.append((year, int(match.group("round")), path))

    if not selected:
        raise RuntimeError(f"No DHL race files found for years {years}")

    file_profiles: dict[str, dict[str, Any]] = {}
    all_records: list[dict[str, Any]] = []
    seen_year_round: set[tuple[int, int]] = set()
    duplicate_year_round: list[tuple[int, int]] = []

    for year, round_number, source_path in selected:
        event_key = (year, round_number)
        if event_key in seen_year_round:
            duplicate_year_round.append(event_key)
        seen_year_round.add(event_key)

        url = f"{RAW_ROOT}/{commit}/{source_path}"
        response = session.get(url, timeout=args.timeout)
        response.raise_for_status()
        content = response.content

        destination = args.output_dir / source_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

        profile, records = parse_tsv(content, source_path)
        profile.update(
            {
                "year": year,
                "round": round_number,
                "bytes": len(content),
                "sha256": sha256(content),
                "source_path": source_path,
            }
        )
        file_profiles[source_path] = profile
        for record in records:
            all_records.append(
                {
                    **record,
                    "year": year,
                    "round": round_number,
                    "source_path": source_path,
                }
            )

    if duplicate_year_round:
        raise ValueError(
            "More than one DHL file maps to a season/round: "
            f"{sorted(set(duplicate_year_round))}"
        )

    files_by_year = Counter(profile["year"] for profile in file_profiles.values())
    rows_by_year = Counter()
    for profile in file_profiles.values():
        rows_by_year[profile["year"]] += profile["rows"]

    duplicate_driver_lap_rows = 0
    driver_lap_counts = Counter(
        (
            row["year"],
            row["round"],
            row.get("Driver", ""),
            row.get("Lap", ""),
        )
        for row in all_records
        if row.get("Driver") and row.get("Lap")
    )
    duplicate_driver_lap_rows = sum(
        count for count in driver_lap_counts.values() if count > 1
    )
    missing_by_column = {
        column: sum(not row.get(column, "") for row in all_records)
        for column in EXPECTED_COLUMNS
    }
    invalid_numeric_by_column: dict[str, int] = {}
    for column in ("Pos.", "Time (sec)", "Lap", "Points"):
        invalid = 0
        for row in all_records:
            value = row.get(column, "")
            if not value:
                continue
            try:
                float(value)
            except ValueError:
                invalid += 1
        invalid_numeric_by_column[column] = invalid

    manifest = {
        "repository": REPOSITORY,
        "commit_sha": commit,
        "commit_date_utc": commit_date,
        "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
        "years": years,
        "raw_output_directory": args.output_dir.as_posix(),
        "race_file_count": len(file_profiles),
        "race_files_by_year": {
            str(year): files_by_year.get(year, 0) for year in years
        },
        "stop_rows": len(all_records),
        "stop_rows_by_year": {
            str(year): rows_by_year.get(year, 0) for year in years
        },
        "header_only_files": sorted(
            path for path, profile in file_profiles.items() if profile["header_only"]
        ),
        "files_with_malformed_rows": sorted(
            path
            for path, profile in file_profiles.items()
            if profile["malformed_line_numbers"]
        ),
        "files_missing_required_columns": sorted(
            path
            for path, profile in file_profiles.items()
            if profile["missing_required_columns"]
        ),
        "missing_cells_by_column": missing_by_column,
        "invalid_nonempty_numeric_cells_by_column": invalid_numeric_by_column,
        "duplicate_driver_lap_rows": duplicate_driver_lap_rows,
        "skipped_non_race_csv_files": skipped_csvs,
        "files": file_profiles,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"DHL mirror commit: {commit}")
    print(f"Commit date: {commit_date or 'unknown'}")
    print(f"Downloaded {len(file_profiles)} race files to {args.output_dir}")
    print(f"Race files by year: {dict(sorted(files_by_year.items()))}")
    print(f"Stop rows by year: {dict(sorted(rows_by_year.items()))}")
    print(f"Header-only files: {len(manifest['header_only_files'])}")
    print(f"Files with malformed rows: {len(manifest['files_with_malformed_rows'])}")
    print(f"Missing cells by column: {missing_by_column}")
    print(f"Invalid nonempty numeric cells: {invalid_numeric_by_column}")
    print(f"Duplicate driver/lap rows: {duplicate_driver_lap_rows}")
    print(f"Manifest: {args.manifest}")


if __name__ == "__main__":
    main()
