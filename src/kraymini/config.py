from __future__ import annotations

import ipaddress
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(Exception):
    pass


@dataclass
class GeneralConfig:
    xray_bin: str = "xray"
    output_config: str = "~/.kraymini/xray.json"
    refresh_interval: int = 10800
    node_include: list[str] = field(default_factory=list)
    node_exclude: list[str] = field(default_factory=list)


@dataclass
class SubscriptionConfig:
    url: str
    name: str = ""


@dataclass
class InboundConfig:
    listen: str = "127.0.0.1"
    socks_port: int = 10808
    http_port: int = 10809
    api_port: int = 10810
    sniffing: bool = True


@dataclass
class WsTransportConfig:
    path: str = "/"
    host: str = ""


@dataclass
class GrpcTransportConfig:
    service_name: str = ""
    multi_mode: bool = True


@dataclass
class H2TransportConfig:
    path: str = "/"
    host: list[str] = field(default_factory=list)


@dataclass
class TransportConfig:
    network: str = "tcp"
    ws: WsTransportConfig | None = None
    grpc: GrpcTransportConfig | None = None
    h2: H2TransportConfig | None = None


@dataclass
class RealityConfig:
    public_key: str = ""
    short_id: str = ""
    spider_x: str = "/"


@dataclass
class SecurityConfig:
    mode: str = "none"
    server_name: str = ""
    allow_insecure: bool = False
    fingerprint: str = "chrome"
    alpn: list[str] = field(default_factory=list)
    reality: RealityConfig | None = None


@dataclass
class LandingProxyConfig:
    protocol: str
    address: str
    port: int
    uuid: str = ""
    password: str = ""
    method: str = ""
    transport: TransportConfig = field(default_factory=TransportConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)


@dataclass
class RoutingRule:
    outbound_tag: str
    domain: list[str] = field(default_factory=list)
    ip: list[str] = field(default_factory=list)
    network: str = ""
    inbound_tag: list[str] = field(default_factory=list)


@dataclass
class RoutingConfig:
    domain_strategy: str = "IPOnDemand"
    domain_matcher: str = "mph"
    rules: list[RoutingRule] = field(default_factory=list)


@dataclass
class DnsServer:
    address: str
    port: int = 53
    domains: list[str] = field(default_factory=list)
    expect_ips: list[str] = field(default_factory=list)


@dataclass
class DnsConfig:
    hosts: dict[str, str] = field(default_factory=dict)
    servers: list[DnsServer] = field(default_factory=list)


@dataclass
class ObservatoryConfig:
    probe_url: str = "https://www.google.com/generate_204"
    probe_interval: str = "5m"


@dataclass
class LogConfig:
    level: str = "info"
    xray_level: str = "warning"
    file: str = ""


@dataclass
class KrayminiConfig:
    subscriptions: list[SubscriptionConfig]
    general: GeneralConfig = field(default_factory=GeneralConfig)
    inbound: InboundConfig = field(default_factory=InboundConfig)
    landing_proxy: LandingProxyConfig | None = None
    routing: RoutingConfig | None = None
    dns: DnsConfig | None = None
    observatory: ObservatoryConfig = field(default_factory=ObservatoryConfig)
    log: LogConfig = field(default_factory=LogConfig)


VALID_LOG_LEVELS = {"debug", "info", "warning", "error"}
VALID_XRAY_LEVELS = {"debug", "info", "warning", "error", "none"}
VALID_NETWORKS = {"tcp", "ws", "grpc", "h2"}
VALID_DOMAIN_STRATEGIES = {"AsIs", "IPIfNonMatch", "IPOnDemand"}
VALID_DOMAIN_MATCHERS = {"linear", "mph"}
VALID_OUTBOUND_TAGS = {"direct", "blocked"}

SEARCH_PATHS = [
    Path("./config.toml"),
    Path("~/.kraymini/config.toml"),
    Path("/usr/local/etc/kraymini/config.toml"),
    Path("/etc/kraymini/config.toml"),
]


def _expand_path(p: str) -> str:
    return str(Path(p).expanduser())


