from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from ..models import Node
from ._utils import split_fragment


def parse(uri: str) -> Node:
    raw_uri = uri
    uri_part, fragment = split_fragment(uri)

    parsed = urlparse(uri_part.replace("vless://", "https://", 1))
    params = parse_qs(parsed.query, keep_blank_values=True)

    def param(key: str, default: str = "") -> str:
        values = params.get(key, [default])
        return values[0] if values else default

    uuid = parsed.username or ""
    address = parsed.hostname or ""
    port = parsed.port or 0

    network = param("type", "tcp")
    security = param("security", "none")

    transport = {
        "network": network,
        "security": security,
        "sni": param("sni"),
        "fingerprint": param("fp"),
        "alpn": param("alpn"),
        "host": param("host"),
        "path": param("path"),
        "header_type": param("headerType"),
    }

    if network == "grpc":
        transport["service_name"] = param("serviceName")

    if security == "reality":
        transport["public_key"] = param("pbk")
        transport["short_id"] = param("sid")
        transport["spider_x"] = param("spx", "/")

    credentials: dict = {
        "uuid": uuid,
        "encryption": param("encryption", "none"),
    }
    flow = param("flow")
    if flow:
        credentials["flow"] = flow

    return Node(
        raw_uri=raw_uri,
        remark=fragment,
        protocol="vless",
        address=address,
        port=port,
        credentials=credentials,
        transport=transport,
    )
