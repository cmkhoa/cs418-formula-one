"""Aggregate event-level weather and race-control context without changing stop rows."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline_utils import as_float, mean, read_csv, read_json, write_csv, write_json


OPENF1_MEASURES = (
    "air_temperature", "track_temperature", "humidity", "pressure", "wind_speed"
)
FASTF1_MEASURES = (
    ("AirTemp", "air_temperature"), ("TrackTemp", "track_temperature"),
    ("Humidity", "humidity"), ("Pressure", "pressure"), ("WindSpeed", "wind_speed"),
)
BASE_COLUMNS = (
    "event_id", "year", "round", "raceId", "race_name", "race_date", "circuitId",
    "circuit_ref", "circuit_name", "circuit_location", "circuit_country",
    "openf1_session_key", "openf1_weather_observations", "openf1_rain_observations",
    "openf1_any_rain", "openf1_race_control_messages", "openf1_safety_car_messages",
    "openf1_virtual_safety_car_messages", "openf1_red_flag_messages",
    "fastf1_available", "fastf1_weather_observations", "fastf1_rain_observations",
    "fastf1_any_rain",
)
SUMMARY_COLUMNS = tuple(
    f"{source}_{measure}_{stat}"
    for source in ("openf1", "fastf1")
    for measure in ("air_temperature", "track_temperature", "humidity", "pressure", "wind_speed")
    for stat in ("min", "mean", "max")
)
COLUMNS = BASE_COLUMNS + SUMMARY_COLUMNS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--event-bridge", type=Path, default=Path("data/interim/event_bridge.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/interim/event_context.csv"))
    parser.add_argument("--manifest", type=Path, default=Path("metadata/event_context_manifest.json"))
    return parser.parse_args()


def numeric_summary(rows: list[dict[str, Any]], source_key: str, output_key: str) -> dict[str, Any]:
    values = [as_float(row.get(source_key)) for row in rows]
    numbers = [value for value in values if value is not None]
    return {
        f"{output_key}_min": min(numbers) if numbers else "",
        f"{output_key}_mean": mean(numbers) if numbers else "",
        f"{output_key}_max": max(numbers) if numbers else "",
    }


def is_rain(value: Any) -> bool:
    return str(value).strip().casefold() in {"1", "1.0", "true"}


def main() -> None:
    args = parse_args()
    events = read_csv(args.event_bridge)
    output: list[dict[str, Any]] = []
    for event in events:
        openf1_dir = (
            args.data_dir / "raw" / "openf1" / event["year"] / event["openf1_session_key"]
        )
        weather = read_json(openf1_dir / "weather.json")
        control = read_json(openf1_dir / "race_control.json")
        messages = [str(row.get("message") or "").upper() for row in control]
        fastf1_weather: list[dict[str, str]] = []
        if event["fastf1_available"] == "True":
            fastf1_weather = read_csv(Path(event["fastf1_source_directory"]) / "weather.csv")

        row: dict[str, Any] = {
            "event_id": event["event_id"], "year": int(event["year"]),
            "round": int(event["round"]), "raceId": int(event["raceId"]),
            "race_name": event["race_name"], "race_date": event["race_date"],
            "circuitId": int(event["circuitId"]), "circuit_ref": event["circuit_ref"],
            "circuit_name": event["circuit_name"], "circuit_location": event["circuit_location"],
            "circuit_country": event["circuit_country"],
            "openf1_session_key": int(event["openf1_session_key"]),
            "openf1_weather_observations": len(weather),
            "openf1_rain_observations": sum(is_rain(item.get("rainfall")) for item in weather),
            "openf1_any_rain": any(is_rain(item.get("rainfall")) for item in weather),
            "openf1_race_control_messages": len(control),
            "openf1_safety_car_messages": sum(
                "SAFETY CAR" in message and "VIRTUAL SAFETY CAR" not in message
                for message in messages
            ),
            "openf1_virtual_safety_car_messages": sum(
                "VIRTUAL SAFETY CAR" in message for message in messages
            ),
            "openf1_red_flag_messages": sum("RED FLAG" in message for message in messages),
            "fastf1_available": bool(fastf1_weather),
            "fastf1_weather_observations": len(fastf1_weather),
            "fastf1_rain_observations": sum(is_rain(item.get("Rainfall")) for item in fastf1_weather),
            "fastf1_any_rain": any(is_rain(item.get("Rainfall")) for item in fastf1_weather),
        }
        for measure in OPENF1_MEASURES:
            row.update(numeric_summary(weather, measure, f"openf1_{measure}"))
        for source_key, output_key in FASTF1_MEASURES:
            row.update(numeric_summary(fastf1_weather, source_key, f"fastf1_{output_key}"))
        output.append(row)

    if len(output) != len(events) or len({row["event_id"] for row in output}) != len(output):
        raise ValueError("Event context must contain exactly one row per event")
    if any(row["openf1_weather_observations"] == 0 for row in output):
        raise ValueError("An OpenF1 event has no weather observations")

    write_csv(args.output, COLUMNS, output)
    manifest = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_file": args.output.as_posix(), "rows": len(output),
        "unique_event_ids": True,
        "openf1_weather_observations": sum(row["openf1_weather_observations"] for row in output),
        "openf1_race_control_messages": sum(row["openf1_race_control_messages"] for row in output),
        "events_with_openf1_rain": sum(row["openf1_any_rain"] for row in output),
        "fastf1_events": sum(row["fastf1_available"] for row in output),
        "fastf1_weather_observations": sum(row["fastf1_weather_observations"] for row in output),
        "note": "Safety-car, VSC, and red-flag values count matching messages, not unique periods.",
        "columns": list(COLUMNS),
    }
    write_json(args.manifest, manifest)
    print(f"Event context rows: {len(output)}")
    print(f"OpenF1 weather observations: {manifest['openf1_weather_observations']}")
    print(f"FastF1 events represented: {manifest['fastf1_events']}")


if __name__ == "__main__":
    main()
