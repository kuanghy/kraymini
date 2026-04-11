import sys

import pytest

from kraymini.cli import build_parser, main


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
        assert "kraymini" in out and "0.1.0" in out
