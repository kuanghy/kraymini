import stat
import time
from unittest.mock import patch, MagicMock

import pytest

from kraymini.scheduler import CrashMonitor, Daemon
from kraymini.config import KrayminiConfig, SubscriptionConfig, GeneralConfig
from kraymini.models import Node


class TestCrashMonitor:
    def test_record_crash(self):
        m = CrashMonitor(max_crashes=3, crash_window=30)
        m.record_crash()
        assert not m.is_suspended

    def test_suspend(self):
        m = CrashMonitor(max_crashes=3, crash_window=30)
        for _ in range(3):
            m.record_crash()
        assert m.is_suspended

    def test_reset(self):
        m = CrashMonitor(max_crashes=3, crash_window=30)
        for _ in range(3):
            m.record_crash()
        m.reset()
        assert not m.is_suspended

    def test_old_crashes_expire(self):
        m = CrashMonitor(max_crashes=3, crash_window=2)
        m.record_crash()
        m.record_crash()
        time.sleep(2.1)
        m.record_crash()
        assert not m.is_suspended


@pytest.fixture
def fake_xray(tmp_path):
    script = tmp_path / "fake_xray"
    script.write_text(
        '#!/bin/sh\n'
        'if [ "$1" = "run" ] && [ "$2" = "-test" ]; then exit 0; fi\n'
        'if [ "$1" = "run" ] && [ "$2" = "-c" ]; then while true; do sleep 1; done; fi\n',
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


class TestDaemon:
    def _make_config(self, tmp_path, xray_bin):
        return KrayminiConfig(
            subscriptions=[SubscriptionConfig(url="https://example.com/sub")],
            general=GeneralConfig(
                xray_bin=xray_bin,
                output_config=str(tmp_path / "xray.json"),
                refresh_interval=3600,
            ),
        )

    @patch("kraymini.scheduler.SubscriptionManager")
    def test_initial_start(self, mock_mgr_cls, tmp_path, fake_xray):
        mock_mgr = MagicMock()
        mock_mgr.refresh.return_value = [
            Node(raw_uri="vless://test", remark="test-node", protocol="vless",
                 address="host", port=443,
                 credentials={"uuid": "u", "encryption": "none"},
                 transport={"network": "tcp", "security": "none", "sni": "",
                             "fingerprint": "", "alpn": "", "host": "", "path": "",
                             "header_type": ""}),
        ]
        mock_mgr_cls.return_value = mock_mgr
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        cfg = self._make_config(tmp_path, fake_xray)
        daemon = Daemon(cfg, str(config_path))
        daemon.initial_start()
        assert daemon.xray.is_running()
        assert daemon.current_nodes is not None
        daemon.shutdown()
        assert not daemon.xray.is_running()

    @patch("kraymini.scheduler.SubscriptionManager")
    def test_initial_start_no_nodes(self, mock_mgr_cls, tmp_path, fake_xray):
        mock_mgr = MagicMock()
        mock_mgr.refresh.return_value = None
        mock_mgr_cls.return_value = mock_mgr
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        cfg = self._make_config(tmp_path, fake_xray)
        daemon = Daemon(cfg, str(config_path))
        with pytest.raises(SystemExit):
            daemon.initial_start()
