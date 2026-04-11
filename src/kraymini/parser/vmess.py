from __future__ import annotations

import base64
import json

from kraymini.models import Node


def parse(uri: str) -> Node:
    raw_uri = uri
    payload = uri.removeprefix("vmess://")

    padding = 4 - len(payload) % 4
    if padding != 4:
        payload += "=" * padding

    try:
        decoded = base64.urlsafe_b64decode(payload)
    except Exception:
        decoded = base64.b64decode(payload)

    data = json.loads(decoded)

    port = int(data.get("port", 0))
    network = data.get("net", "tcp")

    transport = {
        "network": network,
        "security": data.get("tls", ""),
        "sni": data.get("sni", ""),
        "fingerprint": data.get("fp", ""),
        "alpn": data.get("alpn", ""),
        "host": data.get("host", ""),
        "path": data.get("path", ""),
        "header_type": data.get("type", ""),
    }

    if network == "grpc":
        transport["service_name"] = data.get("path", "")

    return Node(
        raw_uri=raw_uri,
        remark=data.get("ps", ""),
        protocol="vmess",
        address=data.get("add", ""),
        port=port,
        credentials={
            "uuid": data.get("id", ""),
            "alter_id": int(data.get("aid", 0)),
            "security": data.get("scy", "auto"),
        },
        transport=transport,
    )
