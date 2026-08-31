from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVICE_TEXT = (PROJECT_ROOT / "systemd/room-monitor.service").read_text()
INSTALLER_TEXT = (PROJECT_ROOT / "scripts/install.sh").read_text()


def test_service_uses_dedicated_user_and_i2c_group():
    assert "User=room-monitor" in SERVICE_TEXT
    assert "Group=room-monitor" in SERVICE_TEXT
    assert "SupplementaryGroups=i2c" in SERVICE_TEXT
    assert "User=root" not in SERVICE_TEXT


def test_service_uses_protected_state_directory_and_external_secrets():
    assert "EnvironmentFile=/etc/room-monitor.env" in SERVICE_TEXT
    assert "StateDirectory=room-monitor" in SERVICE_TEXT
    assert "StateDirectoryMode=0700" in SERVICE_TEXT
    assert "UMask=0077" in SERVICE_TEXT


def test_service_restarts_with_limits_and_writes_to_journal():
    assert "Restart=on-failure" in SERVICE_TEXT
    assert "RestartSec=10" in SERVICE_TEXT
    assert "StartLimitBurst=5" in SERVICE_TEXT
    assert "StandardOutput=journal" in SERVICE_TEXT
    assert "StandardError=journal" in SERVICE_TEXT


def test_service_applies_practical_hardening_without_blocking_i2c_or_ipv4():
    assert "NoNewPrivileges=true" in SERVICE_TEXT
    assert "ProtectSystem=strict" in SERVICE_TEXT
    assert "ReadWritePaths=/opt/room-monitor/data" in SERVICE_TEXT
    assert "ProtectHome=true" in SERVICE_TEXT
    assert "RestrictNamespaces=true" in SERVICE_TEXT
    assert "RestrictAddressFamilies=AF_UNIX AF_INET" in SERVICE_TEXT
    assert "PrivateDevices=true" not in SERVICE_TEXT


def test_installer_does_not_assume_a_login_username_or_overwrite_secrets():
    assert "/home/" not in INSTALLER_TEXT
    assert 'if [ ! -e "$ENV_FILE" ]' in INSTALLER_TEXT
    assert 'Preserved existing $ENV_FILE' in INSTALLER_TEXT
    assert "systemctl enable room-monitor.service" in INSTALLER_TEXT
    assert not any(
        line.strip().startswith("systemctl start room-monitor.service")
        for line in INSTALLER_TEXT.splitlines()
    )


def test_installer_copies_only_runtime_sources():
    assert 'room_monitor/*.py' in INSTALLER_TEXT
    assert ".env.example" in INSTALLER_TEXT
    assert "cp -a" not in INSTALLER_TEXT
    assert ".git" not in INSTALLER_TEXT
    assert 'DATA_DIR=$INSTALL_DIR/data' in INSTALLER_TEXT
    assert 'install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$DATA_DIR"' in INSTALLER_TEXT
    assert "temperature_monitor.db" in INSTALLER_TEXT


def test_installer_repairs_permissions_for_persisted_thresholds():
    assert 'if [ -e "$STATE_DIR/thresholds.json" ]' in INSTALLER_TEXT
    assert 'chmod 0600 "$STATE_DIR/thresholds.json"' in INSTALLER_TEXT
