import json

import pytest

from room_monitor.threshold_store import JsonThresholdStore, ThresholdManager
from room_monitor.thresholds import AlertThresholds


@pytest.mark.parametrize(
    "thresholds",
    [
        AlertThresholds(-40.0, 125.0, 0.0, 100.0),
        AlertThresholds(12.5, 26.0, 35.0, 55.5),
    ],
)
def test_valid_threshold_boundaries(thresholds):
    assert thresholds.temperature_low_c < thresholds.temperature_high_c
    assert thresholds.humidity_low_pct < thresholds.humidity_high_pct


@pytest.mark.parametrize(
    "values",
    [
        (-41.0, 27.0, 30.0, 60.0),
        (10.0, 126.0, 30.0, 60.0),
        (27.0, 10.0, 30.0, 60.0),
        (10.0, 27.0, -1.0, 60.0),
        (10.0, 27.0, 30.0, 101.0),
        (10.0, 27.0, 60.0, 30.0),
        (float("nan"), 27.0, 30.0, 60.0),
    ],
)
def test_invalid_thresholds_are_rejected(values):
    with pytest.raises(ValueError):
        AlertThresholds(*values)


def test_thresholds_round_trip_with_restricted_permissions(tmp_path):
    path = tmp_path / "thresholds.json"
    expected = AlertThresholds(12.5, 26.0, 35.0, 55.5)
    store = JsonThresholdStore(path)

    store.save(expected)

    assert store.load() == expected
    assert json.loads(path.read_text())["version"] == 1
    assert path.stat().st_mode & 0o777 == 0o600


def test_manager_restores_saved_updates_after_restart(tmp_path):
    store = JsonThresholdStore(tmp_path / "thresholds.json")
    manager = ThresholdManager(store)
    manager.set_temperature(12.0, 26.0)
    manager.set_humidity(35.0, 55.0)

    restarted = ThresholdManager(store)

    assert restarted.get() == AlertThresholds(12.0, 26.0, 35.0, 55.0)


@pytest.mark.parametrize("contents", ["bad json", '{"version":99}', '{"version":1}'])
def test_invalid_threshold_file_uses_safe_defaults(tmp_path, contents, caplog):
    path = tmp_path / "thresholds.json"
    path.write_text(contents)

    thresholds = JsonThresholdStore(path).load()

    assert thresholds == AlertThresholds()
    assert "Ignoring invalid threshold file" in caplog.text
