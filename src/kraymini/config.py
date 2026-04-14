from __future__ import annotations

import ipaddress
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

from .constants import LANDING_CHAIN_PREFIX


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
class XhttpTransportConfig:
    path: str = "/"
    host: str = ""
    mode: str = ""


@dataclass
class HttpupgradeTransportConfig:
    path: str = "/"
    host: str = ""


@dataclass
class TransportConfig:
    network: str = "tcp"
    ws: WsTransportConfig | None = None
    grpc: GrpcTransportConfig | None = None
    h2: H2TransportConfig | None = None
    xhttp: XhttpTransportConfig | None = None
    httpupgrade: HttpupgradeTransportConfig | None = None


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
    enable_concurrency: bool = True


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
VALID_NETWORKS = {"tcp", "ws", "grpc", "h2", "xhttp", "httpupgrade"}
VALID_DOMAIN_STRATEGIES = {"AsIs", "IPIfNonMatch", "IPOnDemand"}
VALID_DOMAIN_MATCHERS = {"linear", "mph"}
VALID_OUTBOUND_TAGS = {"direct", "blocked"}

SEARCH_PATHS = [
    Path("./config.toml"),
    Path("~/.kraymini/config.toml"),
    Path("/usr/local/etc/kraymini/config.toml"),
    Path("/etc/kraymini/config.toml"),
]
TOP_LEVEL_KEYS = {
    "general",
    "subscriptions",
    "inbound",
    "landing_proxy",
    "routing",
    "dns",
    "observatory",
    "log",
}


def _expand_path(p: str) -> str:
    return str(Path(p).expanduser())


def _known_keys(cls: type) -> set[str]:
    return {f.name for f in fields(cls)}


def _reject_unknown_keys(cls: type, data: dict, context: str) -> None:
    unknown = sorted(set(data) - _known_keys(cls))
    if unknown:
        raise ConfigError(f"未知配置项: {context}.{unknown[0]}")


def _reject_unknown_top_level(raw: dict) -> None:
    unknown = sorted(set(raw) - TOP_LEVEL_KEYS)
    if unknown:
        raise ConfigError(f"未知配置项: {unknown[0]}")


def _from_toml(cls: type, data: dict):
    """从 TOML dict 构建 dataclass，缺失键使用 dataclass 默认值"""
    return cls(**{k: v for k, v in data.items() if k in _known_keys(cls)})


def _load_transport(data: dict) -> TransportConfig:
    _reject_unknown_keys(TransportConfig, data, "landing_proxy.transport")
    if "ws" in data:
        _reject_unknown_keys(
            WsTransportConfig, data["ws"], "landing_proxy.transport.ws"
        )
    if "grpc" in data:
        _reject_unknown_keys(
            GrpcTransportConfig, data["grpc"], "landing_proxy.transport.grpc"
        )
    if "h2" in data:
        _reject_unknown_keys(
            H2TransportConfig, data["h2"], "landing_proxy.transport.h2"
        )
    if "xhttp" in data:
        _reject_unknown_keys(
            XhttpTransportConfig, data["xhttp"], "landing_proxy.transport.xhttp"
        )
    if "httpupgrade" in data:
        _reject_unknown_keys(
            HttpupgradeTransportConfig,
            data["httpupgrade"],
            "landing_proxy.transport.httpupgrade",
        )
    ws = _from_toml(WsTransportConfig, data["ws"]) if "ws" in data else None
    grpc = _from_toml(GrpcTransportConfig, data["grpc"]) if "grpc" in data else None
    h2 = _from_toml(H2TransportConfig, data["h2"]) if "h2" in data else None
    xhttp = _from_toml(XhttpTransportConfig, data["xhttp"]) if "xhttp" in data else None
    httpupgrade = (
        _from_toml(HttpupgradeTransportConfig, data["httpupgrade"])
        if "httpupgrade" in data
        else None
    )
    kwargs: dict = {"ws": ws, "grpc": grpc, "h2": h2, "xhttp": xhttp, "httpupgrade": httpupgrade}
    if "network" in data:
        kwargs["network"] = data["network"]
    return TransportConfig(**kwargs)


def _load_security(data: dict) -> SecurityConfig:
    _reject_unknown_keys(SecurityConfig, data, "landing_proxy.security")
    if "reality" in data:
        _reject_unknown_keys(
            RealityConfig, data["reality"], "landing_proxy.security.reality"
        )
    reality = _from_toml(RealityConfig, data["reality"]) if "reality" in data else None
    flat = {k: v for k, v in data.items() if k != "reality"}
    sc = _from_toml(SecurityConfig, flat)
    sc.reality = reality
    return sc


def _load_landing_proxy(data: dict) -> LandingProxyConfig:
    _reject_unknown_keys(LandingProxyConfig, data, "landing_proxy")
    transport = _load_transport(data.get("transport", {}))
    security = _load_security(data.get("security", {}))
    flat = {k: v for k, v in data.items() if k not in ("transport", "security")}
    lp = _from_toml(LandingProxyConfig, flat)
    lp.transport = transport
    lp.security = security
    return lp


