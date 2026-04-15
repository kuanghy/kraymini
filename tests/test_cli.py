import platform
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kraymini import __version__
from kraymini.cli import build_parser, cmd_genconfig, cmd_nodes, cmd_run, main
from kraymini.config import GeneralConfig, KrayminiConfig, SubscriptionConfig
from kraymini.models import Node
from kraymini.subscription import save_cache


class TestBuildParser:
    def test_run(self):
        args = build_parser().parse_args(["run", "-c", "/tmp/config.toml"])
        assert args.command == "run" and args.config == "/tmp/config.toml"

    def test_genconfig(self):
        args = build_parser().parse_args(["genconfig", "-c", "/tmp/c.toml", "-o", "-"])
        assert args.command == "genconfig" and args.output == "-"

    def test_genconfig_offline(self):
        assert build_parser().parse_args(["genconfig", "--offline"]).offline is True

    def test_check(self):
        assert build_parser().parse_args(["check", "-c", "/tmp/c.toml"]).command == "check"

    def test_version(self):
        assert build_parser().parse_args(["version"]).command == "version"

    def test_verbose(self):
        assert build_parser().parse_args(["-v", "run"]).verbose is True

    def test_nodes(self):
        args = build_parser().parse_args(["nodes", "--refresh", "--json"])
        assert args.command == "nodes"
        assert args.refresh is True
        assert args.json is True


