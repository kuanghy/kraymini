import pytest
from kraymini.config import (
    GeneralConfig,
    SubscriptionConfig,
    InboundConfig,
    LandingProxyConfig,
    TransportConfig,
    SecurityConfig,
    RoutingConfig,
    RoutingRule,
    DnsConfig,
    DnsServer,
    ObservatoryConfig,
    LogConfig,
    KrayminiConfig,
    load_config,
    ConfigError,
)


class TestConfigDataStructures:
    def test_general_config_defaults(self):
        cfg = GeneralConfig()
        assert cfg.xray_bin == "xray"
        assert cfg.output_config == "~/.kraymini/xray.json"
        assert cfg.refresh_interval == 10800
        assert cfg.node_include == []
        assert cfg.node_exclude == []

    def test_subscription_config(self):
        sub = SubscriptionConfig(url="https://example.com/sub")
        assert sub.url == "https://example.com/sub"
        assert sub.name == ""

    def test_inbound_config_defaults(self):
        cfg = InboundConfig()
        assert cfg.listen == "127.0.0.1"
        assert cfg.socks_port == 10808
        assert cfg.http_port == 10809
        assert cfg.api_port == 10810
        assert cfg.sniffing is True

    def test_landing_proxy_config(self):
        lp = LandingProxyConfig(
            protocol="trojan",
            address="landing.example.com",
            port=443,
            password="pw",
        )
        assert lp.protocol == "trojan"
        assert lp.transport.network == "tcp"
        assert lp.security.mode == "none"

    def test_routing_rule(self):
        rule = RoutingRule(
            outbound_tag="direct",
            domain=["geosite:cn"],
        )
        assert rule.outbound_tag == "direct"
        assert rule.domain == ["geosite:cn"]

    def test_kraymini_config_minimal(self):
        cfg = KrayminiConfig(
            subscriptions=[SubscriptionConfig(url="https://example.com/sub")],
        )
        assert cfg.general.xray_bin == "xray"
        assert len(cfg.subscriptions) == 1
        assert cfg.landing_proxy is None
        assert cfg.routing is None
        assert cfg.dns is None


