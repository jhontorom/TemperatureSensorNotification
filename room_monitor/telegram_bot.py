"""Authorized Telegram commands for the room monitor."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
import threading

import httpx
import smbus2
from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest

from room_monitor.config import RuntimeConfig
from room_monitor.alerts import AlertTracker
from room_monitor.monitoring import MonitoringService, format_status_message, register_monitoring_jobs
from room_monitor.sensor import (
    SensorReading,
    SensorReadError,
    read_si7021_temperature_humidity,
)
from room_monitor.state_store import JsonStateStore


LOGGER = logging.getLogger(__name__)
START_MESSAGE = "Room monitor is ready. Use /status for the current reading or /help for available commands."
HELP_MESSAGE = "Available commands:\n/start - Show the welcome message\n/help - Show this help\n/status - Read temperature and humidity"
SENSOR_UNAVAILABLE_MESSAGE = "The room sensor is temporarily unavailable. Please try again shortly."


def build_ipv4_request() -> HTTPXRequest:
    """Build a Telegram request transport that avoids unusable IPv6 routes."""
    transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
    return HTTPXRequest(httpx_kwargs={"transport": transport})


async def handle_application_error(_update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Telegram callback and polling failures without including private data."""
    error = context.error
    error_name = type(error).__name__ if error is not None else "UnknownError"
    LOGGER.warning("Telegram operation failed: %s", error_name)


class RoomMonitorBot:
    """Telegram command handlers restricted to one configured chat."""

    def __init__(self, authorized_chat_id: int, sensor_reader: Callable[[], SensorReading]) -> None:
        self._authorized_chat_id = authorized_chat_id
        self._sensor_reader = sensor_reader

    def is_authorized(self, update: Update) -> bool:
        chat = update.effective_chat
        return chat is not None and chat.id == self._authorized_chat_id

    async def start(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_authorized(update):
            self._log_unauthorized(update)
            return
        if update.effective_message is not None:
            await update.effective_message.reply_text(START_MESSAGE)

    async def help(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_authorized(update):
            self._log_unauthorized(update)
            return
        if update.effective_message is not None:
            await update.effective_message.reply_text(HELP_MESSAGE)

    async def status(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_authorized(update):
            self._log_unauthorized(update)
            return
        if update.effective_message is None:
            return

        try:
            reading = await asyncio.to_thread(self._sensor_reader)
        except (OSError, SensorReadError) as exc:
            LOGGER.warning("Unable to serve /status because the sensor read failed: %s", exc)
            await update.effective_message.reply_text(SENSOR_UNAVAILABLE_MESSAGE)
            return

        await update.effective_message.reply_text(format_status_message(reading))

    def _log_unauthorized(self, update: Update) -> None:
        LOGGER.warning("Ignored Telegram command from an unauthorized chat")


def build_application(config: RuntimeConfig) -> Application:
    """Build the Telegram application and register room-monitor commands."""

    sensor_lock = threading.Lock()

    def read_sensor() -> SensorReading:
        with sensor_lock:
            with smbus2.SMBus(config.i2c_bus) as bus:
                return read_si7021_temperature_humidity(bus, config.i2c_address)

    commands = RoomMonitorBot(config.authorized_chat_id, read_sensor)
    tracker = AlertTracker(JsonStateStore(config.alert_state_file))
    application = (
        ApplicationBuilder()
        .token(config.telegram_bot_token)
        .request(build_ipv4_request())
        .get_updates_request(build_ipv4_request())
        .build()
    )
    application.add_handler(CommandHandler("start", commands.start))
    application.add_handler(CommandHandler("help", commands.help))
    application.add_handler(CommandHandler("status", commands.status))
    application.add_error_handler(handle_application_error)
    if application.job_queue is None:
        raise RuntimeError("Telegram JobQueue support is not installed")
    service = MonitoringService(read_sensor, tracker, config.authorized_chat_id)
    register_monitoring_jobs(application.job_queue, service, config.alert_check_interval_seconds)
    return application
