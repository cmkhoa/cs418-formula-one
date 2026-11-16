"""Acquire and verify the Kaggle Formula 1 relational dataset.

The script supports two modes:

1. Download the current Kaggle snapshot with kagglehub.
2. Copy an already downloaded KaggleHub version with ``--source-dir``.

Raw CSV files are copied to the repository's existing ``data`` directory by
default. A tracked JSON
manifest records the resolved source version, file hashes, row counts, schemas,
and season coverage so later processing can confirm that it used the same input.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


DATASET_HANDLE = "jtrotman/formula-1-race-data"
EXPECTED_FILES = {
    "circuits.csv",
    "constructor_results.csv",
    "constructor_standings.csv",
    "constructors.csv",
    "driver_standings.csv",
    "drivers.csv",
    "lap_times.csv",
    "pit_stops.csv",
    "qualifying.csv",
    "races.csv",
    "results.csv",
    "seasons.csv",
    "sprint_results.csv",
    "status.csv",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        help="Existing extracted Kaggle dataset directory; skips downloading.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data"),
        help="Raw snapshot destination (default: data).",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("metadata/kaggle_manifest.json"),
        help="Manifest destination (default: metadata/kaggle_manifest.json).",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Ask kagglehub to redownload instead of using its cache.",
    )
    return parser.parse_args()


def resolve_source(args: argparse.Namespace) -> Path:
    if args.source_dir is not None:
        source = args.source_dir.expanduser().resolve()
        if not source.is_dir():
            raise FileNotFoundError(f"Source directory does not exist: {source}")
        return source

    try:
        import kagglehub
    except ImportError as exc:
        raise RuntimeError(
            "kagglehub is required for downloading. Install it with "
            "`python -m pip install kagglehub`, or pass --source-dir."
        ) from exc

    return Path(
        kagglehub.dataset_download(
            DATASET_HANDLE,
            force_download=args.force_download,
        )
    ).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def csv_profile(path: Path) -> dict[str, object]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.reader(file)
        try:
            columns = next(reader)
        except StopIteration as exc:
            raise ValueError(f"CSV is empty: {path}") from exc
        rows = sum(1 for _ in reader)

    return {
        "rows": rows,
        "columns": columns,
        "column_count": len(columns),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def race_coverage(races_path: Path) -> dict[str, object]:
    with races_path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        years: list[int] = []
        round_counts: dict[int, int] = {}
        duplicate_keys: set[tuple[int, int]] = set()
        seen_keys: set[tuple[int, int]] = set()

        for row in reader:
            year = int(row["year"])
            round_number = int(row["round"])
            years.append(year)
            round_counts[year] = round_counts.get(year, 0) + 1
            key = (year, round_number)
            if key in seen_keys:
                duplicate_keys.add(key)
            seen_keys.add(key)

    if not years:
        raise ValueError("races.csv contains no data rows")
    if duplicate_keys:
        raise ValueError(
            "races.csv has duplicate (year, round) keys: "
            f"{sorted(duplicate_keys)[:10]}"
        )

    return {
        "minimum_year": min(years),
        "maximum_year": max(years),
        "race_count": len(years),
        "races_by_year_2023_2025": {
            str(year): round_counts.get(year, 0) for year in range(2023, 2026)
        },
        "year_round_key_unique": True,
    }


def inferred_kaggle_version(source: Path) -> str | None:
    if source.parent.name == "versions" and source.name.isdigit():
        return source.name
    return None


def main() -> None:
    args = parse_args()
    source = resolve_source(args)
    source_files = {path.name for path in source.glob("*.csv")}
    missing = EXPECTED_FILES - source_files
    unexpected = source_files - EXPECTED_FILES
    if missing:
        raise FileNotFoundError(f"Missing expected Kaggle tables: {sorted(missing)}")
    if unexpected:
        print(f"Warning: unexpected CSV files will also be copied: {sorted(unexpected)}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name in sorted(source_files):
        shutil.copy2(source / name, args.output_dir / name)

    profiles = {
        name: csv_profile(args.output_dir / name) for name in sorted(source_files)
    }
    coverage = race_coverage(args.output_dir / "races.csv")

    manifest = {
        "dataset_handle": DATASET_HANDLE,
        "kaggle_version": inferred_kaggle_version(source),
        "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_mode": "local_directory" if args.source_dir is not None else "kagglehub",
        "raw_output_directory": args.output_dir.as_posix(),
        "expected_table_count": len(EXPECTED_FILES),
        "actual_table_count": len(source_files),
        "race_coverage": coverage,
        "files": profiles,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"Kaggle source: {source}")
    print(f"Resolved Kaggle version: {manifest['kaggle_version'] or 'unknown'}")
    print(f"Copied {len(source_files)} tables to {args.output_dir}")
    print(
        "Race coverage: "
        f"{coverage['minimum_year']}–{coverage['maximum_year']} "
        f"({coverage['race_count']} races)"
    )
    print(
        "Complete-season scope counts: "
        f"{coverage['races_by_year_2023_2025']}"
    )
    print(f"Manifest: {args.manifest}")


if __name__ == "__main__":
    main()
