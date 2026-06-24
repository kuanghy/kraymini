import stat
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from kraymini.scheduler import CrashMonitor, Daemon, next_daily_restart_at
from kraymini.config import KrayminiConfig, SubscriptionConfig, GeneralConfig
from kraymini.connectivity import ProbeResult
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

    @patch("kraymini.scheduler.SubscriptionManager")
    def test_initial_start_exits_when_generated_config_invalid(
        self,
        mock_mgr_cls,
        tmp_path,
        fake_xray,
    ):
        mock_mgr = MagicMock()
        mock_mgr.refresh.return_value = [
            Node(
                raw_uri="vless://test",
                remark="test-node",
                protocol="vless",
                address="host",
                port=443,
                credentials={"uuid": "u", "encryption": "none"},
                transport={
                    "network": "tcp",
                    "security": "none",
                    "sni": "",
                    "fingerprint": "",
                    "alpn": "",
                    "host": "",
                    "path": "",
                    "header_type": "",
                },
            ),
        ]
        mock_mgr_cls.return_value = mock_mgr
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        cfg = self._make_config(tmp_path, fake_xray)
        daemon = Daemon(cfg, str(config_path))
        daemon.xray.validate_config = MagicMock(return_value=False)

        with pytest.raises(SystemExit):
            daemon.initial_start()
        assert daemon.current_nodes is None
        assert not Path(cfg.general.output_config).exists()

    @patch("kraymini.process.XrayProcess.check_available", return_value=False)
    @patch("kraymini.scheduler.SubscriptionManager")
    def test_initial_start_checks_xray_before_refresh(
        self,
        mock_mgr_cls,
        mock_check_available,
        tmp_path,
        fake_xray,
    ):
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        cfg = self._make_config(tmp_path, fake_xray)
        daemon = Daemon(cfg, str(config_path))
        with pytest.raises(SystemExit):
            daemon.initial_start()

        mock_check_available.assert_called_once_with()
        mock_mgr.refresh.assert_not_called()

    @patch("kraymini.process.XrayProcess.check_available", return_value=False)
    @patch("kraymini.scheduler.SubscriptionManager")
    def test_refresh_checks_xray_before_subscription_refresh(
        self,
        mock_mgr_cls,
        mock_check_available,
        tmp_path,
        fake_xray,
    ):
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        cfg = self._make_config(tmp_path, fake_xray)
        daemon = Daemon(cfg, str(config_path))
        daemon.current_nodes = []

        daemon._do_refresh()

        mock_check_available.assert_called_once_with()
        mock_mgr.refresh.assert_not_called()

    @patch("kraymini.scheduler.SubscriptionManager")
    def test_daemon_passes_gomemlimit_to_xray_process(
        self,
        mock_mgr_cls,
        tmp_path,
        fake_xray,
    ):
        mock_mgr_cls.return_value = MagicMock()
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        cfg = self._make_config(tmp_path, fake_xray)
        cfg.general.xray_gomemlimit = "1GiB"
        daemon = Daemon(cfg, str(config_path))
        assert daemon.xray.gomemlimit == "1GiB"

    @patch("kraymini.scheduler.SubscriptionManager")
    def test_force_refresh_reloads_when_nodes_unchanged(
        self,
        mock_mgr_cls,
        tmp_path,
        fake_xray,
    ):
        mock_mgr = MagicMock()
        node = Node(
            raw_uri="vless://test",
            remark="test-node",
            protocol="vless",
            address="host",
            port=443,
            credentials={"uuid": "u", "encryption": "none"},
            transport={
                "network": "tcp",
                "security": "none",
                "sni": "",
                "fingerprint": "",
                "alpn": "",
                "host": "",
                "path": "",
                "header_type": "",
            },
        )
        mock_mgr.refresh.return_value = [node]
        mock_mgr.nodes_changed.return_value = False
        mock_mgr_cls.return_value = mock_mgr
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        cfg = self._make_config(tmp_path, fake_xray)
        daemon = Daemon(cfg, str(config_path))
        daemon.current_nodes = [node]
        daemon.xray.check_available = MagicMock(return_value=True)
        daemon.xray.validate_config = MagicMock(return_value=True)
        daemon.xray.reload = MagicMock()

        daemon._do_refresh(force_reload=True, reason="每日定时重启")

        daemon.xray.reload.assert_called_once()
        mock_mgr.nodes_changed.assert_called_once()

    @patch("kraymini.scheduler.SubscriptionManager")
    def test_validation_failure_keeps_live_config_and_current_nodes(
        self,
        mock_mgr_cls,
        tmp_path,
        fake_xray,
    ):
        old_node = Node(
            raw_uri="vless://old",
            remark="old-node",
            protocol="vless",
            address="old-host",
            port=443,
            credentials={"uuid": "old", "encryption": "none"},
            transport={
                "network": "tcp",
                "security": "none",
                "sni": "",
                "fingerprint": "",
                "alpn": "",
                "host": "",
                "path": "",
                "header_type": "",
            },
        )
        new_node = Node(
            raw_uri="vless://new",
            remark="new-node",
            protocol="vless",
            address="new-host",
            port=443,
            credentials={"uuid": "new", "encryption": "none"},
            transport={
                "network": "tcp",
                "security": "none",
                "sni": "",
                "fingerprint": "",
                "alpn": "",
                "host": "",
                "path": "",
                "header_type": "",
            },
        )
        mock_mgr = MagicMock()
        mock_mgr.refresh.return_value = [new_node]
        mock_mgr.nodes_changed.return_value = True
        mock_mgr_cls.return_value = mock_mgr
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        cfg = self._make_config(tmp_path, fake_xray)
        live_config = tmp_path / "xray.json"
        live_config.write_text('{"old": true}')
        daemon = Daemon(cfg, str(config_path))
        daemon.current_nodes = [old_node]
        daemon.xray.check_available = MagicMock(return_value=True)
        daemon.xray.validate_config = MagicMock(return_value=False)
        daemon.xray.reload = MagicMock()

        daemon._do_refresh()

        assert live_config.read_text() == '{"old": true}'
        assert daemon.current_nodes == [old_node]
        daemon.xray.reload.assert_not_called()

    @patch("kraymini.scheduler.SubscriptionManager")
    def test_validation_failure_restart_uses_existing_live_config(
        self,
        mock_mgr_cls,
        tmp_path,
        fake_xray,
    ):
        new_node = Node(
            raw_uri="vless://new",
            remark="new-node",
            protocol="vless",
            address="new-host",
            port=443,
            credentials={"uuid": "new", "encryption": "none"},
            transport={
                "network": "tcp",
                "security": "none",
                "sni": "",
                "fingerprint": "",
                "alpn": "",
                "host": "",
                "path": "",
                "header_type": "",
            },
        )
        mock_mgr = MagicMock()
        mock_mgr.refresh.return_value = [new_node]
        mock_mgr.nodes_changed.return_value = True
        mock_mgr_cls.return_value = mock_mgr
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        cfg = self._make_config(tmp_path, fake_xray)
        live_config = tmp_path / "xray.json"
        live_config.write_text('{"old": true}')
        daemon = Daemon(cfg, str(config_path))
        daemon.current_nodes = []
        daemon.xray.check_available = MagicMock(return_value=True)
        daemon.xray.validate_config = MagicMock(return_value=False)
        daemon.xray.reload = MagicMock()

        daemon._do_refresh(
            force_reload=True,
            restart_on_failure=True,
            reason="每日定时重启",
        )

        daemon.xray.reload.assert_called_once_with(
            str(live_config),
            log_file=cfg.log.file,
        )
        assert live_config.read_text() == '{"old": true}'

    @patch("kraymini.scheduler.SubscriptionManager")
    def test_reload_failure_keeps_previous_current_nodes(
        self,
        mock_mgr_cls,
        tmp_path,
        fake_xray,
    ):
        old_node = Node(
            raw_uri="vless://old",
            remark="old-node",
            protocol="vless",
            address="old-host",
            port=443,
            credentials={"uuid": "old", "encryption": "none"},
            transport={
                "network": "tcp",
                "security": "none",
                "sni": "",
                "fingerprint": "",
                "alpn": "",
                "host": "",
                "path": "",
                "header_type": "",
            },
        )
        new_node = Node(
            raw_uri="vless://new",
            remark="new-node",
            protocol="vless",
            address="new-host",
            port=443,
            credentials={"uuid": "new", "encryption": "none"},
            transport={
                "network": "tcp",
                "security": "none",
                "sni": "",
                "fingerprint": "",
                "alpn": "",
                "host": "",
                "path": "",
                "header_type": "",
            },
        )
        mock_mgr = MagicMock()
        mock_mgr.refresh.return_value = [new_node]
        mock_mgr.nodes_changed.return_value = True
        mock_mgr_cls.return_value = mock_mgr
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        cfg = self._make_config(tmp_path, fake_xray)
        live_config = tmp_path / "xray.json"
        live_config.write_text('{"old": true}')
        daemon = Daemon(cfg, str(config_path))
        daemon.current_nodes = [old_node]
        daemon.xray.check_available = MagicMock(return_value=True)
        daemon.xray.validate_config = MagicMock(return_value=True)
        daemon.xray.reload = MagicMock(side_effect=RuntimeError("reload failed"))

        with pytest.raises(RuntimeError, match="reload failed"):
            daemon._do_refresh()

        assert daemon.current_nodes == [old_node]
        assert live_config.exists()
        assert 'new-node' in live_config.read_text()


