from kraymini.parser.vless import parse


class TestVlessParser:
    def test_ws_tls(self):
        node = parse("vless://a3482e88@ws.example.com:443?type=ws&security=tls&path=%2Fws&host=ws.example.com&sni=ws.example.com&fp=chrome#香港-WS")
        assert node.protocol == "vless" and node.remark == "香港-WS" and node.transport["network"] == "ws"

    def test_reality(self):
        node = parse("vless://uuid@host:443?type=tcp&security=reality&sni=ms.com&fp=chrome&pbk=abc&sid=def&spx=%2F#R")
        assert node.transport["public_key"] == "abc" and node.transport["short_id"] == "def"

    def test_grpc(self):
        node = parse("vless://uuid@host:443?type=grpc&security=tls&serviceName=mygrpc&sni=host&fp=chrome#gRPC")
        assert node.transport["service_name"] == "mygrpc"

    def test_flow(self):
        node = parse("vless://uuid@host:443?type=tcp&security=reality&flow=xtls-rprx-vision&sni=s&fp=c&pbk=k&sid=i#X")
        assert node.credentials["flow"] == "xtls-rprx-vision"

    def test_encoded_remark(self):
        assert parse("vless://uuid@host:443?type=tcp&security=none#%E7%BE%8E%E5%9B%BD-01").remark == "美国-01"

    def test_raw_uri(self):
        uri = "vless://uuid@host:443?type=tcp&security=none#test"
        assert parse(uri).raw_uri == uri

    def test_xhttp(self):
        node = parse("vless://uuid@host:443?type=xhttp&security=tls&path=%2Fxhttp&host=cdn.example.com&mode=auto&sni=cdn.example.com#XHTTP")
        assert node.transport["network"] == "xhttp"
        assert node.transport["path"] == "/xhttp"
        assert node.transport["host"] == "cdn.example.com"
        assert node.transport["xhttp_mode"] == "auto"

    def test_xhttp_no_mode(self):
        node = parse("vless://uuid@host:443?type=xhttp&path=%2Fx&sni=host#t")
        assert node.transport["network"] == "xhttp"
        assert "xhttp_mode" not in node.transport

    def test_splithttp_normalized_to_xhttp(self):
        """splithttp 应被规范化为 xhttp"""
        node = parse("vless://uuid@host:443?type=splithttp&path=%2Fs&mode=stream-up&sni=host#t")
        assert node.transport["network"] == "xhttp"
        assert node.transport["xhttp_mode"] == "stream-up"

    def test_httpupgrade(self):
        node = parse("vless://uuid@host:443?type=httpupgrade&security=tls&path=%2Fup&host=cdn.example.com&sni=cdn.example.com#HU")
        assert node.transport["network"] == "httpupgrade"
        assert node.transport["path"] == "/up"
        assert node.transport["host"] == "cdn.example.com"
