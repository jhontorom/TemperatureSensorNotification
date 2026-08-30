"""Room monitor process entry point."""

from __future__ import annotations

import logging

from room_monitor.config import load_runtime_config
from room_monitor.telegram_bot import build_application


def main() -> None:
    config = load_runtime_config()
    logging.basicConfig(
        level=config.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger(__name__).info("Starting room monitor Telegram bot")
    build_application(config).run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
