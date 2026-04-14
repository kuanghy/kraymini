import json
from pathlib import Path

from kraymini.generator import (
    generate_inbounds,
    generate_node_outbound,
    generate_landing_proxy_outbound,
    generate_landing_chain_outbound,
    landing_chain_tag,
    generate_fixed_outbounds,
    generate_balancer,
    generate_observatory,
    generate_routing,
    generate_dns,
    generate_api,
    generate_stats_policy,
    generate_xray_config,
    write_xray_config,
)
from kraymini.config import (
    InboundConfig,
    KrayminiConfig,
    SubscriptionConfig,
    LandingProxyConfig,
    TransportConfig,
    SecurityConfig,
    WsTransportConfig,
    GrpcTransportConfig,
    XhttpTransportConfig,
    HttpupgradeTransportConfig,
    ObservatoryConfig,
    RoutingConfig,
    RoutingRule,
    DnsConfig,
    DnsServer,
    LogConfig,
)
from kraymini.models import Node


def test_landing_chain_tag():
    assert landing_chain_tag("my-node") == "LP-Via: my-node"


def _vless_node(remark="node-1", address="host1", port=443):
    return Node(
        raw_uri="vless://...", remark=remark, protocol="vless",
        address=address, port=port,
        credentials={"uuid": "uuid1", "encryption": "none"},
        transport={"network": "tcp", "security": "none", "sni": "",
                    "fingerprint": "", "alpn": "", "host": "", "path": "",
                    "header_type": ""},
    )


class TestGenerateInbounds:
    def test_default(self):
        ibs = generate_inbounds(InboundConfig())
        assert len(ibs) == 3
        api = next(i for i in ibs if i["tag"] == "in-api")
        assert api["protocol"] == "dokodemo-door" and api["port"] == 10810
        socks = next(i for i in ibs if i["tag"] == "in-socks")
        assert socks["protocol"] == "socks" and socks["sniffing"]["enabled"] is True
        http = next(i for i in ibs if i["tag"] == "in-http")
        assert http["protocol"] == "http" and http["port"] == 10809

    def test_sniffing_disabled(self):
        socks = next(i for i in generate_inbounds(InboundConfig(sniffing=False)) if i["tag"] == "in-socks")
        assert socks.get("sniffing", {}).get("enabled") is not True

    def test_custom_listen(self):
        for ib in generate_inbounds(InboundConfig(listen="0.0.0.0")):
            assert ib["listen"] == "0.0.0.0"


