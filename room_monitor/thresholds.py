"""Alert threshold logic for room readings."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReadingSummary:
    temperature_c: float
    humidity_pct: float
    issues: list[str] = field(default_factory=list)
    is_alerting: bool = False


def summarize_reading(temperature_c: float, humidity_pct: float) -> ReadingSummary:
    """Return whether the current values are in-range or in an alert state."""
    issues: list[str] = []

    if temperature_c < 10.0:
        issues.append("temperature_low")
    elif temperature_c > 27.0:
        issues.append("temperature_high")

    if humidity_pct < 30.0:
        issues.append("humidity_low")
    elif humidity_pct > 60.0:
        issues.append("humidity_high")

    return ReadingSummary(
        temperature_c=temperature_c,
        humidity_pct=humidity_pct,
        issues=issues,
        is_alerting=bool(issues),
    )