class TestDaemonConnectivity:
    def _make_config(self, tmp_path, xray_bin: str) -> KrayminiConfig:
        return KrayminiConfig(
            subscriptions=[SubscriptionConfig(url="https://example.com/sub")],
            general=GeneralConfig(
                xray_bin=xray_bin,
                output_config=str(tmp_path / "xray.json"),
                refresh_interval=3600,
                connectivity_check_interval=600,
            ),
        )

    @patch("kraymini.scheduler.check_proxy_connectivity")
    def test_maybe_check_connectivity_skipped_when_interval_zero(
        self,
        mock_proxy,
        tmp_path,
        fake_xray,
    ):
        cfg = self._make_config(tmp_path, fake_xray)
        cfg.general.connectivity_check_interval = 0
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        daemon = Daemon(cfg, str(config_path))
        daemon._last_connectivity_check = 0.0
        daemon._maybe_check_connectivity(10_000.0)
        mock_proxy.assert_not_called()

    @patch("kraymini.process.XrayProcess.is_running", return_value=False)
    @patch("kraymini.scheduler.check_proxy_connectivity")
    def test_maybe_check_connectivity_skipped_when_xray_not_running(
        self,
        mock_proxy,
        _mock_is_running,
        tmp_path,
        fake_xray,
    ):
        cfg = self._make_config(tmp_path, fake_xray)
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        daemon = Daemon(cfg, str(config_path))
        daemon._last_connectivity_check = 0.0
        daemon._maybe_check_connectivity(10_000.0)
        mock_proxy.assert_not_called()
        # 被跳过时不应推进时间戳，下次 xray 恢复后仍会立刻触发
        assert daemon._last_connectivity_check == 0.0

    @patch("kraymini.scheduler.check_proxy_connectivity")
    def test_maybe_check_connectivity_skipped_before_interval_elapsed(
        self,
        mock_proxy,
        tmp_path,
        fake_xray,
    ):
        cfg = self._make_config(tmp_path, fake_xray)
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        daemon = Daemon(cfg, str(config_path))
        daemon._last_connectivity_check = 9_500.0
        daemon._maybe_check_connectivity(10_000.0)
        mock_proxy.assert_not_called()

    @patch("kraymini.process.XrayProcess.is_running", return_value=True)
    @patch("kraymini.scheduler.logger.info")
    @patch("kraymini.scheduler.check_local_connectivity")
    @patch("kraymini.scheduler.check_proxy_connectivity")
    def test_maybe_check_connectivity_logs_latency_on_success(
        self,
        mock_proxy,
        mock_local,
        mock_log_info,
        _mock_is_running,
        tmp_path,
        fake_xray,
    ):
        mock_proxy.return_value = ProbeResult(ok=True, latency_ms=42, error=None)
        cfg = self._make_config(tmp_path, fake_xray)
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        daemon = Daemon(cfg, str(config_path))
        daemon._last_connectivity_check = 0.0
        daemon._maybe_check_connectivity(10_000.0)
        mock_proxy.assert_called_once()
        mock_local.assert_not_called()
        mock_log_info.assert_called_once()
        assert mock_log_info.call_args[0][0] == "网络连通性正常，延迟 %d ms"
        assert mock_log_info.call_args[0][1] == 42

    @patch("kraymini.process.XrayProcess.is_running", return_value=True)
    @patch.object(Daemon, "_do_refresh")
    @patch("kraymini.scheduler.logger.warning")
    @patch("kraymini.scheduler.check_local_connectivity", return_value=True)
    @patch("kraymini.scheduler.check_proxy_connectivity")
    def test_maybe_check_connectivity_refreshes_when_proxy_down_local_up(
        self,
        mock_proxy,
        mock_local,
        mock_log_warning,
        mock_do_refresh,
        _mock_is_running,
        tmp_path,
        fake_xray,
    ):
        mock_proxy.return_value = ProbeResult(ok=False, error="proxy-down")
        cfg = self._make_config(tmp_path, fake_xray)
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        daemon = Daemon(cfg, str(config_path))
        daemon._last_connectivity_check = 0.0
        daemon._maybe_check_connectivity(10_000.0)
        mock_do_refresh.assert_called_once()
        mock_log_warning.assert_called_once()

    @patch("kraymini.process.XrayProcess.is_running", return_value=True)
    @patch.object(Daemon, "_do_refresh")
    @patch("kraymini.scheduler.logger.warning")
    @patch("kraymini.scheduler.check_local_connectivity", return_value=False)
    @patch("kraymini.scheduler.check_proxy_connectivity")
    def test_maybe_check_connectivity_no_refresh_when_local_down(
        self,
        mock_proxy,
        mock_local,
        mock_log_warning,
        mock_do_refresh,
        _mock_is_running,
        tmp_path,
        fake_xray,
    ):
        mock_proxy.return_value = ProbeResult(ok=False, error="proxy-down")
        cfg = self._make_config(tmp_path, fake_xray)
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        daemon = Daemon(cfg, str(config_path))
        daemon._last_connectivity_check = 0.0
        daemon._maybe_check_connectivity(10_000.0)
        mock_do_refresh.assert_not_called()
        mock_log_warning.assert_called_once()


