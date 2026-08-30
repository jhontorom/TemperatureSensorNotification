#!/bin/sh
set -eu

INSTALL_DIR=/opt/room-monitor
ENV_FILE=/etc/room-monitor.env
SERVICE_FILE=/etc/systemd/system/room-monitor.service
SERVICE_USER=room-monitor
STATE_DIR=/var/lib/room-monitor

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer with sudo." >&2
    exit 1
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(dirname -- "$SCRIPT_DIR")

for command in python3 getent groupadd useradd usermod install systemctl; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "Required command is missing: $command" >&2
        exit 1
    fi
done

if ! getent group i2c >/dev/null; then
    echo "The i2c group does not exist. Enable I2C and install Raspberry Pi I2C support first." >&2
    exit 1
fi

if ! getent group "$SERVICE_USER" >/dev/null; then
    groupadd --system "$SERVICE_USER"
fi
if ! getent passwd "$SERVICE_USER" >/dev/null; then
    useradd --system --gid "$SERVICE_USER" --home-dir /nonexistent --shell /usr/sbin/nologin "$SERVICE_USER"
fi
usermod --append --groups i2c "$SERVICE_USER"

install -d -o root -g root -m 0755 "$INSTALL_DIR"
install -d -o root -g root -m 0755 "$INSTALL_DIR/room_monitor"
install -o root -g root -m 0644 "$PROJECT_DIR"/room_monitor/*.py "$INSTALL_DIR/room_monitor/"
install -o root -g root -m 0644 "$PROJECT_DIR/requirements.txt" "$INSTALL_DIR/requirements.txt"

if [ ! -x "$INSTALL_DIR/.venv/bin/python3" ]; then
    python3 -m venv "$INSTALL_DIR/.venv"
fi
"$INSTALL_DIR/.venv/bin/python3" -m pip install --disable-pip-version-check -r "$INSTALL_DIR/requirements.txt"

install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0700 "$STATE_DIR"
if [ -e "$STATE_DIR/alert-state.json" ]; then
    chown "$SERVICE_USER:$SERVICE_USER" "$STATE_DIR/alert-state.json"
    chmod 0600 "$STATE_DIR/alert-state.json"
fi
if [ -e "$STATE_DIR/thresholds.json" ]; then
    chown "$SERVICE_USER:$SERVICE_USER" "$STATE_DIR/thresholds.json"
    chmod 0600 "$STATE_DIR/thresholds.json"
fi

if [ ! -e "$ENV_FILE" ]; then
    install -o root -g root -m 0600 "$PROJECT_DIR/.env.example" "$ENV_FILE"
    echo "Created $ENV_FILE from the placeholder template. Configure it before starting the service."
else
    chown root:root "$ENV_FILE"
    chmod 0600 "$ENV_FILE"
    echo "Preserved existing $ENV_FILE."
fi

install -o root -g root -m 0644 "$PROJECT_DIR/systemd/room-monitor.service" "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable room-monitor.service

echo "Installation complete. Review $ENV_FILE, then run:"
echo "  sudo systemctl start room-monitor.service"
echo "  sudo systemctl status room-monitor.service --no-pager"
