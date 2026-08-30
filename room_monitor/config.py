"""Runtime configuration for the room monitoring app."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RuntimeConfig:
    telegram_bot_token: str = field(repr=False)
    authorized_chat_id: int
    i2c_bus: int
    i2c_address: int
    log_level: str = "INFO"


def _get_env_int(name: str, default: int | None = None) -> int | None:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value, 0)


def load_runtime_config() -> RuntimeConfig:
    token = os.getenv("ROOM_MONITOR_TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("ROOM_MONITOR_TELEGRAM_BOT_TOKEN is required")

    chat_id_raw = os.getenv("ROOM_MONITOR_AUTHORIZED_CHAT_ID")
    if chat_id_raw is None:
        raise ValueError("ROOM_MONITOR_AUTHORIZED_CHAT_ID is required")

    bus = _get_env_int("ROOM_MONITOR_I2C_BUS", 1)
    address = _get_env_int("ROOM_MONITOR_I2C_ADDRESS", 0x40)
    if bus is None or address is None:
        raise ValueError("I2C configuration must be integers")

    return RuntimeConfig(
        telegram_bot_token=token,
        authorized_chat_id=int(chat_id_raw),
        i2c_bus=bus,
        i2c_address=address,
        log_level=os.getenv("ROOM_MONITOR_LOG_LEVEL", "INFO"),
    )
