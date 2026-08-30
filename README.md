# Room Monitor

A Raspberry Pi 5 room-monitoring application for the SparkFun Si7021 humidity and temperature sensor.

## Features

- Reads temperature and humidity from the Si7021 over I²C bus 1 at address 0x40.
- Exposes the current status and supports Telegram commands.
- Detects alert transitions and persists state across restarts.
- Runs as a `systemd` service on Raspberry Pi OS.
- Uses a permission-restricted environment file for secrets.

## Installation

1. Install Python 3 and dependencies:
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-pip python3-venv
   python3 -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Copy the example environment file to a secure location outside the repository, for example `/etc/room-monitor.env`.
3. Fill in the real values there. Do not commit secrets to the repository.

## Configuration

Set these environment variables in the secure file:

- `ROOM_MONITOR_TELEGRAM_BOT_TOKEN`
- `ROOM_MONITOR_AUTHORIZED_CHAT_ID`
- `ROOM_MONITOR_I2C_BUS`
- `ROOM_MONITOR_I2C_ADDRESS`
- `ROOM_MONITOR_LOG_LEVEL`

The project expects the Pi to have I²C enabled and the sensor visible at `0x40` on bus 1.

## Running tests

```bash
pytest -q
```

## Checking the sensor

With the virtual environment active and the current user permitted to access
`/dev/i2c-1`, run:

```bash
python -m room_monitor.cli_sensor_check --bus 1 --address 0x40
```

The check prints temperature in Celsius and Fahrenheit plus relative humidity.
It validates the Si7021 checksum and physical measurement ranges, retries brief
I2C failures three times, and exits nonzero with a concise error if the sensor
remains unavailable or returns invalid data.

## Operational notes

- `systemd` service file is in `systemd/room-monitor.service`.
- Use `journalctl -u room-monitor.service -f` to inspect logs.
- The bot token is never stored in source code or documentation.

## Troubleshooting

- Sensor not found: verify `i2cdetect -y 1` shows `40`.
- Permission denied: add the service user to the `i2c` group, then sign out and back in.
- Bad checksum or invalid measurement: check wiring and power, then rerun the sensor check.
- Telegram unauthorized: confirm the bot token and your chat ID are correct.
- Reboots: ensure the service is enabled with `sudo systemctl enable --now room-monitor.service`.