def _load_routing(data: dict) -> RoutingConfig:
    _reject_unknown_keys(RoutingConfig, data, "routing")
    for idx, rule_data in enumerate(data.get("rules", [])):
        _reject_unknown_keys(RoutingRule, rule_data, f"routing.rules[{idx}]")
    try:
        rules = [_from_toml(RoutingRule, r) for r in data.get("rules", [])]
    except TypeError as e:
        raise ConfigError(f"路由规则配置不完整: {e}") from e
    flat = {k: v for k, v in data.items() if k != "rules"}
    rc = _from_toml(RoutingConfig, flat)
    rc.rules = rules
    return rc


def _load_dns(data: dict) -> DnsConfig:
    _reject_unknown_keys(DnsConfig, data, "dns")
    for idx, server_data in enumerate(data.get("servers", [])):
        _reject_unknown_keys(DnsServer, server_data, f"dns.servers[{idx}]")
    try:
        servers = [_from_toml(DnsServer, s) for s in data.get("servers", [])]
    except TypeError as e:
        raise ConfigError(f"DNS 配置不完整: {e}") from e
    flat = {k: v for k, v in data.items() if k != "servers"}
    dc = _from_toml(DnsConfig, flat)
    dc.servers = servers
    return dc


def _validate_config(cfg: KrayminiConfig) -> None:
    if not cfg.subscriptions:
        raise ConfigError("至少配置一个订阅源")
    for sub in cfg.subscriptions:
        if not sub.url.strip():
            raise ConfigError("订阅源 url 不能为空")
        if not sub.url.strip().startswith(("http://", "https://")):
            raise ConfigError(f"订阅源 url 格式不正确: {sub.url!r}")

    ports = [cfg.inbound.socks_port, cfg.inbound.http_port, cfg.inbound.api_port]
    for p in ports:
        if not (1 <= p <= 65535):
            raise ConfigError(f"端口 {p} 超出有效范围 (1-65535)")
    if len(set(ports)) != len(ports):
        raise ConfigError("端口配置存在冲突，三个端口必须互不相同")

    try:
        ipaddress.ip_address(cfg.inbound.listen)
    except ValueError as e:
        raise ConfigError(f"listen 地址不合法: {cfg.inbound.listen!r}") from e

    if cfg.general.refresh_interval <= 0:
        raise ConfigError("refresh_interval 必须为正整数")

    if cfg.log.level not in VALID_LOG_LEVELS:
        raise ConfigError(f"level 必须为 {VALID_LOG_LEVELS} 之一，实际: {cfg.log.level!r}")
    if cfg.log.xray_level not in VALID_XRAY_LEVELS:
        raise ConfigError(
            f"xray_level 必须为 {VALID_XRAY_LEVELS} 之一，实际: {cfg.log.xray_level!r}"
        )

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
            raise ConfigError(
                f"network 必须为 {VALID_NETWORKS} 之一，实际: {lp.transport.network!r}"
            )
        if lp.security.mode == "reality":
            if not lp.security.server_name:
                raise ConfigError("reality 模式需要 server_name")
            if lp.security.reality is None or not lp.security.reality.public_key:
                raise ConfigError("reality 模式需要 public_key")

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
            tag = rule.outbound_tag
            if tag in VALID_OUTBOUND_TAGS:
                pass
            elif lp is not None and tag.startswith(LANDING_CHAIN_PREFIX):
                pass
            else:
                lp_hint = "；或 LP-Via: <节点备注>（与 [landing_proxy] 链式出口对应）"
                hint = f"可用: {sorted(VALID_OUTBOUND_TAGS)}" + (lp_hint if lp else "")
                raise ConfigError(
                    f"outbound_tag {tag!r} 无效。{hint}"
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

    _reject_unknown_top_level(raw)
    _reject_unknown_keys(GeneralConfig, raw.get("general", {}), "general")

    general = _from_toml(GeneralConfig, raw.get("general", {}))
    general.output_config = _expand_path(general.output_config)

    for idx, subscription_data in enumerate(raw.get("subscriptions", [])):
        _reject_unknown_keys(
            SubscriptionConfig,
            subscription_data,
            f"subscriptions[{idx}]",
        )
    try:
        subscriptions = [_from_toml(SubscriptionConfig, s) for s in raw.get("subscriptions", [])]
    except TypeError as e:
        raise ConfigError(f"订阅源配置不完整: {e}") from e

    _reject_unknown_keys(InboundConfig, raw.get("inbound", {}), "inbound")
    inbound = _from_toml(InboundConfig, raw.get("inbound", {}))

    landing_proxy = _load_landing_proxy(raw["landing_proxy"]) if "landing_proxy" in raw else None
    routing = _load_routing(raw["routing"]) if "routing" in raw else None
    dns = _load_dns(raw["dns"]) if "dns" in raw else None
    _reject_unknown_keys(
        ObservatoryConfig,
        raw.get("observatory", {}),
        "observatory",
    )
    observatory = _from_toml(ObservatoryConfig, raw.get("observatory", {}))

    _reject_unknown_keys(LogConfig, raw.get("log", {}), "log")
    log = _from_toml(LogConfig, raw.get("log", {}))
    if log.file:
        log.file = _expand_path(log.file)

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
