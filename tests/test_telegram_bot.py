from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from room_monitor.sensor import SensorReadError, SensorReading
from room_monitor.config import RuntimeConfig
from room_monitor.telegram_bot import (
    HELP_MESSAGE,
    SENSOR_UNAVAILABLE_MESSAGE,
    START_MESSAGE,
    RoomMonitorBot,
    build_application,
    handle_application_error,
)


AUTHORIZED_CHAT_ID = 123456789


@pytest.fixture(autouse=True)
def run_sensor_thread_inline(monkeypatch):
    async def run_inline(function, *args):
        return function(*args)

    monkeypatch.setattr("room_monitor.telegram_bot.asyncio.to_thread", run_inline)


def make_update(chat_id=AUTHORIZED_CHAT_ID):
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(effective_chat=SimpleNamespace(id=chat_id), effective_message=message)


@pytest.mark.asyncio
async def test_start_replies_to_authorized_chat():
    update = make_update()
    bot = RoomMonitorBot(AUTHORIZED_CHAT_ID, Mock())

    await bot.start(update, None)

    update.effective_message.reply_text.assert_awaited_once_with(START_MESSAGE)


@pytest.mark.asyncio
async def test_help_replies_to_authorized_chat():
    update = make_update()
    bot = RoomMonitorBot(AUTHORIZED_CHAT_ID, Mock())

    await bot.help(update, None)

    update.effective_message.reply_text.assert_awaited_once_with(HELP_MESSAGE)


@pytest.mark.asyncio
async def test_status_reports_celsius_fahrenheit_and_humidity():
    update = make_update()
    sensor_reader = Mock(return_value=SensorReading(temperature_c=25.0, humidity_pct=48.5))
    bot = RoomMonitorBot(AUTHORIZED_CHAT_ID, sensor_reader)

    await bot.status(update, None)

    sensor_reader.assert_called_once_with()
    message = update.effective_message.reply_text.await_args.args[0]
    assert "25.00 C" in message
    assert "77.00 F" in message
    assert "48.50%" in message


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["start", "help", "status"])
async def test_unauthorized_chat_receives_no_reply_or_sensor_data(command):
    update = make_update(chat_id=999)
    sensor_reader = Mock(return_value=SensorReading(temperature_c=25.0, humidity_pct=48.5))
    bot = RoomMonitorBot(AUTHORIZED_CHAT_ID, sensor_reader)

    await getattr(bot, command)(update, None)

    update.effective_message.reply_text.assert_not_awaited()
    sensor_reader.assert_not_called()


@pytest.mark.asyncio
async def test_status_reports_temporary_failure_without_crashing():
    update = make_update()
    sensor_reader = Mock(side_effect=SensorReadError("sensor disconnected"))
    bot = RoomMonitorBot(AUTHORIZED_CHAT_ID, sensor_reader)

    await bot.status(update, None)

    update.effective_message.reply_text.assert_awaited_once_with(SENSOR_UNAVAILABLE_MESSAGE)


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
    )

    build_application(config)

    builder.request.assert_called_once_with(requests[0])
    builder.get_updates_request.assert_called_once_with(requests[1])
    builder.build.return_value.add_error_handler.assert_called_once_with(handle_application_error)
    register_jobs.assert_called_once()
    assert register_jobs.call_args.args[0] is builder.build.return_value.job_queue
    assert register_jobs.call_args.args[2] == 60
