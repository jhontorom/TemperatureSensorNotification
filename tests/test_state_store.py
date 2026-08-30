import json

import pytest

from room_monitor.alerts import AlertState
from room_monitor.state_store import JsonStateStore, StatePersistenceError
from room_monitor.thresholds import RangeState


def test_missing_state_file_loads_normal_state(tmp_path):
    store = JsonStateStore(tmp_path / "state.json")

    assert store.load() == AlertState()


def test_state_round_trip_uses_versioned_json_and_restrictive_permissions(tmp_path):
    path = tmp_path / "nested" / "state.json"
    store = JsonStateStore(path)
    expected = AlertState(RangeState.HIGH, RangeState.LOW)

    store.save(expected)

    assert store.load() == expected
    assert json.loads(path.read_text()) == {
        "version": 1,
        "temperature": "high",
        "humidity": "low",
    }
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "contents",
    [
        "not-json",
        '{"version":99,"temperature":"normal","humidity":"normal"}',
        '{"version":1,"temperature":"invalid","humidity":"normal"}',
        '{"version":1,"temperature":"normal"}',
    ],
)
def test_corrupt_or_unsupported_state_recovers_as_normal(tmp_path, contents, caplog):
    path = tmp_path / "state.json"
    path.write_text(contents)

    state = JsonStateStore(path).load()

    assert state == AlertState()
    assert "Ignoring invalid alert state file" in caplog.text


def test_failed_atomic_replace_preserves_previous_state(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    store = JsonStateStore(path)
    original = AlertState(RangeState.LOW, RangeState.NORMAL)
    store.save(original)
    monkeypatch.setattr("room_monitor.state_store.os.replace", lambda *_: (_ for _ in ()).throw(OSError("disk error")))

    with pytest.raises(StatePersistenceError, match="Unable to save"):
        store.save(AlertState(RangeState.HIGH, RangeState.HIGH))

    assert store.load() == original
    assert list(tmp_path.glob(".alert-state-*")) == []
