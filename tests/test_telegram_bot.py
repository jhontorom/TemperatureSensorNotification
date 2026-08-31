from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from room_monitor.sensor import SensorReadError, SensorReading
from room_monitor.config import RuntimeConfig
from room_monitor.telegram_bot import (
    HELP_MESSAGE,
    HUMIDITY_USAGE,
    SENSOR_UNAVAILABLE_MESSAGE,
    START_MESSAGE,
    TEMPERATURE_USAGE,
    THRESHOLD_SAVE_FAILED,
    RoomMonitorBot,
    build_application,
    format_thresholds_message,
    handle_application_error,
)
from room_monitor.threshold_store import ThresholdManager, ThresholdPersistenceError
from room_monitor.thresholds import AlertThresholds


AUTHORIZED_CHAT_ID = 123456789


@pytest.fixture(autouse=True)
def run_sensor_thread_inline(monkeypatch):
    async def run_inline(function, *args):
        return function(*args)

    monkeypatch.setattr("room_monitor.telegram_bot.asyncio.to_thread", run_inline)


def make_update(chat_id=AUTHORIZED_CHAT_ID):
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(effective_chat=SimpleNamespace(id=chat_id), effective_message=message)


class MemoryThresholdStore:
    def __init__(self):
        self.thresholds = AlertThresholds()
        self.failure = None

    def load(self):
        return self.thresholds

    def save(self, thresholds):
        if self.failure:
            raise self.failure
        self.thresholds = thresholds


def make_bot(sensor_reader=Mock()):
    return RoomMonitorBot(AUTHORIZED_CHAT_ID, sensor_reader, ThresholdManager(MemoryThresholdStore()))


@pytest.mark.asyncio
async def test_start_replies_to_authorized_chat():
    update = make_update()
    bot = make_bot()

    await bot.start(update, None)

    update.effective_message.reply_text.assert_awaited_once_with(START_MESSAGE)


@pytest.mark.asyncio
async def test_help_replies_to_authorized_chat():
    update = make_update()
    bot = make_bot()

    await bot.help(update, None)

    update.effective_message.reply_text.assert_awaited_once_with(HELP_MESSAGE)


@pytest.mark.asyncio
async def test_status_reports_celsius_fahrenheit_and_humidity():
    update = make_update()
    sensor_reader = Mock(return_value=SensorReading(temperature_c=25.0, humidity_pct=48.5))
    bot = make_bot(sensor_reader)

    await bot.status(update, None)

    sensor_reader.assert_called_once_with()
    message = update.effective_message.reply_text.await_args.args[0]
    assert "23.42 C" in message
    assert "74.15 F" in message
    assert "48.50%" in message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command", ["start", "help", "status", "thresholds", "set_temperature", "set_humidity"]
)
async def test_unauthorized_chat_receives_no_reply_or_sensor_data(command):
    update = make_update(chat_id=999)
    sensor_reader = Mock(return_value=SensorReading(temperature_c=25.0, humidity_pct=48.5))
    bot = make_bot(sensor_reader)

    await getattr(bot, command)(update, None)

    update.effective_message.reply_text.assert_not_awaited()
    sensor_reader.assert_not_called()


@pytest.mark.asyncio
async def test_status_reports_temporary_failure_without_crashing():
    update = make_update()
    sensor_reader = Mock(side_effect=SensorReadError("sensor disconnected"))
    bot = make_bot(sensor_reader)

    await bot.status(update, None)

    update.effective_message.reply_text.assert_awaited_once_with(SENSOR_UNAVAILABLE_MESSAGE)


@pytest.mark.asyncio
async def test_thresholds_reports_current_values():
    update = make_update()
    bot = make_bot()

    await bot.thresholds(update, None)

    update.effective_message.reply_text.assert_awaited_once_with(
        format_thresholds_message(AlertThresholds())
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command", "args", "expected"),
    [
        ("set_temperature", ["12.5", "26"], "Temperature: 12.5 C to 26 C"),
        ("set_humidity", ["35", "55.5"], "Humidity: 35% to 55.5%"),
    ],
)
async def test_authorized_threshold_update_is_persisted_and_confirmed(command, args, expected):
    update = make_update()
    bot = make_bot()

    await getattr(bot, command)(update, SimpleNamespace(args=args))

    assert expected in update.effective_message.reply_text.await_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command", "args", "usage"),
    [
        ("set_temperature", [], TEMPERATURE_USAGE),
        ("set_temperature", ["cold", "25"], TEMPERATURE_USAGE),
        ("set_humidity", ["60", "30"], HUMIDITY_USAGE),
    ],
)
async def test_invalid_threshold_command_keeps_previous_values(command, args, usage):
    update = make_update()
    bot = make_bot()

    await getattr(bot, command)(update, SimpleNamespace(args=args))

    assert update.effective_message.reply_text.await_args.args[0].startswith(usage)


@pytest.mark.asyncio
async def test_threshold_persistence_failure_reports_error_and_keeps_previous_values():
    update = make_update()
    store = MemoryThresholdStore()
    store.failure = ThresholdPersistenceError("disk unavailable")
    manager = ThresholdManager(store)
    bot = RoomMonitorBot(AUTHORIZED_CHAT_ID, Mock(), manager)

    await bot.set_temperature(update, SimpleNamespace(args=["12", "25"]))

    update.effective_message.reply_text.assert_awaited_once_with(THRESHOLD_SAVE_FAILED)
    assert manager.get() == AlertThresholds()


@pytest.mark.asyncio
async def test_application_error_log_excludes_update_and_error_details(caplog):
    update = "private update contents"
    context = SimpleNamespace(error=RuntimeError("private error details"))

    await handle_application_error(update, context)

    assert "Telegram operation failed: RuntimeError" in caplog.text
    assert update not in caplog.text
    assert "private error details" not in caplog.text


def test_application_configures_ipv4_for_api_and_polling(monkeypatch, tmp_path):
    requests = [Mock(name="api_request"), Mock(name="polling_request")]
    builder = Mock()
    builder.token.return_value = builder
    builder.request.return_value = builder
    builder.get_updates_request.return_value = builder
    builder.build.return_value = Mock()
    monkeypatch.setattr("room_monitor.telegram_bot.ApplicationBuilder", Mock(return_value=builder))
    monkeypatch.setattr("room_monitor.telegram_bot.build_ipv4_request", Mock(side_effect=requests))
    register_jobs = Mock()
    monkeypatch.setattr("room_monitor.telegram_bot.register_monitoring_jobs", register_jobs)
    config = RuntimeConfig(
        "secret",
        AUTHORIZED_CHAT_ID,
        1,
        0x40,
        alert_state_file=tmp_path / "alert-state.json",
        threshold_file=tmp_path / "thresholds.json",
        database_file=tmp_path / "data" / "temperature_monitor.db",
    )

    build_application(config)

    builder.request.assert_called_once_with(requests[0])
    builder.get_updates_request.assert_called_once_with(requests[1])
    assert builder.build.return_value.add_handler.call_count == 6
    builder.build.return_value.add_error_handler.assert_called_once_with(handle_application_error)
    register_jobs.assert_called_once()
    assert register_jobs.call_args.args[0] is builder.build.return_value.job_queue
    assert register_jobs.call_args.args[2] == 60
    assert register_jobs.call_args.kwargs["measurement_interval_seconds"] == 60
