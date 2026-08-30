import pytest

from room_monitor.config import load_runtime_config
from room_monitor import sensor
from room_monitor.sensor import (
    InvalidMeasurementError,
    SensorReadError,
    read_si7021_temperature_humidity,
    temperature_to_fahrenheit,
)
from room_monitor.thresholds import summarize_reading


def test_temperature_conversion_is_correct():
    assert temperature_to_fahrenheit(0.0) == 32.0
    assert round(temperature_to_fahrenheit(20.0), 2) == 68.0
    assert round(temperature_to_fahrenheit(25.0), 2) == 77.0


def test_threshold_summary_marks_alerts_and_recovery():
    low_temp = summarize_reading(9.0, 45.0)
    assert low_temp.is_alerting is True
    assert "temperature_low" in low_temp.issues

    normal = summarize_reading(21.0, 45.0)
    assert normal.is_alerting is False
    assert not normal.issues

    high_humidity = summarize_reading(22.0, 65.0)
    assert high_humidity.is_alerting is True
    assert "humidity_high" in high_humidity.issues

    recovery = summarize_reading(22.0, 45.0)
    assert recovery.is_alerting is False
    assert not recovery.issues


def test_runtime_config_reads_required_environment_values(monkeypatch):
    monkeypatch.setenv("ROOM_MONITOR_TELEGRAM_BOT_TOKEN", "example-token")
    monkeypatch.setenv("ROOM_MONITOR_AUTHORIZED_CHAT_ID", "123456789")
    monkeypatch.setenv("ROOM_MONITOR_I2C_BUS", "1")
    monkeypatch.setenv("ROOM_MONITOR_I2C_ADDRESS", "0x40")
    monkeypatch.setenv("ROOM_MONITOR_ALERT_STATE_FILE", "/tmp/room-monitor-test-state.json")
    monkeypatch.setenv("ROOM_MONITOR_ALERT_CHECK_INTERVAL_SECONDS", "60")

    config = load_runtime_config()

    assert config.telegram_bot_token == "example-token"
    assert config.authorized_chat_id == 123456789
    assert config.i2c_bus == 1
    assert config.i2c_address == 0x40
    assert str(config.alert_state_file) == "/tmp/room-monitor-test-state.json"
    assert config.alert_check_interval_seconds == 60
    assert "example-token" not in repr(config)


def test_runtime_config_rejects_invalid_alert_interval(monkeypatch):
    monkeypatch.setenv("ROOM_MONITOR_TELEGRAM_BOT_TOKEN", "example-token")
    monkeypatch.setenv("ROOM_MONITOR_AUTHORIZED_CHAT_ID", "123456789")
    monkeypatch.setenv("ROOM_MONITOR_ALERT_CHECK_INTERVAL_SECONDS", "0")

    with pytest.raises(ValueError, match="must be at least 1"):
        load_runtime_config()


class FakeReadMessage(list):
    def __init__(self, address, length):
        super().__init__([0] * length)
        self.address = address


class FakeI2CMessageFactory:
    @staticmethod
    def write(address, data):
        return ("write", address, list(data))

    @staticmethod
    def read(address, length):
        return FakeReadMessage(address, length)


class FakeBus:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def i2c_rdwr(self, message):
        if isinstance(message, tuple):
            self.calls.append(message)
            return

        self.calls.append(("read", message.address, len(message)))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        message[:] = response


def with_crc(high_byte, low_byte):
    data = [high_byte, low_byte]
    return [*data, sensor._crc8(data)]


def test_si7021_uses_no_hold_raw_i2c_commands_and_converts_readings(monkeypatch):
    # Raw values that represent approximately 50% RH and 25 C.
    humidity_raw = round((50.0 + 6.0) * 65536.0 / 125.0)
    temperature_raw = round((25.0 + 46.85) * 65536.0 / 175.72)
    bus = FakeBus([with_crc(humidity_raw >> 8, humidity_raw & 0xFF), with_crc(temperature_raw >> 8, temperature_raw & 0xFF)])
    monkeypatch.setattr(sensor.smbus2, "i2c_msg", FakeI2CMessageFactory)
    monkeypatch.setattr(sensor.time, "sleep", lambda _: None)

    reading = read_si7021_temperature_humidity(bus)

    assert bus.calls == [
        ("write", 0x40, [0xF5]),
        ("read", 0x40, 3),
        ("write", 0x40, [0xF3]),
        ("read", 0x40, 3),
    ]
    assert reading.humidity_pct == pytest.approx(50.0, abs=0.01)
    assert reading.temperature_c == pytest.approx(25.0, abs=0.01)


