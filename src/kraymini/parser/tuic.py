from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

from ..models import Node
from ._utils import split_fragment


def parse(uri: str) -> Node:
    raw_uri = uri
    uri_part, fragment = split_fragment(uri)

    parsed = urlparse(uri_part.replace("tuic://", "https://", 1))
    params = parse_qs(parsed.query, keep_blank_values=True)

    def param(key: str, default: str = "") -> str:
        values = params.get(key, [default])
        return values[0] if values else default

    uuid = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    address = parsed.hostname or ""
    port = parsed.port or 0

    insecure_raw = param("insecure", "0")
    insecure = insecure_raw == "1"

    # 支持 congestion_control 和缩写 cc 两种参数名
    congestion_control = param("congestion_control") or param("cc", "bbr")
    udp_relay_mode = param("udp_relay_mode", "native")
    zero_rtt = param("zero_rtt_handshake", "0") == "1"

    transport: dict = {
        "network": "tuic",
        "security": "tls",
        "sni": param("sni"),
        "insecure": insecure,
        "alpn": param("alpn"),
        "fingerprint": param("fp", "chrome"),
        "congestion_control": congestion_control,
        "udp_relay_mode": udp_relay_mode,
        "zero_rtt": zero_rtt,
    }

    return Node(
        raw_uri=raw_uri,
        remark=fragment,
        protocol="tuic",
        address=address,
        port=port,
        credentials={"uuid": uuid, "password": password},
        transport=transport,
    )
