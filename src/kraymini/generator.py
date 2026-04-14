from __future__ import annotations

import json
from pathlib import Path

from .config import (
    InboundConfig,
    KrayminiConfig,
    LandingProxyConfig,
    RoutingConfig,
    DnsConfig,
    ObservatoryConfig,
)
from .constants import LANDING_CHAIN_PREFIX, USER_AGENT
from .models import Node


def landing_chain_tag(node_remark: str) -> str:
    return f"{LANDING_CHAIN_PREFIX}{node_remark}"


def generate_inbounds(cfg: InboundConfig) -> list[dict]:
    inbounds = [
        {
            "tag": "in-api",
            "protocol": "dokodemo-door",
            "listen": cfg.listen,
            "port": cfg.api_port,
            "settings": {"address": "127.0.0.1"},
        },
    ]
    sniffing_cfg = None
    if cfg.sniffing:
        sniffing_cfg = {"enabled": True, "destOverride": ["http", "tls"]}

    socks_ib: dict = {
        "tag": "in-socks",
        "protocol": "socks",
        "listen": cfg.listen,
        "port": cfg.socks_port,
        "settings": {"udp": True},
    }
    if sniffing_cfg:
        socks_ib["sniffing"] = sniffing_cfg

    http_ib: dict = {
        "tag": "in-http",
        "protocol": "http",
        "listen": cfg.listen,
        "port": cfg.http_port,
    }
    if sniffing_cfg:
        http_ib["sniffing"] = sniffing_cfg

    inbounds.append(socks_ib)
    inbounds.append(http_ib)
    return inbounds