def test_si7021_rejects_humidity_outside_physical_range(monkeypatch):
    temperature_raw = round((20.0 + 46.85) * 65536.0 / 175.72)
    bus = FakeBus([with_crc(0xFF, 0xFF), with_crc(temperature_raw >> 8, temperature_raw & 0xFF)])
    monkeypatch.setattr(sensor.smbus2, "i2c_msg", FakeI2CMessageFactory)
    monkeypatch.setattr(sensor.time, "sleep", lambda _: None)

    with pytest.raises(InvalidMeasurementError, match="Humidity measurement out of range"):
        read_si7021_temperature_humidity(bus)


def test_si7021_rejects_temperature_outside_sensor_range(monkeypatch):
    humidity_raw = round((50.0 + 6.0) * 65536.0 / 125.0)
    bus = FakeBus([with_crc(humidity_raw >> 8, humidity_raw & 0xFF), with_crc(0xFF, 0xFF)])
    monkeypatch.setattr(sensor.smbus2, "i2c_msg", FakeI2CMessageFactory)
    monkeypatch.setattr(sensor.time, "sleep", lambda _: None)

    with pytest.raises(InvalidMeasurementError, match="Temperature measurement out of range"):
        read_si7021_temperature_humidity(bus)


def test_si7021_wraps_i2c_read_failure(monkeypatch):
    bus = FakeBus([OSError(121, "Remote I/O error")] * 3)
    monkeypatch.setattr(sensor.smbus2, "i2c_msg", FakeI2CMessageFactory)
    monkeypatch.setattr(sensor.time, "sleep", lambda _: None)

    with pytest.raises(SensorReadError, match="0x40") as error:
        read_si7021_temperature_humidity(bus)

    assert isinstance(error.value.__cause__, OSError)


def test_si7021_retries_a_transient_i2c_failure(monkeypatch):
    humidity_raw = round((45.0 + 6.0) * 65536.0 / 125.0)
    temperature_raw = round((21.0 + 46.85) * 65536.0 / 175.72)
    bus = FakeBus(
        [
            OSError(121, "Remote I/O error"),
            with_crc(humidity_raw >> 8, humidity_raw & 0xFF),
            with_crc(temperature_raw >> 8, temperature_raw & 0xFF),
        ]
    )
    monkeypatch.setattr(sensor.smbus2, "i2c_msg", FakeI2CMessageFactory)
    monkeypatch.setattr(sensor.time, "sleep", lambda _: None)

    reading = read_si7021_temperature_humidity(bus)

    assert reading.temperature_c == pytest.approx(21.0, abs=0.01)
    assert reading.humidity_pct == pytest.approx(45.0, abs=0.01)


def test_si7021_rejects_bad_checksum_after_bounded_retries(monkeypatch):
    bus = FakeBus([[0x66, 0x66, 0x00]] * 3)
    monkeypatch.setattr(sensor.smbus2, "i2c_msg", FakeI2CMessageFactory)
    monkeypatch.setattr(sensor.time, "sleep", lambda _: None)

    with pytest.raises(SensorReadError, match="after 3 attempt") as error:
        read_si7021_temperature_humidity(bus)

    assert "checksum" in str(error.value.__cause__).lower()


def test_si7021_rejects_incomplete_response(monkeypatch):
    bus = FakeBus([[0x12, 0x34]] * 3)
    monkeypatch.setattr(sensor.smbus2, "i2c_msg", FakeI2CMessageFactory)
    monkeypatch.setattr(sensor.time, "sleep", lambda _: None)

    with pytest.raises(SensorReadError, match="incomplete measurement"):
        read_si7021_temperature_humidity(bus)


def test_si7021_validates_retry_options():
    with pytest.raises(ValueError, match="attempts"):
        read_si7021_temperature_humidity(FakeBus([]), attempts=0)
    with pytest.raises(ValueError, match="retry_delay"):
        read_si7021_temperature_humidity(FakeBus([]), retry_delay_seconds=-1)
