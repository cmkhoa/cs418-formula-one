"""Acquire OpenF1 race-session data for 2023–2025 with a resumable cache."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


BASE_URL = "https://api.openf1.org/v1"
DEFAULT_YEARS = (2023, 2024, 2025)
SESSION_ENDPOINTS = ("drivers", "pit", "weather", "race_control", "session_result")


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
        "--output-dir",
        type=Path,
        default=Path("data/raw/openf1"),
        help="Raw JSON cache directory.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("metadata/openf1_manifest.json"),
        help="Acquisition manifest path.",
    )
    parser.add_argument(
        "--request-interval",
        type=float,
        default=2.1,
        help="Minimum seconds between API calls (default: 2.1).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=90.0,
        help="HTTP timeout in seconds (default: 90).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Redownload files that already exist.",
    )
    return parser.parse_args()


class RateLimitedClient:
    def __init__(self, interval: float, timeout: float) -> None:
        self.interval = interval
        self.timeout = timeout
        self.last_request = 0.0
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "cs418-formula-one-data-acquisition"}
        )

    def get(self, endpoint: str, **params: Any) -> list[dict[str, Any]]:
        for attempt in range(1, 6):
            elapsed = time.monotonic() - self.last_request
            if elapsed < self.interval:
                time.sleep(self.interval - elapsed)
            response = self.session.get(
                f"{BASE_URL}/{endpoint}", params=params, timeout=self.timeout
            )
            self.last_request = time.monotonic()
            if response.status_code == 429:
                wait = float(response.headers.get("Retry-After", 10))
                time.sleep(max(wait, 10.0))
                continue
            if response.status_code == 404:
                # OpenF1 uses 404 when an endpoint has no rows for a valid
                # historical session (notably early-2023 pit data).
                return []
            if response.status_code >= 500 and attempt < 5:
                time.sleep(min(2**attempt, 30))
                continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise TypeError(
                    f"Expected a JSON list from {endpoint}, got {type(payload).__name__}"
                )
            return payload
        raise RuntimeError(f"OpenF1 request failed after retries: {endpoint} {params}")


def write_json(path: Path, payload: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise TypeError(f"Expected JSON list in {path}")
    return payload


def acquire_json(
    client: RateLimitedClient,
    path: Path,
    endpoint: str,
    overwrite: bool,
    **params: Any,
) -> list[dict[str, Any]]:
    if path.exists() and not overwrite:
        return load_json(path)
    payload = client.get(endpoint, **params)
    write_json(path, payload)
    return payload


def sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def profile_json(path: Path) -> dict[str, Any]:
    rows = load_json(path)
    schemas = Counter(tuple(sorted(row.keys())) for row in rows)
    return {
        "rows": len(rows),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "schemas": [
            {"columns": list(columns), "rows": count}
            for columns, count in sorted(schemas.items())
        ],
    }


def main() -> None:
    args = parse_args()
    years = sorted(set(args.years))
    client = RateLimitedClient(args.request_interval, args.timeout)
    failures: dict[str, str] = {}
    race_sessions: list[dict[str, Any]] = []

    for year in years:
        path = args.output_dir / f"sessions_{year}.json"
        sessions = acquire_json(
            client, path, "sessions", args.overwrite, year=year
        )
        selected = [
            row
            for row in sessions
            if row.get("session_name") == "Race" and not row.get("is_cancelled", False)
        ]
        race_sessions.extend(selected)
        print(
            f"{year}: {len(sessions)} sessions, {len(selected)} non-cancelled races",
            flush=True,
        )

    session_keys = [int(row["session_key"]) for row in race_sessions]
    if len(session_keys) != len(set(session_keys)):
        raise ValueError("OpenF1 race sessions contain duplicate session_key values")
    race_sessions.sort(key=lambda row: row.get("date_start", ""))

    for index, session in enumerate(race_sessions, start=1):
        session_key = int(session["session_key"])
        year = int(session["year"])
        directory = args.output_dir / str(year) / str(session_key)
        print(
            f"[{index}/{len(race_sessions)}] {year} "
            f"{session.get('circuit_short_name', '')} session={session_key}",
            flush=True,
        )
        for endpoint in SESSION_ENDPOINTS:
            path = directory / f"{endpoint}.json"
            try:
                acquire_json(
                    client,
                    path,
                    endpoint,
                    args.overwrite,
                    session_key=session_key,
                )
            except Exception as exc:
                key = f"{session_key}:{endpoint}"
                failures[key] = f"{type(exc).__name__}: {exc}"
                print(f"  {endpoint} FAILED: {failures[key]}", flush=True)

    profiles: dict[str, Any] = {}
    incomplete_sessions: list[int] = []
    endpoint_totals = Counter()
    empty_endpoint_files: list[str] = []
    for session in race_sessions:
        session_key = int(session["session_key"])
        year = int(session["year"])
        directory = args.output_dir / str(year) / str(session_key)
        required = SESSION_ENDPOINTS
        if not all((directory / f"{endpoint}.json").exists() for endpoint in required):
            incomplete_sessions.append(session_key)
            continue
        session_profile: dict[str, Any] = {
            "session_metadata": session,
            "endpoints": {},
        }
        for endpoint in required:
            relative = f"{year}/{session_key}/{endpoint}.json"
            profile = profile_json(directory / f"{endpoint}.json")
            session_profile["endpoints"][endpoint] = profile
            endpoint_totals[endpoint] += profile["rows"]
            if profile["rows"] == 0:
                empty_endpoint_files.append(relative)
        profiles[str(session_key)] = session_profile

    sessions_by_year = Counter(int(row["year"]) for row in race_sessions)
    meeting_keys = [int(row["meeting_key"]) for row in race_sessions]
    year_session_files = {
        str(year): profile_json(args.output_dir / f"sessions_{year}.json")
        for year in years
    }
    manifest = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "years": years,
        "raw_output_directory": args.output_dir.as_posix(),
        "request_interval_seconds": args.request_interval,
        "expected_race_session_count": len(race_sessions),
        "complete_race_session_count": len(profiles),
        "race_sessions_by_year": {
            str(year): sessions_by_year.get(year, 0) for year in years
        },
        "session_key_unique": len(session_keys) == len(set(session_keys)),
        "meeting_key_unique_for_races": len(meeting_keys) == len(set(meeting_keys)),
        "incomplete_session_keys": incomplete_sessions,
        "failures": failures,
        "endpoint_row_totals": dict(sorted(endpoint_totals.items())),
        "empty_endpoint_files": sorted(empty_endpoint_files),
        "year_session_files": year_session_files,
        "sessions": profiles,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"Complete OpenF1 race sessions: {len(profiles)}/{len(race_sessions)}")
    print(f"Sessions by year: {dict(sorted(sessions_by_year.items()))}")
    print(f"Endpoint row totals: {dict(sorted(endpoint_totals.items()))}")
    print(f"Incomplete sessions: {len(incomplete_sessions)}")
    print(f"Manifest: {args.manifest}")
    if incomplete_sessions:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