class TestDailyRestartSchedule:
    def test_next_daily_restart_at_same_day(self):
        now = time.mktime((2026, 6, 24, 1, 0, 0, 0, 0, -1))
        scheduled = next_daily_restart_at(now, "03:30")
        assert scheduled is not None
        scheduled_tm = time.localtime(scheduled)
        assert (scheduled_tm.tm_hour, scheduled_tm.tm_min) == (3, 30)
        assert scheduled_tm.tm_mday == 24

    def test_next_daily_restart_at_next_day_when_time_passed(self):
        now = time.mktime((2026, 6, 24, 23, 0, 0, 0, 0, -1))
        scheduled = next_daily_restart_at(now, "03:30")
        assert scheduled is not None
        scheduled_tm = time.localtime(scheduled)
        assert (scheduled_tm.tm_hour, scheduled_tm.tm_min) == (3, 30)
        assert scheduled_tm.tm_mday == 25

    @patch("kraymini.scheduler.SubscriptionManager")
    def test_maybe_run_daily_restart_triggers_force_reload(
        self,
        mock_mgr_cls,
        tmp_path,
        fake_xray,
    ):
        mock_mgr_cls.return_value = MagicMock()
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        cfg = KrayminiConfig(
            subscriptions=[SubscriptionConfig(url="https://example.com/sub")],
            general=GeneralConfig(
                xray_bin=fake_xray,
                output_config=str(tmp_path / "xray.json"),
                daily_restart_time="03:30",
            ),
        )
        daemon = Daemon(cfg, str(config_path))
        daemon._next_daily_restart_at = 100.0
        daemon._do_refresh = MagicMock()

        assert daemon._maybe_run_daily_restart(100.0) is True
        daemon._do_refresh.assert_called_once_with(
            force_reload=True,
            restart_on_failure=True,
            reason="每日定时重启",
        )
        assert daemon._next_daily_restart_at is not None
        assert daemon._next_daily_restart_at > 100.0
