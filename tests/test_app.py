import errno
import logging
import sys

import pytest

from room_monitor.app import RedactingFormatter, acquire_instance_lock, configure_logging
from room_monitor.config import RuntimeConfig


def test_formatter_redacts_token_from_message_and_exception():
    token = "private-test-token"
    formatter = RedactingFormatter(token)
    try:
        raise RuntimeError(f"request URL contained {token}")
    except RuntimeError:
        record = logging.LogRecord(
            "test",
            logging.ERROR,
            __file__,
            1,
            "failed with %s",
            (token,),
            exc_info=sys.exc_info(),
        )

    output = formatter.format(record)

    assert token not in output
    assert output.count("[REDACTED]") == 2


def test_configure_logging_suppresses_noisy_dependency_info(tmp_path):
    config = RuntimeConfig(
        "private-test-token",
        123,
        1,
        0x40,
        log_level="INFO",
        alert_state_file=tmp_path / "state.json",
    )

    configure_logging(config)

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
    assert logging.getLogger("apscheduler").level == logging.WARNING


class FakeSocket:
    bound_names: set[str] = set()

    def __init__(self, *_args):
        self.name = None

    def bind(self, name):
        if name in self.bound_names:
            raise OSError(errno.EADDRINUSE, "Address already in use")
        self.name = name
        self.bound_names.add(name)

    def close(self):
        if self.name is not None:
            self.bound_names.discard(self.name)
            self.name = None


@pytest.fixture(autouse=True)
def reset_fake_socket_names():
    FakeSocket.bound_names.clear()


def test_instance_lock_rejects_second_process_for_same_bot(monkeypatch):
    monkeypatch.setattr("room_monitor.app.socket.socket", FakeSocket)
    first = acquire_instance_lock("same-test-token")
    try:
        with pytest.raises(RuntimeError, match="already running"):
            acquire_instance_lock("same-test-token")
    finally:
        first.close()


def test_instance_lock_allows_different_bots(monkeypatch):
    monkeypatch.setattr("room_monitor.app.socket.socket", FakeSocket)
    first = acquire_instance_lock("first-test-token")
    second = acquire_instance_lock("second-test-token")
    first.close()
    second.close()