class TestGenerateNodeOutbound:
    def test_vmess_ws_tls(self):
        node = Node(
            raw_uri="vmess://...", remark="HK-WS", protocol="vmess",
            address="hk.example.com", port=443,
            credentials={"uuid": "test-uuid", "alter_id": 0, "security": "auto"},
            transport={"network": "ws", "security": "tls", "sni": "hk.example.com",
                        "fingerprint": "chrome", "alpn": "", "host": "hk.example.com",
                        "path": "/ws", "header_type": ""},
        )
        ob = generate_node_outbound(node)
        assert ob["tag"] == "HK-WS" and ob["protocol"] == "vmess"
        assert ob["settings"]["vnext"][0]["users"][0]["id"] == "test-uuid"
        assert ob["streamSettings"]["network"] == "ws"
        assert ob["streamSettings"]["security"] == "tls"
        assert ob["streamSettings"]["wsSettings"]["path"] == "/ws"
        assert ob["streamSettings"]["tlsSettings"]["serverName"] == "hk.example.com"

    def test_vless_reality(self):
        node = Node(
            raw_uri="vless://...", remark="Reality", protocol="vless",
            address="1.2.3.4", port=443,
            credentials={"uuid": "uuid", "encryption": "none", "flow": "xtls-rprx-vision"},
            transport={"network": "tcp", "security": "reality", "sni": "www.microsoft.com",
                        "fingerprint": "chrome", "public_key": "pubkey", "short_id": "sid",
                        "spider_x": "/", "alpn": "", "host": "", "path": "", "header_type": ""},
        )
        ob = generate_node_outbound(node)
        assert ob["settings"]["vnext"][0]["users"][0]["flow"] == "xtls-rprx-vision"
        assert ob["streamSettings"]["security"] == "reality"
        assert ob["streamSettings"]["realitySettings"]["publicKey"] == "pubkey"

    def test_trojan(self):
        node = Node(
            raw_uri="trojan://...", remark="Trojan", protocol="trojan",
            address="host", port=443, credentials={"password": "pw"},
            transport={"network": "tcp", "security": "tls", "sni": "host",
                        "fingerprint": "chrome", "alpn": "", "host": "", "path": "", "header_type": ""},
        )
        ob = generate_node_outbound(node)
        assert ob["protocol"] == "trojan"
        assert ob["settings"]["servers"][0]["password"] == "pw"

    def test_ss(self):
        node = Node(
            raw_uri="ss://...", remark="SS", protocol="ss",
            address="host", port=8388, credentials={"method": "aes-256-gcm", "password": "pw"},
            transport={"network": "tcp"},
        )
        ob = generate_node_outbound(node)
        assert ob["protocol"] == "shadowsocks"
        srv = ob["settings"]["servers"][0]
        assert srv["method"] == "aes-256-gcm" and srv["password"] == "pw"

    def test_grpc(self):
        node = Node(
            raw_uri="vless://...", remark="gRPC", protocol="vless",
            address="host", port=443, credentials={"uuid": "uuid", "encryption": "none"},
            transport={"network": "grpc", "security": "tls", "sni": "host",
                        "fingerprint": "chrome", "service_name": "mygrpc",
                        "alpn": "", "host": "", "path": "", "header_type": ""},
        )
        ob = generate_node_outbound(node)
        assert ob["streamSettings"]["grpcSettings"]["serviceName"] == "mygrpc"
        assert ob["streamSettings"]["grpcSettings"]["multiMode"] is True

    def test_grpc_multi_mode_false(self):
        node = Node(
            raw_uri="vless://...", remark="gRPC2", protocol="vless",
            address="host", port=443, credentials={"uuid": "uuid", "encryption": "none"},
            transport={"network": "grpc", "security": "tls", "sni": "host",
                        "fingerprint": "chrome", "service_name": "svc",
                        "multi_mode": False, "alpn": "", "host": "", "path": "", "header_type": ""},
        )
        ob = generate_node_outbound(node)
        assert ob["streamSettings"]["grpcSettings"]["multiMode"] is False

    def test_vmess_tcp_http_obfuscation(self):
        node = Node(
            raw_uri="vmess://...", remark="VM-TCP-HTTP", protocol="vmess",
            address="1.2.3.4", port=443,
            credentials={"uuid": "u", "alter_id": 0, "security": "auto"},
            transport={
                "network": "tcp", "security": "", "sni": "", "fingerprint": "",
                "alpn": "", "header_type": "http", "host": "cdn.example.com",
                "path": "/fake/path.js",
            },
        )
        ob = generate_node_outbound(node)
        tcp = ob["streamSettings"]["tcpSettings"]
        assert tcp["header"]["type"] == "http"
        assert tcp["header"]["request"]["path"] == ["/fake/path.js"]
        assert tcp["header"]["request"]["headers"]["Host"] == ["cdn.example.com"]

    def test_tuic(self):
        node = Node(
            raw_uri="tuic://...", remark="TUIC-JP", protocol="tuic",
            address="tuic.example.com", port=443,
            credentials={"uuid": "test-uuid", "password": "test-pw"},
            transport={
                "network": "tuic", "security": "tls",
                "sni": "tuic.example.com", "insecure": False,
                "fingerprint": "chrome", "alpn": "h3",
                "congestion_control": "bbr", "udp_relay_mode": "native",
                "zero_rtt": False,
            },
        )
        ob = generate_node_outbound(node)
        assert ob["tag"] == "TUIC-JP" and ob["protocol"] == "tuic"
        s = ob["settings"]
        assert s["server"] == "tuic.example.com" and s["port"] == 443
        assert s["uuid"] == "test-uuid" and s["password"] == "test-pw"
        assert s["congestionControl"] == "bbr" and s["udpRelayMode"] == "native"
        assert "zeroRttHandshake" not in s
        ss = ob["streamSettings"]
        assert ss["network"] == "tuic" and ss["security"] == "tls"
        assert ss["tlsSettings"]["serverName"] == "tuic.example.com"
        assert ss["tlsSettings"]["alpn"] == ["h3"]

    def test_tuic_zero_rtt(self):
        node = Node(
            raw_uri="tuic://...", remark="TUIC", protocol="tuic",
            address="host", port=443,
            credentials={"uuid": "u", "password": "p"},
            transport={
                "network": "tuic", "security": "tls", "sni": "host",
                "insecure": False, "fingerprint": "chrome", "alpn": "",
                "congestion_control": "cubic", "udp_relay_mode": "quic",
                "zero_rtt": True,
            },
        )
        ob = generate_node_outbound(node)
        assert ob["settings"]["zeroRttHandshake"] is True
        assert ob["settings"]["congestionControl"] == "cubic"
        assert ob["settings"]["udpRelayMode"] == "quic"
        # 未指定 alpn 时，tuic 默认使用 h3
        assert ob["streamSettings"]["tlsSettings"]["alpn"] == ["h3"]

    def test_xhttp(self):
        node = Node(
            raw_uri="vless://...", remark="XHTTP", protocol="vless",
            address="cdn.example.com", port=443,
            credentials={"uuid": "uuid", "encryption": "none"},
            transport={
                "network": "xhttp", "security": "tls", "sni": "cdn.example.com",
                "fingerprint": "chrome", "alpn": "", "host": "cdn.example.com",
                "path": "/xhttp", "header_type": "", "xhttp_mode": "auto",
            },
        )
        ob = generate_node_outbound(node)
        assert ob["streamSettings"]["network"] == "xhttp"
        xs = ob["streamSettings"]["xhttpSettings"]
        assert xs["host"] == "cdn.example.com"
        assert xs["path"] == "/xhttp"
        assert xs["mode"] == "auto"

    def test_xhttp_no_mode(self):
        node = Node(
            raw_uri="vless://...", remark="XHTTP2", protocol="vless",
            address="host", port=443,
            credentials={"uuid": "uuid", "encryption": "none"},
            transport={
                "network": "xhttp", "security": "tls", "sni": "host",
                "fingerprint": "chrome", "alpn": "", "host": "host",
                "path": "/x", "header_type": "",
            },
        )
        ob = generate_node_outbound(node)
        xs = ob["streamSettings"]["xhttpSettings"]
        assert "mode" not in xs

    def test_httpupgrade(self):
        node = Node(
            raw_uri="vless://...", remark="HU", protocol="vless",
            address="cdn.example.com", port=443,
            credentials={"uuid": "uuid", "encryption": "none"},
            transport={
                "network": "httpupgrade", "security": "tls",
                "sni": "cdn.example.com", "fingerprint": "chrome",
                "alpn": "", "host": "cdn.example.com", "path": "/up",
                "header_type": "",
            },
        )
        ob = generate_node_outbound(node)
        assert ob["streamSettings"]["network"] == "httpupgrade"
        hu = ob["streamSettings"]["httpupgradeSettings"]
        assert hu["host"] == "cdn.example.com" and hu["path"] == "/up"

    def test_proxy_settings(self):
        ob = generate_node_outbound(_vless_node(), proxy_tag="landing-proxy")
        assert ob["proxySettings"]["tag"] == "landing-proxy"
        assert ob["proxySettings"]["transportLayer"] is True


