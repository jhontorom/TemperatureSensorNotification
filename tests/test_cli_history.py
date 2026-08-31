from room_monitor.cli_history import main
from room_monitor.database import initialize_database, save_sensor_reading


def test_history_cli_displays_recent_measurements(tmp_path, capsys):
    path = tmp_path / "temperature_monitor.db"
    initialize_database(path)
    save_sensor_reading(74.2, 48.0, path, timestamp="2026-08-30 14:01:00")

    result = main(["--database", str(path), "--limit", "10"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Timestamp" in output
    assert "Calibrated" in output
    assert "Raw" in output
    assert "2026-08-30 14:01:00" in output
    assert "71.4 F" in output
    assert "74.2 F" in output
    assert "48.0 %" in output
