import base64
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from unittest.mock import patch

import pytest

from kraymini.subscription import (
    fetch_subscription, FetchError,
    deduplicate_nodes, assign_names, filter_nodes,
    save_cache, load_cache, get_cache_path,
    SubscriptionManager,
)
from kraymini.models import Node
from kraymini.config import KrayminiConfig, SubscriptionConfig


SAMPLE_URIS = [
    "vless://uuid@host1:443?type=tcp&security=none#node1",
    "trojan://pw@host2:443?type=tcp&security=tls&sni=host2#node2",
]


class MockHandler(BaseHTTPRequestHandler):
    response_body = b""
    status_code = 200

    def do_GET(self):
        self.send_response(self.status_code)
        self.end_headers()
        self.wfile.write(self.response_body)

    def log_message(self, format, *args):
        pass


@pytest.fixture
def mock_server():
    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    yield server
    server.shutdown()


def _node(uri="vless://a", remark="test", source="", address="host"):
    return Node(raw_uri=uri, remark=remark, protocol="vless",
                address=address, port=443, credentials={}, transport={}, source=source)


class TestFetchSubscription:
    def test_fetch_and_decode(self, mock_server):
        raw = "\n".join(SAMPLE_URIS)
        MockHandler.response_body = base64.b64encode(raw.encode())
        MockHandler.status_code = 200
        host, port = mock_server.server_address
        uris = fetch_subscription(f"http://{host}:{port}/sub")
        assert len(uris) == 2
        assert uris[0] == SAMPLE_URIS[0]

    def test_fetch_with_blank_lines(self, mock_server):
        raw = f"\n{SAMPLE_URIS[0]}\n\n{SAMPLE_URIS[1]}\n\n"
        MockHandler.response_body = base64.b64encode(raw.encode())
        MockHandler.status_code = 200
        host, port = mock_server.server_address
        uris = fetch_subscription(f"http://{host}:{port}/sub")
        assert len(uris) == 2

    def test_fetch_http_error(self, mock_server):
        MockHandler.status_code = 500
        MockHandler.response_body = b"error"
        host, port = mock_server.server_address
        with pytest.raises(FetchError):
            fetch_subscription(f"http://{host}:{port}/sub")

    def test_fetch_timeout(self):
        with pytest.raises(FetchError):
            fetch_subscription("http://192.0.2.1:1/sub", timeout=1, retries=1)


class TestDeduplicateNodes:
    def test_dedup_by_endpoint(self):
        n1 = Node(raw_uri="uri-1", remark="a", protocol="vless",
                  address="host1", port=443, credentials={"uuid": "u1"}, transport={})
        n2 = Node(raw_uri="uri-2", remark="b", protocol="vless",
                  address="host2", port=443, credentials={"uuid": "u2"}, transport={})
        n3 = Node(raw_uri="uri-3", remark="c", protocol="vless",
                  address="host1", port=443, credentials={"uuid": "u1"}, transport={})
        result = deduplicate_nodes([n1, n2, n3])
        assert len(result) == 2
        assert result[0].remark == "a"

    def test_same_host_different_credentials(self):
        n1 = Node(raw_uri="vless://uuid1@host:443", remark="a", protocol="vless",
                  address="host", port=443, credentials={"uuid": "uuid-1"}, transport={})
        n2 = Node(raw_uri="vless://uuid2@host:443", remark="b", protocol="vless",
                  address="host", port=443, credentials={"uuid": "uuid-2"}, transport={})
        assert len(deduplicate_nodes([n1, n2])) == 2


class TestAssignNames:
    def test_empty_remark_with_source(self):
        nodes = [_node("uri", remark="", source="provider-a")]
        assert assign_names(nodes)[0].remark == "provider-a-0"

    def test_empty_remark_no_source(self):
        nodes = [_node("uri", remark="", source="")]
        assert assign_names(nodes)[0].remark == "sub-0"

    def test_reserved_tag_conflict(self):
        nodes = [_node("uri-1", remark="direct"), _node("uri-2", remark="blocked")]
        result = assign_names(nodes)
        assert result[0].remark == "direct_node"
        assert result[1].remark == "blocked_node"

    def test_duplicate_names(self):
        nodes = [_node("u1", "香港-01"), _node("u2", "香港-01"), _node("u3", "香港-01")]
        result = assign_names(nodes)
        assert result[0].remark == "香港-01"
        assert result[1].remark == "香港-01_2"
        assert result[2].remark == "香港-01_3"

    def test_reserved_then_dedup(self):
        nodes = [_node("u1", "direct"), _node("u2", "direct")]
        result = assign_names(nodes)
        assert result[0].remark == "direct_node"
        assert result[1].remark == "direct_node_2"


