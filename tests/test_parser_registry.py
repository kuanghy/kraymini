import base64, json, pytest
from kraymini.parser import parse_uri, ParseError
class TestRegistry:
    def test_vmess(self):
        d = {"v":"2","ps":"t","add":"1.2.3.4","port":"443","id":"u","aid":"0","scy":"auto","net":"tcp","type":"","host":"","path":"","tls":"","sni":"","alpn":"","fp":""}
        assert parse_uri(f"vmess://{base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip('=')}").protocol == "vmess"
    def test_vless(self):
        assert parse_uri("vless://uuid@host:443?type=tcp&security=none#t").protocol == "vless"
    def test_trojan(self):
        assert parse_uri("trojan://pw@host:443?type=tcp&security=tls&sni=host#t").protocol == "trojan"
    def test_ss(self):
        u = base64.urlsafe_b64encode(b"aes-256-gcm:pw").decode().rstrip("=")
        assert parse_uri(f"ss://{u}@host:443#t").protocol == "ss"
    def test_hy2(self):
        assert parse_uri("hy2://pw@host:443#t").protocol == "hysteria2"
    def test_unknown(self):
        with pytest.raises(ParseError, match="不支持的协议"): parse_uri("unknown://x")
    def test_bad_vmess(self):
        with pytest.raises(ParseError): parse_uri("vmess://not-valid!!!")
