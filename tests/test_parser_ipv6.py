import base64
import json

import pytest

from kraymini.generator import generate_node_outbound
from kraymini.parser import parse_uri, ParseError
from kraymini.parser._utils import normalize_server_address


class TestNormalizeServerAddress:
    def test_strip_brackets(self):
        assert normalize_server_address("[2001:db8::1]") == "2001:db8::1"

    def test_domain_unchanged(self):
        assert normalize_server_address("hk.example.com") == "hk.example.com"

    def test_bare_ipv6_unchanged(self):
        assert normalize_server_address("2001:db8::1") == "2001:db8::1"

    def test_empty_brackets_raises(self):
        with pytest.raises(ValueError, match="方括号内为空"):
            normalize_server_address("[]")

    def test_bracketed_domain_raises(self):
        with pytest.raises(ValueError, match="不是合法的 IPv6"):
            normalize_server_address("[example.com]")

    def test_bracketed_ipv4_raises(self):
        with pytest.raises(ValueError, match="须为 IPv6"):
            normalize_server_address("[127.0.0.1]")


class TestParseUriIpv6:
    def test_ss_bracketed(self):
        node = parse_uri("ss://aes-256-gcm:pw@[2001:db8::1]:443#r")
        assert node.address == "2001:db8::1"
        assert node.port == 443

    def test_ss_raw(self):
        node = parse_uri("ss://aes-256-gcm:pw@2001:db8::1:443#r")
        assert node.address == "2001:db8::1"
        assert node.port == 443

    def test_vless_bracketed(self):
        node = parse_uri(
            "vless://uuid@[2001:db8::1]:443?encryption=none&security=none#r"
        )
        assert node.address == "2001:db8::1"
        assert node.port == 443

    def test_trojan_bracketed(self):
        node = parse_uri("trojan://pw@[2001:db8::1]:443#r")
        assert node.address == "2001:db8::1"
        assert node.port == 443

    def test_vmess_add(self):
        data = {
            "v": 2,
            "ps": "r",
            "add": "2001:db8::1",
            "port": "443",
            "id": "u",
            "aid": 0,
            "net": "tcp",
        }
        payload = base64.b64encode(json.dumps(data).encode()).decode()
        node = parse_uri(f"vmess://{payload}")
        assert node.address == "2001:db8::1"
        assert node.port == 443

    def test_vless_unbracketed_fails(self):
        with pytest.raises(Exception):
            parse_uri("vless://uuid@2001:db8::1:443?encryption=none#r")

    def test_ss_bracketed_domain_fails(self):
        with pytest.raises(ParseError, match="节点地址不合法"):
            parse_uri("ss://aes-256-gcm:pw@[not-ipv6.example.com]:443#r")


class TestGeneratorIpv6:
    def test_outbound_address_has_no_brackets(self):
        node = parse_uri("ss://aes-256-gcm:pw@[2001:db8::1]:443#r")
        ob = generate_node_outbound(node)
        addr = ob["settings"]["servers"][0]["address"]
        assert addr == "2001:db8::1"
        assert "[" not in addr
