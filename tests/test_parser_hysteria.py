from kraymini.parser import parse_uri
from kraymini.parser.hysteria import parse


class TestHysteria2Parser:
    def test_basic(self):
        node = parse("hy2://my-pw@hy2.com:443?sni=hy2.com&insecure=0#HY2-JP")
        assert node.protocol == "hysteria2" and node.credentials["password"] == "my-pw" and node.transport["insecure"] is False
    def test_obfs(self):
        node = parse("hy2://pw@host:443?sni=host&obfs=salamander&obfs-password=op#obfs")
        assert node.transport["obfs"] == "salamander" and node.transport["obfs_password"] == "op"
    def test_insecure(self):
        assert parse("hy2://pw@host:443?insecure=1#t").transport["insecure"] is True
    def test_encoded_remark(self):
        assert parse("hy2://pw@host:443#%E9%A6%99%E6%B8%AF").remark == "香港"

    def test_registry_supports_hysteria2_prefix(self):
        node = parse_uri("hysteria2://pw@host:443?sni=host#HY2")
        assert node.protocol == "hysteria2"
