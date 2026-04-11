import base64, json
from kraymini.parser.vmess import parse
from kraymini.models import Node

def _make_vmess_uri(overrides=None):
    data = {"v":"2","ps":"香港-01","add":"hk.example.com","port":"443","id":"a3482e88-686a-4a58-8126-99c9df64b7bf","aid":"0","scy":"auto","net":"ws","type":"","host":"hk.example.com","path":"/ws","tls":"tls","sni":"hk.example.com","alpn":"","fp":"chrome"}
    if overrides: data.update(overrides)
    return f"vmess://{base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip('=')}"

class TestVmessParser:
    def test_basic(self):
        node = parse(_make_vmess_uri())
        assert node.protocol == "vmess" and node.remark == "香港-01" and node.port == 443
        assert node.credentials["uuid"] == "a3482e88-686a-4a58-8126-99c9df64b7bf"
        assert node.transport["network"] == "ws" and node.transport["security"] == "tls"
    def test_tcp(self):
        node = parse(_make_vmess_uri({"net":"tcp","tls":""}))
        assert node.transport["network"] == "tcp"
    def test_grpc(self):
        node = parse(_make_vmess_uri({"net":"grpc","path":"svc"}))
        assert node.transport["service_name"] == "svc"
    def test_h2(self):
        node = parse(_make_vmess_uri({"net":"h2","host":"h2.com","path":"/h2"}))
        assert node.transport["network"] == "h2"
    def test_empty_remark(self):
        assert parse(_make_vmess_uri({"ps":""})).remark == ""
    def test_port_int(self):
        assert parse(_make_vmess_uri({"port":8443})).port == 8443
    def test_std_base64(self):
        data = {"v":"2","ps":"t","add":"1.2.3.4","port":"443","id":"u","aid":"0","scy":"auto","net":"tcp","type":"","host":"","path":"","tls":"","sni":"","alpn":"","fp":""}
        assert parse(f"vmess://{base64.b64encode(json.dumps(data).encode()).decode()}").address == "1.2.3.4"
