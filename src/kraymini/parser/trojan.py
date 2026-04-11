from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

from kraymini.models import Node


def parse(uri: str) -> Node:
    raw_uri = uri

    fragment = ""
    if "#" in uri:
        uri_part, fragment = uri.rsplit("#", 1)
        fragment = unquote(fragment)
    else:
        uri_part = uri

    parsed = urlparse(uri_part.replace("trojan://", "https://", 1))
    params = parse_qs(parsed.query, keep_blank_values=True)

    def param(key: str, default: str = "") -> str:
        values = params.get(key, [default])
        return values[0] if values else default

    password = unquote(parsed.username or "")
    address = parsed.hostname or ""
    port = parsed.port or 0
    network = param("type", "tcp")

    transport = {
        "network": network,
        "security": param("security", "tls"),
        "sni": param("sni"),
        "fingerprint": param("fp"),
        "alpn": param("alpn"),
        "host": param("host"),
        "path": param("path"),
        "header_type": param("headerType"),
    }

    if network == "grpc":
        transport["service_name"] = param("serviceName")

    return Node(
        raw_uri=raw_uri,
        remark=fragment,
        protocol="trojan",
        address=address,
        port=port,
        credentials={"password": password},
        transport=transport,
    )
