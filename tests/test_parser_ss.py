import base64
from kraymini.parser.shadowsocks import parse
class TestSSParser:
    def test_sip002(self):
        u = base64.urlsafe_b64encode(b"aes-256-gcm:my-pw").decode().rstrip("=")
        node = parse(f"ss://{u}@ss.com:8388#SS-HK")
        assert node.protocol == "ss" and node.credentials["method"] == "aes-256-gcm" and node.port == 8388
    def test_legacy(self):
        p = base64.urlsafe_b64encode(b"aes-128-gcm:pw@1.2.3.4:443").decode().rstrip("=")
        node = parse(f"ss://{p}#Legacy")
        assert node.address == "1.2.3.4" and node.port == 443
    def test_chacha20(self):
        u = base64.urlsafe_b64encode(b"chacha20-ietf-poly1305:secret").decode().rstrip("=")
        assert parse(f"ss://{u}@host:1234#t").credentials["method"] == "chacha20-ietf-poly1305"
    def test_encoded_remark(self):
        u = base64.urlsafe_b64encode(b"aes-256-gcm:pw").decode().rstrip("=")
        assert parse(f"ss://{u}@host:443#%E7%BE%8E%E5%9B%BD").remark == "美国"
    def test_no_remark(self):
        u = base64.urlsafe_b64encode(b"aes-256-gcm:pw").decode().rstrip("=")
        assert parse(f"ss://{u}@host:443").remark == ""
