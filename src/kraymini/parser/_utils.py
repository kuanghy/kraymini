from __future__ import annotations

import ipaddress
from urllib.parse import unquote


def split_fragment(uri: str) -> tuple[str, str]:
    """拆分 URI 和 fragment（#后的部分），对 fragment 做 URL 解码"""
    if "#" in uri:
        uri_part, fragment = uri.rsplit("#", 1)
        return uri_part, unquote(fragment)
    return uri, ""


def normalize_server_address(host: str) -> str:
    """去掉 IPv6 字面量外层方括号；域名与裸 IPv4/IPv6 原样返回

    仅当 ``[...]`` 内为合法 IPv6 时去括号；空括号、域名或 IPv4 会抛出 ``ValueError``
    """
    host = host.strip()
    if len(host) < 2 or host[0] != "[" or host[-1] != "]":
        return host

    inner = host[1:-1].strip()
    if not inner:
        raise ValueError("服务器地址方括号内为空")

    try:
        addr = ipaddress.ip_address(inner)
    except ValueError as e:
        raise ValueError(f"方括号内不是合法的 IPv6 地址: {inner!r}") from e

    if addr.version != 6:
        raise ValueError(
            f"方括号内须为 IPv6 地址，实际为 IPv{addr.version}: {inner!r}"
        )
    return addr.compressed
