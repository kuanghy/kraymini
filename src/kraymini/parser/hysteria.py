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

    parsed = urlparse(uri_part.replace("hy2://", "https://", 1))
    params = parse_qs(parsed.query, keep_blank_values=True)

    def param(key: str, default: str = "") -> str:
        values = params.get(key, [default])
        return values[0] if values else default

    password = unquote(parsed.username or "")
    address = parsed.hostname or ""
    port = parsed.port or 0

    insecure_raw = param("insecure", "0")
    insecure = insecure_raw == "1"

    transport = {
        "network": "hysteria2",
        "sni": param("sni"),
        "insecure": insecure,
    }

    obfs = param("obfs")
    if obfs:
        transport["obfs"] = obfs
        transport["obfs_password"] = param("obfs-password")

    return Node(
        raw_uri=raw_uri,
        remark=fragment,
        protocol="hysteria2",
        address=address,
        port=port,
        credentials={"password": password},
        transport=transport,
    )
