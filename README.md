# Room Monitor

A Raspberry Pi 5 room-monitoring application for the SparkFun Si7021 humidity and temperature sensor.

## Features

- Reads temperature and humidity from the Si7021 over I²C bus 1 at address 0x40.
- Supports authorized Telegram `/start`, `/help`, and `/status` commands.
- Returns temperature in Celsius and Fahrenheit plus relative humidity.
- Ignores every Telegram chat except the configured private chat ID.
- Lets the authorized chat view and change temperature and humidity alert limits.
- Detects alert and recovery transitions without repeating unchanged alerts.
- Persists independent temperature and humidity state across restarts.
- Sends hourly reports from 8:00 AM through 5:00 PM in the Pi's local time.
- Checks alert thresholds continuously, including outside reporting hours.
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
- `ROOM_MONITOR_ALERT_STATE_FILE`
- `ROOM_MONITOR_THRESHOLD_FILE`
- `ROOM_MONITOR_ALERT_CHECK_INTERVAL_SECONDS`

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

Leave the terminal running and test `/start`, `/help`, `/status`, and
`/thresholds` from the
authorized chat. Stop it with `Ctrl+C`. Commands from every other chat are
silently ignored and do not access the sensor.

Only one process may poll a Telegram bot. Stop this foreground process before
starting the `systemd` service. The application also holds a per-bot
single-instance lock and rejects a second local process before it can poll.

Telegram connections use IPv4 explicitly. This avoids `ConnectTimeout`
failures on networks where DNS returns an IPv6 address but IPv6 routing is
unavailable.

## Alert state

Temperature defaults to normal from 10 C through 27 C, inclusive. Humidity
defaults to normal from 30% through 60%, inclusive. The authorized chat can
inspect and change these limits:

```text
/thresholds
/settemperature 10 27
/sethumidity 30 60
```

Temperature limits must satisfy `-40 <= low < high <= 125 C`. Humidity limits
must satisfy `0 <= low < high <= 100%`. Successful updates take effect on the
next alert check and persist across service restarts. Invalid commands leave
the previous values active. Unauthorized chats receive no response and cannot
read or change thresholds.

A transition outside the active ranges creates one alert event; unchanged
out-of-range readings create none. Returning to the normal range creates one
recovery event. Temperature and humidity are tracked independently.

State is stored as versioned JSON at `ROOM_MONITOR_ALERT_STATE_FILE`, which
defaults to `/var/lib/room-monitor/alert-state.json`. Writes use a restricted
temporary file, file synchronization, and atomic replacement so an interrupted
write cannot leave a partially written active state file. Missing or malformed
state safely starts as normal and is logged.

Thresholds use separate versioned JSON at `ROOM_MONITOR_THRESHOLD_FILE`, which
defaults to `/var/lib/room-monitor/thresholds.json`. Threshold writes use the
same restrictive permissions, synchronization, and atomic replacement pattern.
A missing or malformed threshold file falls back to the documented defaults.

## Automatic monitoring

The bot checks alert thresholds every 60 seconds by default, all day and all
night. Set `ROOM_MONITOR_ALERT_CHECK_INTERVAL_SECONDS` to a positive number to
change that interval. A transition is sent once and committed only after
Telegram accepts the message. If Telegram is unavailable, the transition stays
pending for the next check. If state persistence fails after delivery, further
alert delivery pauses while the same commit is retried, preventing a message
flood.

One status report is scheduled at the start of each hour from 8:00 AM through
5:00 PM inclusive. The scheduler uses the Raspberry Pi's configured local time
zone. Alert checks continue outside this reporting window.

## Running tests

```bash
.venv/bin/python -m pytest -q
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

## Deploying with systemd

The installer uses fixed system paths and a dedicated `room-monitor` service
account, so it does not depend on the login username. It preserves an existing
`/etc/room-monitor.env` and alert-state file. It enables the service at boot but
does not start it until configuration has been reviewed.

From the repository root:

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv i2c-tools
sudo ./scripts/install.sh
sudoedit /etc/room-monitor.env
sudo systemctl start room-monitor.service
sudo systemctl status room-monitor.service --no-pager
```