class TestFilterNodes:
    def test_no_filter(self):
        nodes = [_node("u1", "香港"), _node("u2", "美国"), _node("u3", "日本")]
        assert len(filter_nodes(nodes, [], [])) == 3

    def test_include_only(self):
        nodes = [_node("u1", "香港-01"), _node("u2", "美国-01"), _node("u3", "日本-01")]
        result = filter_nodes(nodes, ["香港", "美国"], [])
        assert len(result) == 2

    def test_exclude_only(self):
        nodes = [_node("u1", "香港"), _node("u2", "剩余流量"), _node("u3", "到期时间")]
        assert len(filter_nodes(nodes, [], ["剩余流量", "到期时间"])) == 1

    def test_include_then_exclude(self):
        nodes = [_node("u1", "香港-高速"), _node("u2", "香港-低速"), _node("u3", "美国-高速")]
        result = filter_nodes(nodes, ["香港"], ["低速"])
        assert len(result) == 1 and result[0].remark == "香港-高速"

    def test_case_insensitive(self):
        nodes = [_node("u1", "HK-Node"), _node("u2", "US-Node")]
        assert len(filter_nodes(nodes, ["hk"], [])) == 1

    def test_include_by_address(self):
        nodes = [
            _node("u1", "节点-A", address="hk.example.com"),
            _node("u2", "节点-B", address="us.example.com"),
        ]
        result = filter_nodes(nodes, ["hk.example"], [])
        assert len(result) == 1 and result[0].remark == "节点-A"

    def test_exclude_by_address(self):
        nodes = [
            _node("u1", "香港", address="1.2.3.4"),
            _node("u2", "香港", address="5.6.7.8"),
        ]
        assert len(filter_nodes(nodes, [], ["1.2.3"])) == 1

    def test_case_insensitive_address(self):
        nodes = [_node("u1", "x", address="AbC.example.com")]
        assert len(filter_nodes(nodes, ["abc"], [])) == 1


class TestNodeCache:
    def test_save_and_load(self, tmp_path):
        nodes = [_node("uri-1", "node1", "src1"), _node("uri-2", "node2", "src2")]
        cache_path = tmp_path / "cache.json"
        save_cache(nodes, cache_path)
        loaded = load_cache(cache_path)
        assert len(loaded) == 2 and loaded[0].raw_uri == "uri-1"

    def test_load_nonexistent(self, tmp_path):
        assert load_cache(tmp_path / "no.json") is None

    def test_load_corrupted(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json{{{")
        assert load_cache(p) is None

    def test_load_invalid_structure(self, tmp_path):
        p = tmp_path / "bad2.json"
        p.write_text('"just a string"')
        assert load_cache(p) is None

    def test_cache_path_from_config(self):
        p1 = get_cache_path("/etc/kraymini/config.toml", "~/.kraymini")
        p2 = get_cache_path("/home/user/.kraymini/config.toml", "~/.kraymini")
        assert p1 != p2 and p1.name.startswith("nodes-cache-")


class TestSubscriptionManager:
    def _make_config(self, tmp_path, subs=None):
        config_path = tmp_path / "config.toml"
        config_path.write_text("")
        if subs is None:
            subs = [SubscriptionConfig(url="https://example.com/sub", name="test")]
        return KrayminiConfig(subscriptions=subs), config_path

    @patch("kraymini.subscription.fetch_subscription")
    def test_refresh_success(self, mock_fetch, tmp_path):
        mock_fetch.return_value = [
            "vless://uuid@host1:443?type=tcp&security=none#node1",
            "trojan://pw@host2:443?type=tcp&security=tls&sni=host2#node2",
        ]
        cfg, cp = self._make_config(tmp_path)
        mgr = SubscriptionManager(cfg, str(cp), runtime_dir=str(tmp_path))
        nodes = mgr.refresh()
        assert nodes is not None and len(nodes) == 2

    @patch("kraymini.subscription.fetch_subscription")
    def test_refresh_partial_failure(self, mock_fetch, tmp_path):
        cfg, cp = self._make_config(tmp_path, subs=[
            SubscriptionConfig(url="https://a.com/sub", name="a"),
            SubscriptionConfig(url="https://b.com/sub", name="b"),
        ])
        mock_fetch.side_effect = [
            FetchError("fail"),
            ["vless://uuid@host:443?type=tcp&security=none#node-b"],
        ]
        mgr = SubscriptionManager(cfg, str(cp), runtime_dir=str(tmp_path))
        assert len(mgr.refresh()) == 1

    @patch("kraymini.subscription.fetch_subscription")
    def test_refresh_all_fail_with_cache(self, mock_fetch, tmp_path):
        cfg, cp = self._make_config(tmp_path)
        mgr = SubscriptionManager(cfg, str(cp), runtime_dir=str(tmp_path))
        save_cache([_node("cached-uri", "cached-node")], mgr.cache_path)
        mock_fetch.side_effect = FetchError("all fail")
        nodes = mgr.refresh()
        assert nodes is not None and len(nodes) == 1

    @patch("kraymini.subscription.fetch_subscription")
    def test_refresh_all_fail_no_cache(self, mock_fetch, tmp_path):
        cfg, cp = self._make_config(tmp_path)
        mgr = SubscriptionManager(cfg, str(cp), runtime_dir=str(tmp_path))
        mock_fetch.side_effect = FetchError("all fail")
        assert mgr.refresh() is None

    @patch("kraymini.subscription.fetch_subscription")
    def test_nodes_changed(self, mock_fetch, tmp_path):
        cfg, cp = self._make_config(tmp_path)
        mgr = SubscriptionManager(cfg, str(cp), runtime_dir=str(tmp_path))
        mock_fetch.return_value = ["vless://uuid@host:443?type=tcp&security=none#n1"]
        nodes1 = mgr.refresh()
        assert mgr.nodes_changed(None, nodes1) is True
        assert mgr.nodes_changed(nodes1, nodes1) is False
        assert mgr.nodes_changed(nodes1, [_node("diff-uri")]) is True
