from __future__ import annotations

import base64

from ..models import Node
from ._utils import split_fragment


def _b64decode(s: str) -> str:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    try:
        return base64.urlsafe_b64decode(s).decode("utf-8")
    except Exception:
        return base64.b64decode(s).decode("utf-8")


def parse(uri: str) -> Node:
    raw_uri = uri
    uri_part, fragment = split_fragment(uri)
    body = uri_part.removeprefix("ss://")

    if "@" in body:
        user_part, server_part = body.rsplit("@", 1)
        decoded_user = _b64decode(user_part)
        method, password = decoded_user.split(":", 1)
        host_port = server_part.split("?")[0]
        host, port_str = host_port.rsplit(":", 1)
        port = int(port_str)
    else:
        decoded = _b64decode(body.split("?")[0])
        method_pw, host_port = decoded.rsplit("@", 1)
        method, password = method_pw.split(":", 1)
        host, port_str = host_port.rsplit(":", 1)
        port = int(port_str)

    return Node(
        raw_uri=raw_uri,
        remark=fragment,
        protocol="ss",
        address=host,
        port=port,
        credentials={
            "method": method,
            "password": password,
        },
        transport={"network": "tcp"},
    )
