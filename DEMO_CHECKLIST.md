# Competition Demo Checklist

## Before the demo

- Confirm the Si7021 appears as `40` with `i2cdetect -y 1`.
- Confirm `sudo systemctl is-enabled room-monitor.service` prints `enabled`.
- Confirm `sudo systemctl is-active room-monitor.service` prints `active`.
- Run `sudo journalctl -u room-monitor.service --since today --no-pager` and resolve recent errors.
- Send `/status` from the authorized Telegram chat and verify Celsius, Fahrenheit, and humidity.
- Confirm no foreground `room_monitor.app` process is running alongside the service.
- Keep the bot token and `/etc/room-monitor.env` out of screenshots and terminal history.

## Live demonstration

1. Show the sensor at I2C address `0x40`.
2. Show the active and enabled systemd service.
3. Send `/status` and explain the three displayed measurements.
4. Demonstrate that an unauthorized chat receives no reply.
5. Run `.venv/bin/python -m pytest tests/test_alerts.py tests/test_resilience.py -q` to demonstrate alert, recovery, outage, and restart behavior with deterministic sensor readings.
6. Explain that repeated out-of-range readings do not repeat an alert and returning to range sends one recovery.
7. Restart the service and show it returns to `active` with its persisted state intact.
8. Send `/status` again to confirm the live sensor and Telegram connection.

## Final state

- Temperature limits: 10 C through 27 C inclusive.
- Humidity limits: 30% through 60% inclusive.
- Alert state file exists at `/var/lib/room-monitor/alert-state.json` after a transition.
- Only the systemd-managed application process is running.
