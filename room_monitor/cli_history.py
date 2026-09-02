"""Display historical sensor readings from SQLite."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from room_monitor.database import (
    DEFAULT_DATABASE_PATH,
    DatabaseError,
    get_readings_between_dates,
    get_recent_readings,
    initialize_database,
)
from room_monitor.sensor import calibrate_temperature_f


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect stored room-monitor measurements")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--limit", type=int, default=20, help="number of recent rows to show")
    parser.add_argument("--start", help="inclusive start timestamp, for example 2026-08-30 08:00:00")
    parser.add_argument("--end", help="inclusive end timestamp, for example 2026-08-30 17:00:00")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    if bool(args.start) != bool(args.end):
        logging.error("--start and --end must be supplied together")
        return 2
    try:
        initialize_database(args.database)
        if args.start and args.end:
            readings = get_readings_between_dates(args.start, args.end, args.database)
        else:
            readings = list(reversed(get_recent_readings(args.limit, args.database)))
    except (DatabaseError, ValueError) as exc:
        logging.error("Unable to display history: %s", exc)
        return 1

    print(f"{'Timestamp (UTC)':<24} {'Temperature':>12} {'Humidity':>11}")
    for reading in readings:
        print(
            f"{reading.timestamp:<24} "
            f"{calibrate_temperature_f(reading.raw_temperature_f):>8.1f} F "
            f"{reading.humidity:>8.1f} %"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
