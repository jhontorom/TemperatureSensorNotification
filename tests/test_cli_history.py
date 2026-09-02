from zoneinfo import ZoneInfo

from room_monitor.cli_history import (
    format_local_timestamp,
    local_timestamp_to_utc,
    main,
)
from room_monitor.database import initialize_database, save_sensor_reading


def test_history_cli_displays_recent_measurements(tmp_path, capsys):
    path = tmp_path / "temperature_monitor.db"
    initialize_database(path)
    save_sensor_reading(74.2, 48.0, path, timestamp="2026-08-30 14:01:00")

    result = main(["--database", str(path), "--limit", "10"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Timestamp" in output
    assert "Temperature" in output
    assert "Timestamp (local)" in output
    assert "69.5 F" in output
    assert "74.2 F" not in output
    assert "48.0 %" in output


def test_utc_storage_timestamp_is_displayed_in_detroit_local_time():
    detroit = ZoneInfo("America/Detroit")

    result = format_local_timestamp("2026-09-02 01:23:25", detroit)

    assert result == "2026-09-01 21:23:25 EDT"


def test_local_date_range_is_converted_to_utc_for_querying():
    detroit = ZoneInfo("America/Detroit")

    result = local_timestamp_to_utc("2026-09-01 21:23:25", detroit)

    assert result == "2026-09-02 01:23:25"
