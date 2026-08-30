# Room Monitor

A Raspberry Pi 5 room-monitoring application for the SparkFun Si7021 humidity and temperature sensor.

## Features

- Reads temperature and humidity from the Si7021 over I²C bus 1 at address 0x40.
- Supports authorized Telegram `/start`, `/help`, and `/status` commands.
- Returns temperature in Celsius and Fahrenheit plus relative humidity.
- Ignores every Telegram chat except the configured private chat ID.
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

Keep the real environment file outside the repository and restrict it to root.
The following command creates it only when it does not already exist:

```bash
sudo test -e /etc/room-monitor.env || sudo install -m 600 -o root -g root .env.example /etc/room-monitor.env
sudoedit /etc/room-monitor.env
sudo chown root:root /etc/room-monitor.env
sudo chmod 600 /etc/room-monitor.env
```

## Telegram setup

### Create the bot

1. In Telegram, open the verified [@BotFather](https://t.me/BotFather)
   account. Check both the exact username and verification mark.
2. Tap **Start**, send `/newbot`, and follow the prompts.
3. Choose a display name and a unique username ending in `bot`.
4. Keep the token returned by BotFather private. Do not paste it into a shell
   command, URL, chat, source file, documentation, or log.
5. For a private room monitor, send `/setjoingroups` to BotFather, select the
   new bot, and disable group joining.

If a token is ever exposed, do not use it. Send `/revoke` to BotFather, select
the bot, and use only the replacement token. Deleting the exposed message does
not replace revocation.

### Store the token

From the project directory, create and edit the protected file:

```bash
sudo test -e /etc/room-monitor.env || sudo install -m 600 -o root -g root .env.example /etc/room-monitor.env
sudoedit /etc/room-monitor.env
```

Replace the token placeholder inside the editor. Leave the chat-ID placeholder
until completing the next step. Verify security without displaying the file:

```bash
sudo chown root:root /etc/room-monitor.env
sudo chmod 600 /etc/room-monitor.env
sudo stat -c '%A %U %G %n' /etc/room-monitor.env
```

The expected result is `-rw------- root root /etc/room-monitor.env`.

### Find the private chat ID

Open the new bot in Telegram, tap **Start**, and send a fresh message such as
`chat-id-check`. Ensure `room_monitor.app` is stopped because two polling
processes can consume each other's updates.

Run the helper from the project directory. Loading the protected file and
starting the helper both occur under `sudo`, avoiding permission errors:

```bash
sudo bash -c 'set -a; . /etc/room-monitor.env; set +a; exec .venv/bin/python -m room_monitor.cli_chat_id'
```

The helper prints chat IDs only; it never prints the token. Edit the protected
file again:

```bash
sudoedit /etc/room-monitor.env
```

Replace `ROOM_MONITOR_AUTHORIZED_CHAT_ID` with the reported private-chat ID.

## Running the Telegram bot

Run the bot in the foreground for its first test:

```bash
sudo bash -c 'set -a; . /etc/room-monitor.env; set +a; exec .venv/bin/python -m room_monitor.app'
```

Leave the terminal running and test `/start`, `/help`, and `/status` from the
authorized chat. Stop it with `Ctrl+C`. Commands from every other chat are
silently ignored and do not access the sensor.

Telegram connections use IPv4 explicitly. This avoids `ConnectTimeout`
failures on networks where DNS returns an IPv6 address but IPv6 routing is
unavailable.

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
- Telegram reports `ConnectTimeout`: verify IPv4 access with `curl -4 -I --connect-timeout 10 https://api.telegram.org`.
- Chat-ID helper finds nothing: stop the main bot, send the bot a fresh message, and immediately rerun the helper.
- Protected environment file says permission denied: run the documented single `sudo bash -c` helper command.
- Reboots: ensure the service is enabled with `sudo systemctl enable --now room-monitor.service`.