class TestLandingProxy:
    def test_chain_outbound_proxy_settings(self):
        lp = LandingProxyConfig(
            protocol="trojan", address="land.com", port=443, password="pw",
            transport=TransportConfig(network="tcp"),
            security=SecurityConfig(mode="tls", server_name="land.com"),
        )
        ob = generate_landing_chain_outbound(lp, "LP-Via: n1", "n1")
        assert ob["tag"] == "LP-Via: n1"
        assert ob["proxySettings"]["tag"] == "n1"
        assert ob["proxySettings"]["transportLayer"] is True

    def test_trojan_tls(self):
        lp = LandingProxyConfig(
            protocol="trojan", address="land.com", port=443, password="pw",
            transport=TransportConfig(network="tcp"),
            security=SecurityConfig(mode="tls", server_name="land.com"),
        )
        ob = generate_landing_proxy_outbound(lp)
        assert ob["tag"] == "landing-proxy" and ob["protocol"] == "trojan"
        assert ob["streamSettings"]["security"] == "tls"

    def test_vless_ws(self):
        lp = LandingProxyConfig(
            protocol="vless", address="host", port=443, uuid="uuid",
            transport=TransportConfig(network="ws", ws=WsTransportConfig(path="/lp", host="ws.host")),
            security=SecurityConfig(mode="tls", server_name="host"),
        )
        ob = generate_landing_proxy_outbound(lp)
        assert ob["streamSettings"]["wsSettings"]["path"] == "/lp"

    def test_vmess_grpc_multi_mode_false(self):
        lp = LandingProxyConfig(
            protocol="vmess", address="grpc.host", port=443, uuid="uuid",
            transport=TransportConfig(
                network="grpc",
                grpc=GrpcTransportConfig(service_name="svc", multi_mode=False),
            ),
            security=SecurityConfig(mode="tls", server_name="grpc.host", alpn=["h2"]),
        )
        ob = generate_landing_proxy_outbound(lp)
        assert ob["streamSettings"]["grpcSettings"]["serviceName"] == "svc"
        assert ob["streamSettings"]["grpcSettings"]["multiMode"] is False

    def test_vless_xhttp(self):
        lp = LandingProxyConfig(
            protocol="vless", address="cdn.host", port=443, uuid="uuid",
            transport=TransportConfig(
                network="xhttp",
                xhttp=XhttpTransportConfig(path="/xhttp", host="cdn.host", mode="auto"),
            ),
            security=SecurityConfig(mode="tls", server_name="cdn.host"),
        )
        ob = generate_landing_proxy_outbound(lp)
        ss = ob["streamSettings"]
        assert ss["network"] == "xhttp"
        assert ss["xhttpSettings"]["path"] == "/xhttp"
        assert ss["xhttpSettings"]["mode"] == "auto"

    def test_vless_httpupgrade(self):
        lp = LandingProxyConfig(
            protocol="vless", address="cdn.host", port=443, uuid="uuid",
            transport=TransportConfig(
                network="httpupgrade",
                httpupgrade=HttpupgradeTransportConfig(path="/up", host="cdn.host"),
            ),
            security=SecurityConfig(mode="tls", server_name="cdn.host"),
        )
        ob = generate_landing_proxy_outbound(lp)
        ss = ob["streamSettings"]
        assert ss["network"] == "httpupgrade"
        assert ss["httpupgradeSettings"]["path"] == "/up"
        assert ss["httpupgradeSettings"]["host"] == "cdn.host"


