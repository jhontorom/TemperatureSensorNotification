"""Alert threshold logic for room readings."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RangeState(str, Enum):
    NORMAL = "normal"
    LOW = "low"
    HIGH = "high"


@dataclass(frozen=True)
class ReadingSummary:
    temperature_c: float
    humidity_pct: float
    issues: list[str] = field(default_factory=list)
    is_alerting: bool = False


def summarize_reading(temperature_c: float, humidity_pct: float) -> ReadingSummary:
    """Return whether the current values are in-range or in an alert state."""
    issues: list[str] = []

    temperature_state = classify_temperature(temperature_c)
    humidity_state = classify_humidity(humidity_pct)

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


def classify_temperature(temperature_c: float) -> RangeState:
    if temperature_c < 10.0:
        return RangeState.LOW
    if temperature_c > 27.0:
        return RangeState.HIGH
    return RangeState.NORMAL


def classify_humidity(humidity_pct: float) -> RangeState:
    if humidity_pct < 30.0:
        return RangeState.LOW
    if humidity_pct > 60.0:
        return RangeState.HIGH
    return RangeState.NORMAL
