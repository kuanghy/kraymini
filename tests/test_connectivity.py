import pytest
from unittest.mock import MagicMock, patch

from kraymini.connectivity import (
    ProbeResult,
    _http_proxy_base,
    check_local_connectivity,
    check_proxy_connectivity,
    parse_tcp_target,
)


class TestParseTcpTarget:
    def test_ipv4(self):
        assert parse_tcp_target("223.5.5.5:443") == ("223.5.5.5", 443)

    def test_ipv6_bracketed(self):
        assert parse_tcp_target("[::1]:443") == ("::1", 443)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            parse_tcp_target("")

    def test_no_port_raises(self):
        with pytest.raises(ValueError):
            parse_tcp_target("host-only")


class TestCheckProxyConnectivity:
    class _FakeResp:
        def read(self, n: int = -1) -> bytes:
            return b"x"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    @patch("kraymini.connectivity.build_opener")
    def test_success_returns_latency(self, mock_build_opener):
        opener = MagicMock()
        opener.open.return_value = self._FakeResp()
        mock_build_opener.return_value = opener
        r = check_proxy_connectivity(
            listen="127.0.0.1",
            mixed_port=18080,
            probe_url="https://example.com/gen204",
            timeout=5.0,
        )
        assert r.ok is True
        assert r.latency_ms is not None
        assert r.latency_ms >= 0
        assert r.error is None
        opener.open.assert_called_once()

    @patch("kraymini.connectivity.build_opener")
    def test_failure_returns_error(self, mock_build_opener):
        from urllib.error import URLError

        opener = MagicMock()
        opener.open.side_effect = URLError("boom")
        mock_build_opener.return_value = opener
        r = check_proxy_connectivity(
            listen="127.0.0.1",
            mixed_port=18080,
            probe_url="https://example.com/gen204",
            timeout=5.0,
        )
        assert r.ok is False
        assert r.latency_ms is None
        assert r.error is not None


class TestCheckLocalConnectivity:
    @staticmethod
    def _conn_context():
        cm = MagicMock()
        cm.__enter__.return_value = None
        cm.__exit__.return_value = None
        return cm

    @patch("kraymini.connectivity.socket.create_connection")
    def test_true_on_first_success(self, mock_conn):
        mock_conn.return_value = self._conn_context()
        assert check_local_connectivity(
            ["127.0.0.1:9", "223.5.5.5:443"],
            timeout=1.0,
        ) is True
        assert mock_conn.call_count == 1

    @patch("kraymini.connectivity.socket.create_connection")
    def test_true_on_second_target(self, mock_conn):
        mock_conn.side_effect = [
            OSError("refused"),
            self._conn_context(),
        ]
        assert check_local_connectivity(
            ["127.0.0.1:9", "223.5.5.5:443"],
            timeout=1.0,
        ) is True
        assert mock_conn.call_count == 2

    @patch("kraymini.connectivity.socket.create_connection")
    def test_false_when_all_fail(self, mock_conn):
        mock_conn.side_effect = OSError("fail")
        assert check_local_connectivity(
            ["127.0.0.1:9", "127.0.0.1:8"],
            timeout=1.0,
        ) is False

    def test_skips_invalid_target_strings(self):
        with patch("kraymini.connectivity.socket.create_connection") as mock_conn:
            mock_conn.side_effect = OSError("x")
            assert check_local_connectivity(
                ["bad-target", "127.0.0.1:9"],
                timeout=1.0,
            ) is False


class TestProbeResult:
    def test_frozen(self):
        r = ProbeResult(ok=True, latency_ms=10, error=None)
        assert r.ok and r.latency_ms == 10


class TestHttpProxyBase:
    def test_loopback(self):
        assert _http_proxy_base("127.0.0.1", 10808) == "http://127.0.0.1:10808"

    def test_ipv4_wildcard_falls_back_to_loopback(self):
        assert _http_proxy_base("0.0.0.0", 10808) == "http://127.0.0.1:10808"

    def test_ipv6_loopback_bracketed(self):
        assert _http_proxy_base("::1", 10808) == "http://[::1]:10808"

    def test_ipv6_wildcard_falls_back_to_loopback(self):
        assert _http_proxy_base("::", 10808) == "http://[::1]:10808"

    def test_hostname_passthrough(self):
        assert _http_proxy_base("proxy.local", 10808) == "http://proxy.local:10808"