class TestFixedOutbounds:
    def test_direct_and_blocked(self):
        obs = generate_fixed_outbounds()
        direct = next(o for o in obs if o["tag"] == "direct")
        assert direct["protocol"] == "freedom" and direct["settings"]["domainStrategy"] == "UseIP"
        blocked = next(o for o in obs if o["tag"] == "blocked")
        assert blocked["protocol"] == "blackhole"


class TestBalancerAndObservatory:
    def test_balancer(self):
        b = generate_balancer(["n1", "n2", "n3"])
        assert b["tag"] == "balancer" and b["selector"] == ["n1", "n2", "n3"]
        assert b["strategy"]["type"] == "leastPing"

    def test_balancer_with_fallback(self):
        b = generate_balancer(["n1"], fallback_tag="blocked")
        assert b["fallbackTag"] == "blocked"

    def test_observatory(self):
        obs = generate_observatory(["n1"], ObservatoryConfig(probe_url="https://cp.cloudflare.com", probe_interval="3m"))
        assert obs["probeURL"] == "https://cp.cloudflare.com" and obs["probeInterval"] == "3m"
        assert obs["enableConcurrency"] is True

    def test_observatory_disable_concurrency(self):
        obs = generate_observatory(
            ["n1"],
            ObservatoryConfig(enable_concurrency=False),
        )
        assert obs["enableConcurrency"] is False


class TestGenerateRouting:
    def test_no_user_rules(self):
        r = generate_routing(None, ["n1", "n2"])
        assert r["domainStrategy"] == "IPOnDemand"
        assert len(r["rules"]) == 2
        assert r["rules"][0]["outboundTag"] == "api"
        assert r["rules"][1]["balancerTag"] == "balancer"

    def test_with_user_rules(self):
        cfg = RoutingConfig(domain_strategy="IPIfNonMatch", domain_matcher="linear", rules=[
            RoutingRule(outbound_tag="direct", domain=["geosite:cn"]),
            RoutingRule(outbound_tag="blocked", domain=["geosite:category-ads"]),
        ])
        r = generate_routing(cfg, ["n1"])
        assert len(r["rules"]) == 4 and r["rules"][1]["domain"] == ["geosite:cn"]
        assert r["domainStrategy"] == "IPIfNonMatch"

    def test_rule_with_ip_and_network(self):
        cfg = RoutingConfig(rules=[RoutingRule(outbound_tag="direct", ip=["geoip:cn"], network="tcp,udp")])
        rule = generate_routing(cfg, [])["rules"][1]
        assert rule["ip"] == ["geoip:cn"] and rule["network"] == "tcp,udp"

    def test_rule_with_inbound_tag(self):
        cfg = RoutingConfig(rules=[RoutingRule(outbound_tag="direct", inbound_tag=["in-socks"])])
        assert generate_routing(cfg, [])["rules"][1]["inboundTag"] == ["in-socks"]

    def test_balancers(self):
        assert generate_routing(None, ["a", "b"])["balancers"][0]["selector"] == ["a", "b"]

    def test_balancer_fallback(self):
        balancer = generate_routing(None, ["a"], fallback_tag="blocked")["balancers"][0]
        assert balancer["fallbackTag"] == "blocked"