class TestLoadConfig:
    def test_load_minimal_config(self, write_config):
        path = write_config('[[subscriptions]]\nurl = "https://example.com/sub"\n')
        cfg = load_config(path)
        assert len(cfg.subscriptions) == 1
        assert cfg.subscriptions[0].url == "https://example.com/sub"
        assert cfg.general.xray_bin == "xray"
        assert cfg.inbound.socks_port == 10808

    def test_load_full_general(self, write_config):
        toml = """
[general]
xray_bin = "/usr/local/bin/xray"
output_config = "/tmp/xray.json"
refresh_interval = 3600
node_include = ["香港", "美国"]
node_exclude = ["剩余流量"]

[[subscriptions]]
url = "https://example.com/sub"
name = "provider-a"
"""
        path = write_config(toml)
        cfg = load_config(path)
        assert cfg.general.xray_bin == "/usr/local/bin/xray"
        assert cfg.general.refresh_interval == 3600
        assert cfg.general.node_include == ["香港", "美国"]
        assert cfg.subscriptions[0].name == "provider-a"

    def test_load_inbound(self, write_config):
        toml = """
[[subscriptions]]
url = "https://example.com/sub"

[inbound]
listen = "0.0.0.0"
socks_port = 1080
http_port = 1081
api_port = 1082
sniffing = false
"""
        path = write_config(toml)
        cfg = load_config(path)
        assert cfg.inbound.listen == "0.0.0.0"
        assert cfg.inbound.socks_port == 1080
        assert cfg.inbound.sniffing is False

    def test_load_landing_proxy_trojan(self, write_config):
        toml = """
[[subscriptions]]
url = "https://example.com/sub"

[landing_proxy]
protocol = "trojan"
address = "landing.example.com"
port = 443
password = "my-password"

[landing_proxy.transport]
network = "ws"

[landing_proxy.transport.ws]
path = "/ws"
host = "landing.example.com"

[landing_proxy.security]
mode = "tls"
server_name = "landing.example.com"
fingerprint = "chrome"
"""
        path = write_config(toml)
        cfg = load_config(path)
        assert cfg.landing_proxy is not None
        assert cfg.landing_proxy.protocol == "trojan"
        assert cfg.landing_proxy.password == "my-password"
        assert cfg.landing_proxy.transport.network == "ws"
        assert cfg.landing_proxy.transport.ws.path == "/ws"
        assert cfg.landing_proxy.security.mode == "tls"
        assert cfg.landing_proxy.security.server_name == "landing.example.com"

    def test_load_landing_proxy_reality(self, write_config):
        toml = """
[[subscriptions]]
url = "https://example.com/sub"

[landing_proxy]
protocol = "vless"
address = "reality.example.com"
port = 443
uuid = "test-uuid"

[landing_proxy.security]
mode = "reality"
server_name = "www.microsoft.com"
fingerprint = "chrome"

[landing_proxy.security.reality]
public_key = "abc123"
short_id = "def456"
"""
        path = write_config(toml)
        cfg = load_config(path)
        assert cfg.landing_proxy.security.mode == "reality"
        assert cfg.landing_proxy.security.reality is not None
        assert cfg.landing_proxy.security.reality.public_key == "abc123"

    def test_load_routing_rules(self, write_config):
        toml = """
[[subscriptions]]
url = "https://example.com/sub"

[routing]
domain_strategy = "IPIfNonMatch"

[[routing.rules]]
domain = ["geosite:cn"]
outbound_tag = "direct"

[[routing.rules]]
ip = ["geoip:cn", "geoip:private"]
outbound_tag = "direct"

[[routing.rules]]
domain = ["geosite:category-ads"]
outbound_tag = "blocked"
"""
        path = write_config(toml)
        cfg = load_config(path)
        assert cfg.routing is not None
        assert cfg.routing.domain_strategy == "IPIfNonMatch"
        assert len(cfg.routing.rules) == 3
        assert cfg.routing.rules[0].domain == ["geosite:cn"]
        assert cfg.routing.rules[2].outbound_tag == "blocked"

    def test_load_dns(self, write_config):
        toml = """
[[subscriptions]]
url = "https://example.com/sub"

[dns]
[dns.hosts]
"mysite" = "1.2.3.4"

[[dns.servers]]
address = "119.29.29.29"
port = 53
domains = ["geosite:cn"]
expect_ips = ["geoip:cn"]

[[dns.servers]]
address = "8.8.8.8"
"""
        path = write_config(toml)
        cfg = load_config(path)
        assert cfg.dns is not None
        assert cfg.dns.hosts == {"mysite": "1.2.3.4"}
        assert len(cfg.dns.servers) == 2
        assert cfg.dns.servers[0].address == "119.29.29.29"
        assert cfg.dns.servers[0].domains == ["geosite:cn"]
        assert cfg.dns.servers[1].port == 53

    def test_load_observatory(self, write_config):
        toml = """
[[subscriptions]]
url = "https://example.com/sub"

[observatory]
probe_url = "https://cp.cloudflare.com"
probe_interval = "3m"
"""
        path = write_config(toml)
        cfg = load_config(path)
        assert cfg.observatory.probe_url == "https://cp.cloudflare.com"
        assert cfg.observatory.probe_interval == "3m"

    def test_load_log(self, write_config):
        toml = """
[[subscriptions]]
url = "https://example.com/sub"

[log]
level = "debug"
xray_level = "info"
file = "/tmp/kraymini.log"
"""
        path = write_config(toml)
        cfg = load_config(path)
        assert cfg.log.level == "debug"
        assert cfg.log.xray_level == "info"
        assert cfg.log.file == "/tmp/kraymini.log"

    def test_path_expansion(self, write_config):
        toml = """
[general]
output_config = "~/.kraymini/xray.json"

[[subscriptions]]
url = "https://example.com/sub"
"""
        path = write_config(toml)
        cfg = load_config(path)
        assert "~" not in cfg.general.output_config
        assert cfg.general.output_config.startswith("/")

    def test_invalid_toml(self, write_config):
        path = write_config("this is not valid toml [[[")
        with pytest.raises(ConfigError, match="配置文件格式错误"):
            load_config(path)

    def test_file_not_found(self, tmp_path):
        path = tmp_path / "nonexistent.toml"
        with pytest.raises(ConfigError, match="配置文件不存在"):
            load_config(path)


