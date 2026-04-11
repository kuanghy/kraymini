from kraymini.parser.trojan import parse
class TestTrojanParser:
    def test_basic(self):
        node = parse("trojan://my-pw@host:443?security=tls&sni=host&type=tcp&fp=chrome#Trojan-HK")
        assert node.protocol == "trojan" and node.credentials["password"] == "my-pw"
    def test_ws(self):
        node = parse("trojan://pw@host:443?type=ws&security=tls&path=%2Fws&host=ws.com&sni=ws.com#WS")
        assert node.transport["network"] == "ws" and node.transport["path"] == "/ws"
    def test_grpc(self):
        node = parse("trojan://pw@host:443?type=grpc&security=tls&serviceName=tgrpc&sni=host#gRPC")
        assert node.transport["service_name"] == "tgrpc"
    def test_special_password(self):
        assert parse("trojan://p%40ss%3Aword@host:443?type=tcp&security=tls&sni=host#t").credentials["password"] == "p@ss:word"
    def test_raw_uri(self):
        uri = "trojan://pw@host:443?type=tcp&security=tls&sni=host#t"
        assert parse(uri).raw_uri == uri