class TestGenerateDns:
    def test_none(self):
        assert generate_dns(None) is None

    def test_with_hosts_and_servers(self):
        cfg = DnsConfig(
            hosts={"mysite": "1.2.3.4"},
            servers=[DnsServer(address="119.29.29.29", port=53, domains=["geosite:cn"], expect_ips=["geoip:cn"]),
                     DnsServer(address="8.8.8.8")],
        )
        dns = generate_dns(cfg)
        assert dns["hosts"] == {"mysite": "1.2.3.4"}
        assert dns["servers"][0]["address"] == "119.29.29.29" and dns["servers"][0]["expectIPs"] == ["geoip:cn"]

    def test_empty_hosts(self):
        dns = generate_dns(DnsConfig(servers=[DnsServer(address="1.1.1.1")]))
        assert dns.get("hosts", {}) == {}


class TestGenerateApi:
    def test_services(self):
        api = generate_api()
        assert api["tag"] == "api" and "ObservatoryService" in api["services"]


class TestStatsPolicy:
    def test_stats_and_policy(self):
        stats, policy = generate_stats_policy()
        assert stats == {} and policy["system"]["statsOutboundUplink"] is True


class TestGenerateXrayConfig:
    def test_minimal(self):
        cfg = KrayminiConfig(subscriptions=[SubscriptionConfig(url="https://example.com/sub")])
        xray = generate_xray_config(cfg, [_vless_node("n1"), _vless_node("n2", "host2")])
        assert len(xray["inbounds"]) == 3
        tags = [o["tag"] for o in xray["outbounds"]]
        assert "n1" in tags and "n2" in tags and "direct" in tags and "blocked" in tags
        assert "landing-proxy" not in tags
        assert "dns" not in xray

    def test_valid_json(self):
        cfg = KrayminiConfig(subscriptions=[SubscriptionConfig(url="https://example.com/sub")])
        xray = generate_xray_config(cfg, [_vless_node()])
        assert json.loads(json.dumps(xray)) == xray

    def test_with_landing_proxy(self):
        cfg = KrayminiConfig(
            subscriptions=[SubscriptionConfig(url="https://example.com/sub")],
            landing_proxy=LandingProxyConfig(
                protocol="trojan", address="land.host", port=443, password="pw",
                transport=TransportConfig(network="tcp"),
                security=SecurityConfig(mode="tls", server_name="land.host"),
            ),
        )
        xray = generate_xray_config(cfg, [_vless_node()])
        tags = [o["tag"] for o in xray["outbounds"]]
        assert "LP-Via: node-1" in tags
        assert "landing-proxy" not in tags
        assert tags[0] == "LP-Via: node-1"
        assert tags[1] == "node-1"
        node_ob = next(o for o in xray["outbounds"] if o["tag"] == "node-1")
        assert "proxySettings" not in node_ob
        chain_ob = next(o for o in xray["outbounds"] if o["tag"] == "LP-Via: node-1")
        assert chain_ob["proxySettings"]["tag"] == "node-1"
        assert xray["routing"]["balancers"][0]["selector"] == ["LP-Via: node-1"]
        assert xray["routing"]["balancers"][0]["fallbackTag"] == "blocked"
        assert xray["observatory"]["subjectSelector"] == ["LP-Via: node-1"]
        assert xray["observatory"]["enableConcurrency"] is True

    def test_log_section(self):
        cfg = KrayminiConfig(
            subscriptions=[SubscriptionConfig(url="https://example.com/sub")],
            log=LogConfig(xray_level="error"),
        )
        assert generate_xray_config(cfg, [_vless_node()])["log"]["loglevel"] == "error"

    def test_write_xray_config(self, tmp_path):
        xray = {"test": True}
        out = tmp_path / "out" / "xray.json"
        written = write_xray_config(xray, str(out))
        assert Path(written).exists()
        assert json.loads(Path(written).read_text()) == xray