class TestCheckCommand:
    def test_check_valid(self, write_config, capsys):
        path = write_config('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        with pytest.raises(SystemExit) as exc_info:
            sys.argv = ["kraymini", "check", "-c", str(path)]
            main()
        assert exc_info.value.code == 0
        assert "OK" in capsys.readouterr().out

    def test_check_invalid(self, write_config):
        path = write_config("[general]\n")
        with pytest.raises(SystemExit) as exc_info:
            sys.argv = ["kraymini", "check", "-c", str(path)]
            main()
        assert exc_info.value.code == 1


class TestVersionCommand:
    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            sys.argv = ["kraymini", "version"]
            main()
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "kraymini" in out and __version__ in out


class TestRunCommand:
    @patch("kraymini.scheduler.Daemon")
    @patch("kraymini.cli.logger.info")
    @patch("kraymini.cli.setup_logging")
    @patch("kraymini.cli.load_config")
    @patch("kraymini.cli.find_config")
    def test_logs_version_and_python_on_startup(
        self,
        mock_find_config,
        mock_load_config,
        _mock_setup_logging,
        mock_logger_info,
        mock_daemon_cls,
        tmp_path,
    ):
        cfg = KrayminiConfig(
            subscriptions=[SubscriptionConfig(url="https://example.com/sub")],
            general=GeneralConfig(output_config=str(tmp_path / "xray.json")),
        )
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        mock_find_config.return_value = config_path
        mock_load_config.return_value = cfg

        assert cmd_run(str(config_path)) == 0

        mock_logger_info.assert_called_once_with(
            "Kraymini version %s, using Python %s",
            __version__,
            platform.python_version(),
        )
        mock_daemon_cls.assert_called_once_with(cfg, str(config_path))
        mock_daemon_cls.return_value.run.assert_called_once_with()


class TestGenconfigCommand:
    @patch("kraymini.process.XrayProcess.check_available", return_value=False)
    @patch("kraymini.cli.SubscriptionManager")
    @patch("kraymini.cli.setup_logging")
    @patch("kraymini.cli.load_config")
    @patch("kraymini.cli.find_config")
    def test_checks_xray_before_online_subscription_refresh(
        self,
        mock_find_config,
        mock_load_config,
        _mock_setup_logging,
        mock_mgr_cls,
        mock_check_available,
        tmp_path,
    ):
        cfg = KrayminiConfig(
            subscriptions=[SubscriptionConfig(url="https://example.com/sub")],
            general=GeneralConfig(output_config=str(tmp_path / "xray.json")),
        )
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        mock_find_config.return_value = config_path
        mock_load_config.return_value = cfg
        mock_mgr_cls.return_value = MagicMock()

        assert cmd_genconfig(str(config_path), None, offline=False) == 2
        mock_check_available.assert_called_once_with()
        mock_mgr_cls.return_value.refresh.assert_not_called()

    @patch("kraymini.process.XrayProcess.validate_config", return_value=True)
    @patch("kraymini.cli.setup_logging")
    @patch("kraymini.cli.load_config")
    @patch("kraymini.cli.find_config")
    def test_offline_genconfig_reports_cache_saved_at(
        self,
        mock_find_config,
        mock_load_config,
        _mock_setup_logging,
        _mock_validate_config,
        tmp_path,
        capsys,
    ):
        cfg = KrayminiConfig(
            subscriptions=[SubscriptionConfig(url="https://example.com/sub")],
            general=GeneralConfig(output_config=str(tmp_path / "xray.json")),
        )
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        mock_find_config.return_value = config_path
        mock_load_config.return_value = cfg
        cache_path = tmp_path / "nodes-cache-test.json"
        save_cache([Node(
            raw_uri="vless://uuid@host:443?type=tcp&security=none#node-1",
            remark="node-1",
            protocol="vless",
            address="host",
            port=443,
            credentials={"uuid": "uuid"},
            transport={"network": "tcp"},
            source="test",
        )], cache_path)

        with patch("kraymini.cli.get_cache_path", return_value=cache_path):
            assert cmd_genconfig(str(config_path), None, offline=True) == 0

        assert "使用本地缓存（保存于" in capsys.readouterr().err


class TestNodesCommand:
    def _node(self, uri="vless://uuid@host:443?type=tcp&security=none#node-1", remark="node-1", source="test"):
        return Node(
            raw_uri=uri,
            remark=remark,
            protocol="vless",
            address="host",
            port=443,
            credentials={"uuid": "uuid"},
            transport={"network": "tcp"},
            source=source,
        )

    @patch("kraymini.cli.setup_logging")
    @patch("kraymini.cli.load_config")
    @patch("kraymini.cli.find_config")
    def test_reads_cache_by_default(
        self,
        mock_find_config,
        mock_load_config,
        _mock_setup_logging,
        tmp_path,
        capsys,
    ):
        cfg = KrayminiConfig(
            subscriptions=[SubscriptionConfig(url="https://example.com/sub")],
            general=GeneralConfig(output_config=str(tmp_path / "xray.json")),
        )
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        mock_find_config.return_value = config_path
        mock_load_config.return_value = cfg
        cache_path = tmp_path / "nodes-cache-test.json"
        save_cache([self._node()], cache_path)

        with patch("kraymini.cli.get_cache_path", return_value=cache_path):
            assert cmd_nodes(str(config_path), refresh=False, as_json=False) == 0

        out = capsys.readouterr().out
        assert "node-1" in out
        assert "共 1 个节点" in out

    @patch("kraymini.cli.setup_logging")
    @patch("kraymini.cli.load_config")
    @patch("kraymini.cli.find_config")
    def test_returns_2_when_cache_missing(
        self,
        mock_find_config,
        mock_load_config,
        _mock_setup_logging,
        tmp_path,
        capsys,
    ):
        cfg = KrayminiConfig(
            subscriptions=[SubscriptionConfig(url="https://example.com/sub")],
            general=GeneralConfig(output_config=str(tmp_path / "xray.json")),
        )
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        mock_find_config.return_value = config_path
        mock_load_config.return_value = cfg

        with patch(
            "kraymini.cli.get_cache_path",
            return_value=tmp_path / "missing-cache.json",
        ):
            assert cmd_nodes(str(config_path), refresh=False, as_json=False) == 2

        assert "缓存不存在" in capsys.readouterr().err

    @patch("kraymini.cli.SubscriptionManager")
    @patch("kraymini.cli.setup_logging")
    @patch("kraymini.cli.load_config")
    @patch("kraymini.cli.find_config")
    def test_refresh_uses_subscription_manager(
        self,
        mock_find_config,
        mock_load_config,
        _mock_setup_logging,
        mock_mgr_cls,
        tmp_path,
        capsys,
    ):
        cfg = KrayminiConfig(
            subscriptions=[SubscriptionConfig(url="https://example.com/sub")],
            general=GeneralConfig(output_config=str(tmp_path / "xray.json")),
        )
        config_path = tmp_path / "config.toml"
        config_path.write_text('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        mock_find_config.return_value = config_path
        mock_load_config.return_value = cfg
        mock_mgr = MagicMock()
        mock_mgr.refresh.return_value = [self._node()]
        mock_mgr_cls.return_value = mock_mgr

        assert cmd_nodes(str(config_path), refresh=True, as_json=True) == 0

        out = capsys.readouterr().out
        assert '"remark": "node-1"' in out
        mock_mgr_cls.assert_called_once_with(cfg, str(config_path), runtime_dir=str(tmp_path))
        mock_mgr.refresh.assert_called_once_with()
