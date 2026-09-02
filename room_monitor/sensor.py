"""Si7021 sensor support."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import math
import time

import smbus2


LOGGER = logging.getLogger(__name__)
DEFAULT_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_SECONDS = 0.1
TEMPERATURE_OFFSET_F = -4.66
TEMPERATURE_OFFSET_C = -2.55


class SensorReadError(RuntimeError):
    """Raised when a sensor read fails."""


class InvalidMeasurementError(SensorReadError):
    """Raised when a measured value falls outside valid ranges."""


class SensorChecksumError(SensorReadError):
    """Raised when the Si7021 response fails its CRC check."""


@dataclass(frozen=True)
class SensorReading:
    temperature_c: float
    humidity_pct: float

    @property
    def raw_temperature_c(self) -> float:
        return self.temperature_c

    @property
    def raw_temperature_f(self) -> float:
        return temperature_to_fahrenheit(self.raw_temperature_c)

    @property
    def calibrated_temperature_c(self) -> float:
        return calibrate_temperature_c(self.raw_temperature_c)

    @property
    def calibrated_temperature_f(self) -> float:
        return calibrate_temperature_f(self.raw_temperature_f)


def temperature_to_fahrenheit(celsius: float) -> float:
    return (celsius * 9.0 / 5.0) + 32.0


def calibrate_temperature_c(raw_temperature_c: float) -> float:
    return raw_temperature_c + TEMPERATURE_OFFSET_C


def calibrate_temperature_f(raw_temperature_f: float) -> float:
    return raw_temperature_f + TEMPERATURE_OFFSET_F


def read_si7021_temperature_humidity(
    bus: smbus2.SMBus,
    i2c_address: int = 0x40,
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
) -> SensorReading:
    """Read and validate temperature and relative humidity from the Si7021.

    Transient I2C and checksum failures are retried a bounded number of times.
    Invalid converted measurements are not retried because they indicate bad
    sensor data rather than a failed bus transaction.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds cannot be negative")

    for attempt in range(1, attempts + 1):
        try:
            return _read_once(bus, i2c_address)
        except InvalidMeasurementError:
            LOGGER.error("Si7021 returned an invalid measurement at address 0x%02x", i2c_address)
            raise
        except (OSError, ValueError, IndexError, SensorChecksumError) as exc:
            if attempt == attempts:
                raise SensorReadError(
                    f"Sensor read failed at address 0x{i2c_address:02x} after {attempts} attempt(s): {exc}"
                ) from exc
            LOGGER.warning(
                "Si7021 read attempt %d/%d failed at address 0x%02x: %s",
                attempt,
                attempts,
                i2c_address,
                exc,
            )
            time.sleep(retry_delay_seconds)

    raise AssertionError("unreachable")


def _read_once(bus: smbus2.SMBus, i2c_address: int) -> SensorReading:
    """Perform one complete Si7021 temperature and humidity read."""

    # The Si7021 does not expose register addresses. Send a no-hold measurement
    # command, wait for conversion, then perform a raw I2C read. ``*_data`` SMBus
    # calls are unsuitable because they add a register byte to the transaction.
    humidity_raw = _read_no_hold_measurement(bus, i2c_address, 0xF5)
    temp_raw = _read_no_hold_measurement(bus, i2c_address, 0xF3)

    humidity_code = ((humidity_raw[0] << 8) | humidity_raw[1]) & 0xFFFC
    temperature_code = ((temp_raw[0] << 8) | temp_raw[1]) & 0xFFFC
    humidity = humidity_code * 125.0 / 65536.0 - 6.0
    temperature = temperature_code * 175.72 / 65536.0 - 46.85

    _validate_measurements(temperature, humidity)
    return SensorReading(temperature_c=float(temperature), humidity_pct=float(humidity))


def _read_no_hold_measurement(bus: smbus2.SMBus, i2c_address: int, command: int) -> list[int]:
    """Issue a no-hold measurement command and return verified data bytes."""
    bus.i2c_rdwr(smbus2.i2c_msg.write(i2c_address, [command]))
    # The Si7021's maximum conversion time is below 13 ms.  Thirty milliseconds
    # gives the Pi scheduler and the sensor sufficient margin without busy waiting.
    time.sleep(0.03)
    response = smbus2.i2c_msg.read(i2c_address, 3)
    bus.i2c_rdwr(response)
    raw = list(response)
    if len(raw) != 3:
        raise ValueError("Si7021 returned an incomplete measurement")
    if _crc8(raw[:2]) != raw[2]:
        raise SensorChecksumError("Si7021 response checksum did not match")
    return raw[:2]


def _crc8(data: list[int]) -> int:
    """Return the Si7021 CRC-8 for two measurement bytes."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def _validate_measurements(temperature_c: float, humidity_pct: float) -> None:
    if not math.isfinite(temperature_c) or not -40.0 <= temperature_c <= 125.0:
        raise InvalidMeasurementError(f"Temperature measurement out of range: {temperature_c:.2f} C")
    if not math.isfinite(humidity_pct) or not 0.0 <= humidity_pct <= 100.0:
        raise InvalidMeasurementError(f"Humidity measurement out of range: {humidity_pct:.2f}%")
