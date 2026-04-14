import stat
import pytest
from kraymini.process import XrayProcess, XrayError


@pytest.fixture
def fake_xray(tmp_path):
    script = tmp_path / "fake_xray"
    script.write_text(
        '#!/bin/sh\n'
        'if [ "$1" = "version" ]; then\n'
        '    echo "Xray 25.3.6"\n'
        '    exit 0\n'
        'fi\n'
        'if [ "$1" = "run" ] && [ "$2" = "-test" ]; then\n'
        '    echo "Configuration OK"\n'
        '    exit 0\n'
        'fi\n'
        'if [ "$1" = "run" ] && [ "$2" = "-c" ]; then\n'
        '    while true; do sleep 1; done\n'
        'fi\n',
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


@pytest.fixture
def bad_xray(tmp_path):
    script = tmp_path / "bad_xray"
    script.write_text('#!/bin/sh\necho "invalid config" >&2\nexit 1\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


class TestXrayProcess:
    def test_check_available_logs_version(self, fake_xray, caplog):
        caplog.set_level("INFO", logger="kraymini")
        assert XrayProcess(fake_xray).check_available() is True
        assert "Xray 25.3.6" in caplog.text

    def test_validate_pass(self, fake_xray, tmp_path):
        cfg = tmp_path / "xray.json"
        cfg.write_text("{}")
        assert XrayProcess(fake_xray).validate_config(str(cfg)) is True

    def test_validate_fail(self, bad_xray, tmp_path):
        cfg = tmp_path / "xray.json"
        cfg.write_text("{}")
        assert XrayProcess(bad_xray).validate_config(str(cfg)) is False

    def test_start_and_stop(self, fake_xray, tmp_path):
        cfg = tmp_path / "xray.json"
        cfg.write_text("{}")
        proc = XrayProcess(fake_xray)
        try:
            proc.start(str(cfg))
            assert proc.is_running()
        finally:
            proc.stop()
        assert not proc.is_running()

    def test_start_redirects_xray_logs_to_configured_file(self, fake_xray, tmp_path):
        cfg = tmp_path / "xray.json"
        cfg.write_text("{}")
        kraymini_log = tmp_path / "kraymini.log"
        proc = XrayProcess(fake_xray)
        try:
            proc.start(str(cfg), log_file=str(kraymini_log))
            assert proc.is_running()
            assert kraymini_log.exists()
        finally:
            proc.stop()

    def test_stop_without_start(self, fake_xray):
        XrayProcess(fake_xray).stop()

    def test_not_found(self):
        with pytest.raises(XrayError, match="不存在"):
            XrayProcess("/nonexistent/xray").start("/tmp/config.json")
