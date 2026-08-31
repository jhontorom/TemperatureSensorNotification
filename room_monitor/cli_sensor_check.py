"""Command-line sensor check used as a basic smoke test."""

from __future__ import annotations

import argparse
import logging
import sys

import smbus2

from room_monitor.sensor import SensorReadError, read_si7021_temperature_humidity


def parse_int_or_hex(value: str) -> int:
    return int(value, 0)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Read the Si7021 values for a quick sanity check.")
    parser.add_argument("--bus", type=int, default=1, help="I2C bus number")
    parser.add_argument("--address", type=parse_int_or_hex, default=0x40, help="Si7021 I2C address, e.g. 0x40 or 64")
    args = parser.parse_args()

    try:
        with smbus2.SMBus(args.bus) as bus:
            reading = read_si7021_temperature_humidity(bus, args.address)
    except (OSError, SensorReadError) as exc:
        logging.getLogger(__name__).error("Unable to read Si7021: %s", exc)
        return 1

    print(
        f"Temperature: {reading.calibrated_temperature_c:.2f} C / "
        f"{reading.calibrated_temperature_f:.2f} F (calibrated)"
    )
    print(
        f"Raw temperature: {reading.raw_temperature_c:.2f} C / "
        f"{reading.raw_temperature_f:.2f} F"
    )
    print(f"Humidity: {reading.humidity_pct:.2f} %")
    return 0


if __name__ == "__main__":
    sys.exit(main())