def _load_transport(data: dict) -> TransportConfig:
    network = data.get("network", "tcp")
    ws = None
    grpc = None
    h2 = None
    if "ws" in data:
        ws = WsTransportConfig(
            path=data["ws"].get("path", "/"),
            host=data["ws"].get("host", ""),
        )
    if "grpc" in data:
        grpc = GrpcTransportConfig(
            service_name=data["grpc"].get("service_name", ""),
            multi_mode=data["grpc"].get("multi_mode", True),
        )
    if "h2" in data:
        h2 = H2TransportConfig(
            path=data["h2"].get("path", "/"),
            host=data["h2"].get("host", []),
        )
    return TransportConfig(network=network, ws=ws, grpc=grpc, h2=h2)


def _load_security(data: dict) -> SecurityConfig:
    reality = None
    if "reality" in data:
        r = data["reality"]
        reality = RealityConfig(
            public_key=r.get("public_key", ""),
            short_id=r.get("short_id", ""),
            spider_x=r.get("spider_x", "/"),
        )
    return SecurityConfig(
        mode=data.get("mode", "none"),
        server_name=data.get("server_name", ""),
        allow_insecure=data.get("allow_insecure", False),
        fingerprint=data.get("fingerprint", "chrome"),
        alpn=data.get("alpn", []),
        reality=reality,
    )


def _load_landing_proxy(data: dict) -> LandingProxyConfig:
    transport = _load_transport(data.get("transport", {}))
    security = _load_security(data.get("security", {}))
    return LandingProxyConfig(
        protocol=data["protocol"],
        address=data["address"],
        port=data["port"],
        uuid=data.get("uuid", ""),
        password=data.get("password", ""),
        method=data.get("method", ""),
        transport=transport,
        security=security,
    )


def _load_routing(data: dict) -> RoutingConfig:
    rules = []
    for r in data.get("rules", []):
        rules.append(RoutingRule(
            outbound_tag=r["outbound_tag"],
            domain=r.get("domain", []),
            ip=r.get("ip", []),
            network=r.get("network", ""),
            inbound_tag=r.get("inbound_tag", []),
        ))
    return RoutingConfig(
        domain_strategy=data.get("domain_strategy", "IPOnDemand"),
        domain_matcher=data.get("domain_matcher", "mph"),
        rules=rules,
    )


def _load_dns(data: dict) -> DnsConfig:
    servers = []
    for s in data.get("servers", []):
        servers.append(DnsServer(
            address=s.get("address", ""),
            port=s.get("port", 53),
            domains=s.get("domains", []),
            expect_ips=s.get("expect_ips", []),
        ))
    return DnsConfig(
        hosts=data.get("hosts", {}),
        servers=servers,
    )


def _validate_config(cfg: KrayminiConfig) -> None:
    if not cfg.subscriptions:
        raise ConfigError("至少配置一个订阅源")
    for sub in cfg.subscriptions:
        if not sub.url.strip():
            raise ConfigError("订阅源 url 不能为空")

    ports = [cfg.inbound.socks_port, cfg.inbound.http_port, cfg.inbound.api_port]
    for p in ports:
        if not (1 <= p <= 65535):
            raise ConfigError(f"端口 {p} 超出有效范围 (1-65535)")
    if len(set(ports)) != len(ports):
        raise ConfigError("端口配置存在冲突，三个端口必须互不相同")

    try:
        ipaddress.ip_address(cfg.inbound.listen)
    except ValueError:
        raise ConfigError(f"listen 地址不合法: {cfg.inbound.listen!r}")

    if cfg.general.refresh_interval <= 0:
        raise ConfigError("refresh_interval 必须为正整数")

    if cfg.log.level not in VALID_LOG_LEVELS:
        raise ConfigError(f"level 必须为 {VALID_LOG_LEVELS} 之一，实际: {cfg.log.level!r}")
    if cfg.log.xray_level not in VALID_XRAY_LEVELS:
        raise ConfigError(f"xray_level 必须为 {VALID_XRAY_LEVELS} 之一，实际: {cfg.log.xray_level!r}")

    lp = cfg.landing_proxy
    if lp is not None:
        if lp.protocol in ("vmess", "vless") and not lp.uuid:
            raise ConfigError(f"{lp.protocol} 协议需要 uuid")
        if lp.protocol == "trojan" and not lp.password:
            raise ConfigError("trojan 协议需要 password")
        if lp.protocol == "shadowsocks":
            if not lp.password:
                raise ConfigError("shadowsocks 协议需要 password")
            if not lp.method:
                raise ConfigError("shadowsocks 协议需要 method")
        if lp.transport.network not in VALID_NETWORKS:
            raise ConfigError(f"network 必须为 {VALID_NETWORKS} 之一，实际: {lp.transport.network!r}")
        if lp.security.mode == "reality":
            if not lp.security.server_name:
                raise ConfigError("reality 模式需要 server_name")
            if lp.security.reality is None or not lp.security.reality.public_key:
                raise ConfigError("reality 模式需要 public_key")

    allowed_tags = set(VALID_OUTBOUND_TAGS)
    if lp is not None:
        allowed_tags.add("landing-proxy")

    if cfg.routing is not None:
        if cfg.routing.domain_strategy not in VALID_DOMAIN_STRATEGIES:
            raise ConfigError(
                f"domain_strategy 必须为 {VALID_DOMAIN_STRATEGIES} 之一，"
                f"实际: {cfg.routing.domain_strategy!r}"
            )
        if cfg.routing.domain_matcher not in VALID_DOMAIN_MATCHERS:
            raise ConfigError(
                f"domain_matcher 必须为 {VALID_DOMAIN_MATCHERS} 之一，"
                f"实际: {cfg.routing.domain_matcher!r}"
            )
        for rule in cfg.routing.rules:
            if rule.outbound_tag not in allowed_tags:
                raise ConfigError(
                    f"outbound_tag {rule.outbound_tag!r} 无效，"
                    f"可用值: {allowed_tags}"
                )
            if not (rule.domain or rule.ip or rule.network or rule.inbound_tag):
                raise ConfigError(
                    "路由规则至少指定 domain/ip/network/inbound_tag 之一作为条件"
                )

    if cfg.dns is not None:
        for srv in cfg.dns.servers:
            if not srv.address:
                raise ConfigError("DNS 服务器必须指定 address")


