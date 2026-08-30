"""Room monitor process entry point."""

from __future__ import annotations

import errno
import hashlib
import logging
import socket

from room_monitor.config import RuntimeConfig, load_runtime_config
from room_monitor.telegram_bot import build_application


class RedactingFormatter(logging.Formatter):
    """Remove the configured bot token from complete rendered log entries."""

    def __init__(self, token: str) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s: %(message)s")
        self._token = token

    def format(self, record: logging.LogRecord) -> str:
        return super().format(record).replace(self._token, "[REDACTED]")


def configure_logging(config: RuntimeConfig) -> None:
    level_name = config.log_level.upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        raise ValueError(f"Invalid log level: {config.log_level}")

    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter(config.telegram_bot_token))
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def acquire_instance_lock(token: str) -> socket.socket:
    """Reserve a Linux abstract socket so only one process polls this bot."""
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    lock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        lock.bind(f"\0room-monitor-{token_hash}")
    except OSError as exc:
        lock.close()
        if exc.errno == errno.EADDRINUSE:
            raise RuntimeError("Another room monitor instance is already running") from exc
        raise
    return lock


def main() -> None:
    config = load_runtime_config()
    configure_logging(config)
    instance_lock = acquire_instance_lock(config.telegram_bot_token)
    logging.getLogger(__name__).info("Starting room monitor Telegram bot")
    try:
        build_application(config).run_polling(allowed_updates=["message"])
    finally:
        instance_lock.close()


if __name__ == "__main__":
    main()
