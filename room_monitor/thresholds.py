"""Alert threshold logic for room readings."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math


class RangeState(str, Enum):
    NORMAL = "normal"
    LOW = "low"
    HIGH = "high"


@dataclass(frozen=True)
class AlertThresholds:
    temperature_low_c: float = 10.0
    temperature_high_c: float = 27.0
    humidity_low_pct: float = 30.0
    humidity_high_pct: float = 60.0

    def __post_init__(self) -> None:
        values = (
            self.temperature_low_c,
            self.temperature_high_c,
            self.humidity_low_pct,
            self.humidity_high_pct,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Thresholds must be finite numbers")
        if not -40.0 <= self.temperature_low_c < self.temperature_high_c <= 125.0:
            raise ValueError("Temperature thresholds must satisfy -40 <= low < high <= 125 C")
        if not 0.0 <= self.humidity_low_pct < self.humidity_high_pct <= 100.0:
            raise ValueError("Humidity thresholds must satisfy 0 <= low < high <= 100%")


DEFAULT_THRESHOLDS = AlertThresholds()


@dataclass(frozen=True)
class ReadingSummary:
    temperature_c: float
    humidity_pct: float
    issues: list[str] = field(default_factory=list)
    is_alerting: bool = False


def summarize_reading(
    temperature_c: float,
    humidity_pct: float,
    thresholds: AlertThresholds = DEFAULT_THRESHOLDS,
) -> ReadingSummary:
    """Return whether the current values are in-range or in an alert state."""
    issues: list[str] = []

    temperature_state = classify_temperature(temperature_c, thresholds)
    humidity_state = classify_humidity(humidity_pct, thresholds)

    if temperature_state is RangeState.LOW:
        issues.append("temperature_low")
    elif temperature_state is RangeState.HIGH:
        issues.append("temperature_high")

    if humidity_state is RangeState.LOW:
        issues.append("humidity_low")
    elif humidity_state is RangeState.HIGH:
        issues.append("humidity_high")

    return ReadingSummary(
        temperature_c=temperature_c,
        humidity_pct=humidity_pct,
        issues=issues,
        is_alerting=bool(issues),
    )


def classify_temperature(
    temperature_c: float, thresholds: AlertThresholds = DEFAULT_THRESHOLDS
) -> RangeState:
    if temperature_c < thresholds.temperature_low_c:
        return RangeState.LOW
    if temperature_c > thresholds.temperature_high_c:
        return RangeState.HIGH
    return RangeState.NORMAL


def classify_humidity(
    humidity_pct: float, thresholds: AlertThresholds = DEFAULT_THRESHOLDS
) -> RangeState:
    if humidity_pct < thresholds.humidity_low_pct:
        return RangeState.LOW
    if humidity_pct > thresholds.humidity_high_pct:
        return RangeState.HIGH
    return RangeState.NORMAL