def _build_stream_settings(transport: dict) -> dict:
    network = transport.get("network", "tcp")
    security = transport.get("security", "")
    ss: dict = {"network": network}

    if security == "tls":
        tls: dict = {
            "serverName": transport.get("sni", ""),
            "allowInsecure": transport.get("insecure", False),
            "fingerprint": transport.get("fingerprint", "chrome"),
        }
        alpn = transport.get("alpn", "")
        if alpn:
            tls["alpn"] = [a.strip() for a in alpn.split(",")]
        elif network in ("grpc", "h2"):
            tls["alpn"] = ["h2"]
        elif network == "tuic":
            tls["alpn"] = ["h3"]
        else:
            tls["alpn"] = ["http/1.1"]
        ss["security"] = "tls"
        ss["tlsSettings"] = tls
    elif security == "reality":
        ss["security"] = "reality"
        ss["realitySettings"] = {
            "serverName": transport.get("sni", ""),
            "fingerprint": transport.get("fingerprint", "chrome"),
            "publicKey": transport.get("public_key", ""),
            "shortId": transport.get("short_id", ""),
            "spiderX": transport.get("spider_x", "/"),
        }
    else:
        ss["security"] = "none"

    if network == "tcp":
        header_type = transport.get("header_type", "")
        if header_type == "http":
            request: dict = {}
            path = transport.get("path", "")
            if path:
                request["path"] = [path]
            host = transport.get("host", "")
            if host:
                request["headers"] = {"Host": [host]}
            ss["tcpSettings"] = {"header": {"type": "http", "request": request}}
    elif network == "ws":
        headers = {
            "Host": transport.get("host", ""),
            "User-Agent": USER_AGENT,
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        ss["wsSettings"] = {"path": transport.get("path", "/"), "headers": headers}
    elif network == "grpc":
        ss["grpcSettings"] = {
            "serviceName": transport.get("service_name", ""),
            "multiMode": transport.get("multi_mode", True),
        }
    elif network == "h2":
        h2s: dict = {"path": transport.get("path", "/")}
        host = transport.get("host", "")
        if host:
            h2s["host"] = [host] if isinstance(host, str) else host
        ss["httpSettings"] = h2s
    elif network == "httpupgrade":
        ss["httpupgradeSettings"] = {
            "host": transport.get("host", ""),
            "path": transport.get("path", "/"),
        }
    elif network == "xhttp":
        xs: dict = {
            "host": transport.get("host", ""),
            "path": transport.get("path", "/"),
        }
        mode = transport.get("xhttp_mode", "")
        if mode:
            xs["mode"] = mode
        ss["xhttpSettings"] = xs

    return ss


def generate_node_outbound(node: Node, proxy_tag: str | None = None) -> dict:
    ob: dict = {"tag": node.remark, "protocol": "", "settings": {}, "streamSettings": {}}

    if node.protocol == "vmess":
        ob["protocol"] = "vmess"
        ob["settings"] = {
            "vnext": [{
                "address": node.address,
                "port": node.port,
                "users": [{
                    "id": node.credentials.get("uuid", ""),
                    "alterId": node.credentials.get("alter_id", 0),
                    "security": node.credentials.get("security", "auto"),
                }],
            }],
        }
    elif node.protocol == "vless":
        ob["protocol"] = "vless"
        user: dict = {
            "id": node.credentials.get("uuid", ""),
            "encryption": node.credentials.get("encryption", "none"),
        }
        flow = node.credentials.get("flow", "")
        if flow:
            user["flow"] = flow
        ob["settings"] = {
            "vnext": [{
                "address": node.address,
                "port": node.port,
                "users": [user],
            }],
        }
    elif node.protocol == "trojan":
        ob["protocol"] = "trojan"
        ob["settings"] = {
            "servers": [{
                "address": node.address,
                "port": node.port,
                "password": node.credentials.get("password", ""),
            }],
        }
    elif node.protocol == "ss":
        ob["protocol"] = "shadowsocks"
        ob["settings"] = {
            "servers": [{
                "address": node.address,
                "port": node.port,
                "method": node.credentials.get("method", ""),
                "password": node.credentials.get("password", ""),
            }],
        }
    elif node.protocol == "hysteria2":
        ob["protocol"] = "hysteria2"
        server: dict = {
            "address": node.address,
            "port": node.port,
            "password": node.credentials.get("password", ""),
        }
        obfs = node.transport.get("obfs", "")
        if obfs:
            server["obfs"] = {
                "type": obfs,
                "password": node.transport.get("obfs_password", ""),
            }
        ob["settings"] = {"servers": [server]}
    elif node.protocol == "tuic":
        ob["protocol"] = "tuic"
        tuic_settings: dict = {
            "server": node.address,
            "port": node.port,
            "uuid": node.credentials.get("uuid", ""),
            "password": node.credentials.get("password", ""),
        }
        congestion = node.transport.get("congestion_control", "bbr")
        if congestion:
            tuic_settings["congestionControl"] = congestion
        udp_mode = node.transport.get("udp_relay_mode", "native")
        if udp_mode:
            tuic_settings["udpRelayMode"] = udp_mode
        if node.transport.get("zero_rtt", False):
            tuic_settings["zeroRttHandshake"] = True
        ob["settings"] = tuic_settings

    ob["streamSettings"] = _build_stream_settings(node.transport)

    if proxy_tag:
        ob["proxySettings"] = {"tag": proxy_tag, "transportLayer": True}

    return ob


def _build_landing_outbound_body(lp: LandingProxyConfig) -> dict:
    transport_dict: dict = {
        "network": lp.transport.network,
        "security": lp.security.mode,
        "sni": lp.security.server_name,
        "fingerprint": lp.security.fingerprint,
        "alpn": ",".join(lp.security.alpn) if lp.security.alpn else "",
    }
    if lp.transport.network == "ws" and lp.transport.ws:
        transport_dict["host"] = lp.transport.ws.host
        transport_dict["path"] = lp.transport.ws.path
    elif lp.transport.network == "grpc" and lp.transport.grpc:
        transport_dict["service_name"] = lp.transport.grpc.service_name
        transport_dict["multi_mode"] = lp.transport.grpc.multi_mode
    elif lp.transport.network == "h2" and lp.transport.h2:
        transport_dict["host"] = lp.transport.h2.host
        transport_dict["path"] = lp.transport.h2.path
    elif lp.transport.network == "xhttp" and lp.transport.xhttp:
        transport_dict["host"] = lp.transport.xhttp.host
        transport_dict["path"] = lp.transport.xhttp.path
        if lp.transport.xhttp.mode:
            transport_dict["xhttp_mode"] = lp.transport.xhttp.mode
    elif lp.transport.network == "httpupgrade" and lp.transport.httpupgrade:
        transport_dict["host"] = lp.transport.httpupgrade.host
        transport_dict["path"] = lp.transport.httpupgrade.path
    if lp.security.mode == "reality" and lp.security.reality:
        transport_dict["public_key"] = lp.security.reality.public_key
        transport_dict["short_id"] = lp.security.reality.short_id
        transport_dict["spider_x"] = lp.security.reality.spider_x

    node = Node(
        raw_uri="", remark="landing-proxy", protocol=lp.protocol,
        address=lp.address, port=lp.port,
        credentials={"uuid": lp.uuid, "password": lp.password,
                      "method": lp.method, "encryption": "none"},
        transport=transport_dict,
    )
    return generate_node_outbound(node, proxy_tag=None)


def generate_landing_proxy_outbound(lp: LandingProxyConfig) -> dict:
    """单条落地 outbound（无链），供测试与协议映射校验。"""
    ob = _build_landing_outbound_body(lp)
    ob["tag"] = "landing-proxy"
    return ob


def generate_landing_chain_outbound(
    lp: LandingProxyConfig, chain_tag: str, via_node_tag: str
) -> dict:
    """落地协议出站，经订阅节点 outbound 连接落地机（出口为落地 IP）。"""
    ob = _build_landing_outbound_body(lp)
    ob["tag"] = chain_tag
    ob["proxySettings"] = {"tag": via_node_tag, "transportLayer": True}
    return ob


def generate_fixed_outbounds() -> list[dict]:
    return [
        {"tag": "direct", "protocol": "freedom", "settings": {"domainStrategy": "UseIP"}},
        {"tag": "blocked", "protocol": "blackhole", "settings": {}},
    ]


def generate_balancer(
    node_tags: list[str], fallback_tag: str | None = None
) -> dict:
    balancer = {
        "tag": "balancer",
        "selector": node_tags,
        "strategy": {"type": "leastPing"},
    }
    if fallback_tag:
        balancer["fallbackTag"] = fallback_tag
    return balancer


def generate_observatory(node_tags: list[str], cfg: ObservatoryConfig) -> dict:
    return {
        "subjectSelector": node_tags,
        "probeURL": cfg.probe_url,
        "probeInterval": cfg.probe_interval,
        "enableConcurrency": cfg.enable_concurrency,
    }


def generate_routing(
    cfg: RoutingConfig | None,
    node_tags: list[str],
    fallback_tag: str | None = None,
) -> dict:
    domain_strategy = "IPOnDemand"
    domain_matcher = "mph"
    if cfg is not None:
        domain_strategy = cfg.domain_strategy
        domain_matcher = cfg.domain_matcher

    rules: list[dict] = []
    rules.append({"type": "field", "inboundTag": ["in-api"], "outboundTag": "api"})

    if cfg is not None:
        for rule in cfg.rules:
            r: dict = {"type": "field", "outboundTag": rule.outbound_tag}
            if rule.domain:
                r["domain"] = rule.domain
            if rule.ip:
                r["ip"] = rule.ip
            if rule.network:
                r["network"] = rule.network
            if rule.inbound_tag:
                r["inboundTag"] = rule.inbound_tag
            rules.append(r)

    rules.append({"type": "field", "network": "tcp,udp", "balancerTag": "balancer"})

    return {
        "domainStrategy": domain_strategy,
        "domainMatcher": domain_matcher,
        "rules": rules,
        "balancers": [generate_balancer(node_tags, fallback_tag=fallback_tag)],
    }


def generate_dns(cfg: DnsConfig | None) -> dict | None:
    if cfg is None:
        return None
    dns: dict = {}
    if cfg.hosts:
        dns["hosts"] = cfg.hosts
    servers: list[dict] = []
    for srv in cfg.servers:
        s: dict = {"address": srv.address}
        if srv.port != 53:
            s["port"] = srv.port
        if srv.domains:
            s["domains"] = srv.domains
        if srv.expect_ips:
            s["expectIPs"] = srv.expect_ips
        servers.append(s)
    if servers:
        dns["servers"] = servers
    return dns


def generate_api() -> dict:
    return {
        "tag": "api",
        "services": ["HandlerService", "LoggerService", "RoutingService", "ObservatoryService"],
    }


def generate_stats_policy() -> tuple[dict, dict]:
    stats: dict = {}
    policy = {"system": {"statsOutboundUplink": True, "statsOutboundDownlink": True}}
    return stats, policy


def generate_xray_config(cfg: KrayminiConfig, nodes: list[Node]) -> dict:
    outbounds: list[dict] = []
    if cfg.landing_proxy:
        balancer_tags: list[str] = []
        for node in nodes:
            ct = landing_chain_tag(node.remark)
            balancer_tags.append(ct)
            outbounds.append(
                generate_landing_chain_outbound(cfg.landing_proxy, ct, node.remark)
            )
        for node in nodes:
            outbounds.append(generate_node_outbound(node, proxy_tag=None))
        balancer_fallback_tag = "blocked"
    else:
        for node in nodes:
            outbounds.append(generate_node_outbound(node, proxy_tag=None))
        balancer_tags = [n.remark for n in nodes]
        balancer_fallback_tag = None

    outbounds.extend(generate_fixed_outbounds())

    routing = generate_routing(
        cfg.routing,
        balancer_tags,
        fallback_tag=balancer_fallback_tag,
    )
    observatory = generate_observatory(balancer_tags, cfg.observatory)
    dns = generate_dns(cfg.dns)
    api = generate_api()
    stats, policy = generate_stats_policy()

    xray: dict = {
        "log": {"loglevel": cfg.log.xray_level},
        "api": api,
        "inbounds": generate_inbounds(cfg.inbound),
        "outbounds": outbounds,
        "routing": routing,
        "observatory": observatory,
        "stats": stats,
        "policy": policy,
    }
    if dns is not None:
        xray["dns"] = dns
    return xray


def write_xray_config(xray_config: dict, output_path: str) -> str:
    path = Path(output_path)
    tmp_path = path.with_suffix(".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.write_text(
        json.dumps(xray_config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp_path.rename(path)
    return str(path)