def find_config(explicit_path: str | None) -> Path:
    if explicit_path is not None:
        p = Path(explicit_path)
        if not p.exists():
            raise ConfigError(f"配置文件不存在: {p}")
        return p

    for sp in SEARCH_PATHS:
        resolved = sp.expanduser()
        if resolved.exists():
            return resolved

    raise ConfigError(
        "未找到配置文件，搜索路径: "
        + ", ".join(str(p) for p in SEARCH_PATHS)
    )


def load_config(path: str | Path) -> KrayminiConfig:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"配置文件不存在: {path}")

    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"配置文件格式错误: {e}") from e

    general_raw = raw.get("general", {})
    general = GeneralConfig(
        xray_bin=general_raw.get("xray_bin", "xray"),
        output_config=_expand_path(general_raw.get("output_config", "~/.kraymini/xray.json")),
        refresh_interval=general_raw.get("refresh_interval", 10800),
        node_include=general_raw.get("node_include", []),
        node_exclude=general_raw.get("node_exclude", []),
    )

    subs_raw = raw.get("subscriptions", [])
    subscriptions = [
        SubscriptionConfig(url=s["url"], name=s.get("name", ""))
        for s in subs_raw
    ]

    inbound_raw = raw.get("inbound", {})
    inbound = InboundConfig(
        listen=inbound_raw.get("listen", "127.0.0.1"),
        socks_port=inbound_raw.get("socks_port", 10808),
        http_port=inbound_raw.get("http_port", 10809),
        api_port=inbound_raw.get("api_port", 10810),
        sniffing=inbound_raw.get("sniffing", True),
    )

    landing_proxy = None
    if "landing_proxy" in raw:
        landing_proxy = _load_landing_proxy(raw["landing_proxy"])

    routing = None
    if "routing" in raw:
        routing = _load_routing(raw["routing"])

    dns = None
    if "dns" in raw:
        dns = _load_dns(raw["dns"])

    obs_raw = raw.get("observatory", {})
    observatory = ObservatoryConfig(
        probe_url=obs_raw.get("probe_url", "https://www.google.com/generate_204"),
        probe_interval=obs_raw.get("probe_interval", "5m"),
    )

    log_raw = raw.get("log", {})
    log_file = log_raw.get("file", "")
    if log_file:
        log_file = _expand_path(log_file)
    log = LogConfig(
        level=log_raw.get("level", "info"),
        xray_level=log_raw.get("xray_level", "warning"),
        file=log_file,
    )

    cfg = KrayminiConfig(
        general=general,
        subscriptions=subscriptions,
        inbound=inbound,
        landing_proxy=landing_proxy,
        routing=routing,
        dns=dns,
        observatory=observatory,
        log=log,
    )

    _validate_config(cfg)
    return cfg