Before starting the service, confirm any earlier foreground test has ended with
`Ctrl+C`. Do not leave `python -m room_monitor.app` running in another terminal.

The deployment layout is:

```text
/opt/room-monitor/                         application and virtual environment
/etc/room-monitor.env                      root-only secrets and configuration
/etc/systemd/system/room-monitor.service   installed systemd unit
/var/lib/room-monitor/alert-state.json     persistent alert state
/var/lib/room-monitor/thresholds.json      persistent alert limits
```

The service runs as the non-login `room-monitor` user with supplementary access
to the `i2c` group. `systemd` creates `/var/lib/room-monitor` with mode `0700`.
Application files are root-owned and read-only to the service. The unit starts
after network-online, restarts after failures with a ten-second delay, limits
restart bursts, writes to the journal, and starts automatically after reboot.

### Logs and operation

```bash
sudo systemctl status room-monitor.service --no-pager
sudo journalctl -u room-monitor.service -n 100 --no-pager
sudo journalctl -u room-monitor.service -f
sudo systemctl restart room-monitor.service
sudo systemctl stop room-monitor.service
```

To verify automatic startup without rebooting:

```bash
sudo systemctl is-enabled room-monitor.service
```

The expected result is `enabled`.

### Updating an installation

Pull and test changes in the repository, then rerun the idempotent installer.
It preserves the protected environment file and state:

```bash
git pull --ff-only
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
sudo systemctl stop room-monitor.service
sudo ./scripts/install.sh
sudo systemctl start room-monitor.service
```

The bot token is never stored in source code or documentation. The logging
formatter redacts the configured token from complete rendered log entries,
including exception tracebacks, and noisy HTTP request logging is disabled.

## Troubleshooting

- Sensor not found: verify `i2cdetect -y 1` shows `40`.
- Permission denied: add the service user to the `i2c` group, then sign out and back in.
- Bad checksum or invalid measurement: check wiring and power, then rerun the sensor check.
- Telegram unauthorized: confirm the bot token and your chat ID are correct.
- Telegram reports `ConnectTimeout`: verify IPv4 access with `curl -4 -I --connect-timeout 10 https://api.telegram.org`.
- Telegram reports `409 Conflict`: stop every foreground `room_monitor.app` process, then restart only the systemd service.
- Chat-ID helper finds nothing: stop the main bot, send the bot a fresh message, and immediately rerun the helper.
- Protected environment file says permission denied: run the documented single `sudo bash -c` helper command.
- Service cannot open I²C: verify `getent group i2c` includes `room-monitor` and restart the service.
- Service does not start: run `sudo journalctl -u room-monitor.service -n 100 --no-pager`.
- Reboots: verify `sudo systemctl is-enabled room-monitor.service` reports `enabled`.

## Quality verification

Run the automated failure simulations before deployment:

```bash
.venv/bin/python -m pytest -q
```

The suite covers persisted restart recovery, Telegram interruption and retry,
sensor disconnection and recovery, unauthorized commands, scheduling, state
write failure, corrupt state, and duplicate-alert prevention.

Verify reboot recovery on the Pi:

```bash
sudo systemctl restart room-monitor.service
sudo systemctl is-active room-monitor.service
sudo systemctl is-enabled room-monitor.service
sudo journalctl -u room-monitor.service --since "2 minutes ago" --no-pager
```

For a controlled sensor-failure check, stop the service, disconnect only the
Si7021, start the service, and confirm the journal reports failed reads while
the process remains active. Stop it again before reconnecting the powered
hardware, then start it and verify `/status`. Never move I2C wiring while the
Pi or sensor is powered.

For a network-interruption check, temporarily disconnect networking and then
restore it. The service must remain active; pending transitions retry after
connectivity returns, and an unchanged out-of-range condition must not flood
messages.

See `DEMO_CHECKLIST.md` for the short competition demonstration procedure.
