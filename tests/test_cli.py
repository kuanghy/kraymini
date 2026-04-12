import sys
from unittest.mock import MagicMock, patch

import pytest

from kraymini.cli import build_parser, cmd_genconfig, main
from kraymini.config import GeneralConfig, KrayminiConfig, SubscriptionConfig


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
        assert "kraymini" in out and "0.1.2" in out


class TestGenconfigCommand:
    @patch("kraymini.process.XrayProcess.check_available", return_value=False)
    @patch("kraymini.subscription.SubscriptionManager")
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
