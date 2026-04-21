import json
import subprocess

import pytest

from kraymini.stats import (
    format_bytes,
    format_traffic_log,
    query_inbound_traffic,
)


class TestFormatBytes:
    def test_zero(self):
        assert format_bytes(0) == "0 B"

    def test_below_kb(self):
        assert format_bytes(1023) == "1023 B"

    def test_exactly_kb(self):
        assert format_bytes(1024) == "1.00 KB"

    def test_large(self):
        # 2 * 1024^4 bytes -> 2.00 TB
        assert format_bytes(2 * 1024**4) == "2.00 TB"


class TestFormatTrafficLog:
    def test_contains_labels_and_sizes(self):
        s = format_traffic_log(100, 2048)
        assert "流量统计" in s
        assert "上行" in s and "下行" in s
        assert "100 B" in s
        assert "2.00 KB" in s


@pytest.fixture
def fake_bin(monkeypatch):
    monkeypatch.setattr("kraymini.stats.resolve_xray_bin", lambda _: "/fake/xray")


def _call():
    return query_inbound_traffic("xray", "127.0.0.1:10810", "in-mixed", timeout=5)


class TestQueryInboundTraffic:
    def test_success_with_int_value(self, monkeypatch, fake_bin):
        """xray 26.x 的 statsquery 计数器值是 JSON 数字。"""
        payload = {
            "stat": [
                {"name": "inbound>>>in-mixed>>>traffic>>>uplink", "value": 271386},
                {"name": "inbound>>>in-mixed>>>traffic>>>downlink", "value": 678008},
            ]
        }

        def fake_run(cmd, **kwargs):
            assert "statsquery" in cmd
            assert "inbound>>>in-mixed>>>traffic" in cmd
            return subprocess.CompletedProcess(cmd, 0, json.dumps(payload), "")

        monkeypatch.setattr("kraymini.stats.subprocess.run", fake_run)
        assert _call() == (271386, 678008)

    def test_success_with_string_value(self, monkeypatch, fake_bin):
        """兼容早期 xray 版本：计数器值序列化为字符串。"""
        payload = {
            "stat": [
                {"name": "inbound>>>in-mixed>>>traffic>>>uplink", "value": "100"},
                {"name": "inbound>>>in-mixed>>>traffic>>>downlink", "value": "200"},
            ]
        }

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, json.dumps(payload), "")

        monkeypatch.setattr("kraymini.stats.subprocess.run", fake_run)
        assert _call() == (100, 200)

    def test_mixed_value_types(self, monkeypatch, fake_bin):
        payload = {
            "stat": [
                {"name": "inbound>>>in-mixed>>>traffic>>>uplink", "value": 42},
                {"name": "inbound>>>in-mixed>>>traffic>>>downlink", "value": "84"},
            ]
        }

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, json.dumps(payload), "")

        monkeypatch.setattr("kraymini.stats.subprocess.run", fake_run)
        assert _call() == (42, 84)

    def test_value_bool_is_rejected(self, monkeypatch, fake_bin):
        """bool 是 int 的子类，需要显式排除以免被当成 0/1。"""
        payload = {
            "stat": [
                {"name": "inbound>>>in-mixed>>>traffic>>>uplink", "value": True},
                {"name": "inbound>>>in-mixed>>>traffic>>>downlink", "value": 1},
            ]
        }

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, json.dumps(payload), "")

        monkeypatch.setattr("kraymini.stats.subprocess.run", fake_run)
        # uplink 解析失败视为计数器不完整 -> 返回 None
        assert _call() is None

    def test_empty_stat_is_zero(self, monkeypatch, fake_bin):
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, '{"stat":[]}', "")

        monkeypatch.setattr("kraymini.stats.subprocess.run", fake_run)
        assert _call() == (0, 0)

    def test_timeout(self, monkeypatch, fake_bin):
        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 5))

        monkeypatch.setattr("kraymini.stats.subprocess.run", fake_run)
        assert _call() is None

    def test_oserror(self, monkeypatch, fake_bin):
        def fake_run(cmd, **kwargs):
            raise OSError("permission denied")

        monkeypatch.setattr("kraymini.stats.subprocess.run", fake_run)
        assert _call() is None

    def test_nonzero_exit(self, monkeypatch, fake_bin):
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 1, "", "err")

        monkeypatch.setattr("kraymini.stats.subprocess.run", fake_run)
        assert _call() is None

    def test_bad_json(self, monkeypatch, fake_bin):
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, "not-json", "")

        monkeypatch.setattr("kraymini.stats.subprocess.run", fake_run)
        assert _call() is None

    def test_no_matching_counters(self, monkeypatch, fake_bin):
        def fake_run(cmd, **kwargs):
            body = '{"stat":[{"name":"other","value":"1"}]}'
            return subprocess.CompletedProcess(cmd, 0, body, "")

        monkeypatch.setattr("kraymini.stats.subprocess.run", fake_run)
        assert _call() is None

    def test_partial_counters(self, monkeypatch, fake_bin):
        # 只有 uplink，没有 downlink —— 视作查询失败，不吞零
        def fake_run(cmd, **kwargs):
            body = (
                '{"stat":[{"name":"inbound>>>in-mixed>>>traffic>>>uplink",'
                '"value":"42"}]}'
            )
            return subprocess.CompletedProcess(cmd, 0, body, "")

        monkeypatch.setattr("kraymini.stats.subprocess.run", fake_run)
        assert _call() is None

    def test_missing_xray_bin(self):
        assert (
            query_inbound_traffic(
                "__no_such_xray_bin__",
                "127.0.0.1:10810",
                "in-mixed",
                timeout=5,
            )
            is None
        )