class TestValidateConfig:
    def test_no_subscriptions(self, write_config):
        path = write_config("[general]\n")
        with pytest.raises(ConfigError, match="至少配置一个订阅源"):
            load_config(path)

    def test_empty_subscription_url(self, write_config):
        path = write_config('[[subscriptions]]\nurl = ""\n')
        with pytest.raises(ConfigError, match="url.*不能为空"):
            load_config(path)

    def test_invalid_port_range(self, write_config):
        toml = '[[subscriptions]]\nurl = "https://example.com/sub"\n\n[inbound]\nsocks_port = 70000\n'
        path = write_config(toml)
        with pytest.raises(ConfigError, match="端口.*范围"):
            load_config(path)

    def test_port_conflict(self, write_config):
        toml = '[[subscriptions]]\nurl = "https://example.com/sub"\n\n[inbound]\nsocks_port = 10808\nhttp_port = 10808\n'
        path = write_config(toml)
        with pytest.raises(ConfigError, match="端口.*冲突"):
            load_config(path)

    def test_invalid_listen_address(self, write_config):
        toml = '[[subscriptions]]\nurl = "https://example.com/sub"\n\n[inbound]\nlisten = "not_an_ip"\n'
        path = write_config(toml)
        with pytest.raises(ConfigError, match="listen.*合法"):
            load_config(path)

    def test_valid_listen_ipv6(self, write_config):
        toml = '[[subscriptions]]\nurl = "https://example.com/sub"\n\n[inbound]\nlisten = "::1"\n'
        path = write_config(toml)
        cfg = load_config(path)
        assert cfg.inbound.listen == "::1"

    def test_landing_proxy_vmess_needs_uuid(self, write_config):
        toml = '[[subscriptions]]\nurl = "https://example.com/sub"\n\n[landing_proxy]\nprotocol = "vmess"\naddress = "host"\nport = 443\n'
        path = write_config(toml)
        with pytest.raises(ConfigError, match="uuid"):
            load_config(path)

    def test_landing_proxy_trojan_needs_password(self, write_config):
        toml = '[[subscriptions]]\nurl = "https://example.com/sub"\n\n[landing_proxy]\nprotocol = "trojan"\naddress = "host"\nport = 443\n'
        path = write_config(toml)
        with pytest.raises(ConfigError, match="password"):
            load_config(path)

    def test_landing_proxy_ss_needs_password_and_method(self, write_config):
        toml = '[[subscriptions]]\nurl = "https://example.com/sub"\n\n[landing_proxy]\nprotocol = "shadowsocks"\naddress = "host"\nport = 443\npassword = "pw"\n'
        path = write_config(toml)
        with pytest.raises(ConfigError, match="method"):
            load_config(path)

    def test_landing_proxy_invalid_network(self, write_config):
        toml = '[[subscriptions]]\nurl = "https://example.com/sub"\n\n[landing_proxy]\nprotocol = "trojan"\naddress = "host"\nport = 443\npassword = "pw"\n\n[landing_proxy.transport]\nnetwork = "quic"\n'
        path = write_config(toml)
        with pytest.raises(ConfigError, match="network"):
            load_config(path)

    def test_reality_requires_server_name_and_public_key(self, write_config):
        toml = '[[subscriptions]]\nurl = "https://example.com/sub"\n\n[landing_proxy]\nprotocol = "vless"\naddress = "host"\nport = 443\nuuid = "test-uuid"\n\n[landing_proxy.security]\nmode = "reality"\n'
        path = write_config(toml)
        with pytest.raises(ConfigError, match="server_name|public_key"):
            load_config(path)

    def test_routing_rule_invalid_outbound_tag(self, write_config):
        toml = '[[subscriptions]]\nurl = "https://example.com/sub"\n\n[[routing.rules]]\ndomain = ["example.com"]\noutbound_tag = "invalid-tag"\n'
        path = write_config(toml)
        with pytest.raises(ConfigError, match="outbound_tag"):
            load_config(path)

    def test_routing_rule_landing_proxy_tag_requires_config(self, write_config):
        toml = '[[subscriptions]]\nurl = "https://example.com/sub"\n\n[[routing.rules]]\ndomain = ["example.com"]\noutbound_tag = "landing-proxy"\n'
        path = write_config(toml)
        with pytest.raises(ConfigError, match="outbound_tag"):
            load_config(path)

    def test_routing_rule_landing_proxy_invalid_when_landing_configured(self, write_config):
        toml = """
[[subscriptions]]
url = "https://example.com/sub"

[landing_proxy]
protocol = "trojan"
address = "h.com"
port = 443
password = "pw"

[[routing.rules]]
domain = ["example.com"]
outbound_tag = "landing-proxy"
"""
        path = write_config(toml)
        with pytest.raises(ConfigError, match="outbound_tag"):
            load_config(path)

    def test_routing_rule_lp_via_allowed_with_landing(self, write_config):
        toml = """
[[subscriptions]]
url = "https://example.com/sub"

[landing_proxy]
protocol = "trojan"
address = "h.com"
port = 443
password = "pw"

[[routing.rules]]
domain = ["example.com"]
outbound_tag = "LP-Via: my-node"
"""
        path = write_config(toml)
        cfg = load_config(path)
        assert cfg.routing is not None
        assert cfg.routing.rules[0].outbound_tag == "LP-Via: my-node"

    def test_routing_rule_must_have_condition(self, write_config):
        toml = '[[subscriptions]]\nurl = "https://example.com/sub"\n\n[[routing.rules]]\noutbound_tag = "direct"\n'
        path = write_config(toml)
        with pytest.raises(ConfigError, match="至少指定.*条件"):
            load_config(path)

    def test_dns_server_requires_address(self, write_config):
        toml = '[[subscriptions]]\nurl = "https://example.com/sub"\n\n[[dns.servers]]\nport = 53\n'
        path = write_config(toml)
        with pytest.raises(ConfigError, match="address"):
            load_config(path)

    def test_invalid_refresh_interval(self, write_config):
        toml = '[general]\nrefresh_interval = -1\n\n[[subscriptions]]\nurl = "https://example.com/sub"\n'
        path = write_config(toml)
        with pytest.raises(ConfigError, match="refresh_interval.*正整数"):
            load_config(path)

    def test_invalid_log_level(self, write_config):
        toml = '[[subscriptions]]\nurl = "https://example.com/sub"\n\n[log]\nlevel = "verbose"\n'
        path = write_config(toml)
        with pytest.raises(ConfigError, match="level"):
            load_config(path)

    def test_invalid_xray_level(self, write_config):
        toml = '[[subscriptions]]\nurl = "https://example.com/sub"\n\n[log]\nxray_level = "trace"\n'
        path = write_config(toml)
        with pytest.raises(ConfigError, match="xray_level"):
            load_config(path)

    def test_invalid_domain_strategy(self, write_config):
        toml = '[[subscriptions]]\nurl = "https://example.com/sub"\n\n[routing]\ndomain_strategy = "Invalid"\n'
        path = write_config(toml)
        with pytest.raises(ConfigError, match="domain_strategy"):
            load_config(path)

    def test_invalid_domain_matcher(self, write_config):
        toml = '[[subscriptions]]\nurl = "https://example.com/sub"\n\n[routing]\ndomain_matcher = "unknown"\n'
        path = write_config(toml)
        with pytest.raises(ConfigError, match="domain_matcher"):
            load_config(path)
