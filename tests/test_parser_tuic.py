from kraymini.parser import parse_uri
from kraymini.parser.tuic import parse


class TestTuicParser:
    def test_basic(self):
        node = parse(
            "tuic://user-uuid:my-password@tuic.example.com:443"
            "?sni=tuic.example.com&congestion_control=bbr#TUIC-JP"
        )
        assert node.protocol == "tuic"
        assert node.credentials["uuid"] == "user-uuid"
        assert node.credentials["password"] == "my-password"
        assert node.address == "tuic.example.com"
        assert node.port == 443
        assert node.remark == "TUIC-JP"
        assert node.transport["security"] == "tls"
        assert node.transport["sni"] == "tuic.example.com"
        assert node.transport["congestion_control"] == "bbr"
        assert node.transport["insecure"] is False

    def test_insecure(self):
        node = parse("tuic://uuid:pw@host:443?insecure=1#t")
        assert node.transport["insecure"] is True

    def test_congestion_control_cc_alias(self):
        """支持缩写参数名 cc"""
        node = parse("tuic://uuid:pw@host:443?cc=cubic#t")
        assert node.transport["congestion_control"] == "cubic"

    def test_udp_relay_mode(self):
        node = parse("tuic://uuid:pw@host:443?udp_relay_mode=quic#t")
        assert node.transport["udp_relay_mode"] == "quic"

    def test_zero_rtt(self):
        node = parse("tuic://uuid:pw@host:443?zero_rtt_handshake=1#t")
        assert node.transport["zero_rtt"] is True

    def test_zero_rtt_default_false(self):
        node = parse("tuic://uuid:pw@host:443#t")
        assert node.transport["zero_rtt"] is False

    def test_alpn(self):
        node = parse("tuic://uuid:pw@host:443?alpn=h3#t")
        assert node.transport["alpn"] == "h3"

    def test_fingerprint(self):
        node = parse("tuic://uuid:pw@host:443?fp=firefox#t")
        assert node.transport["fingerprint"] == "firefox"

    def test_fingerprint_default_chrome(self):
        node = parse("tuic://uuid:pw@host:443#t")
        assert node.transport["fingerprint"] == "chrome"

    def test_encoded_remark(self):
        node = parse("tuic://uuid:pw@host:443#%E9%A6%99%E6%B8%AF")
        assert node.remark == "香港"

    def test_encoded_password(self):
        node = parse("tuic://uuid:my%40password@host:443#t")
        assert node.credentials["password"] == "my@password"

    def test_raw_uri_preserved(self):
        uri = "tuic://uuid:pw@host:443?sni=host#test"
        assert parse(uri).raw_uri == uri

    def test_registry(self):
        node = parse_uri(
            "tuic://u:p@host:443?sni=host&congestion_control=bbr#node"
        )
        assert node.protocol == "tuic"

    def test_network_is_tuic(self):
        node = parse("tuic://uuid:pw@host:443#t")
        assert node.transport["network"] == "tuic"
