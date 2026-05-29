from __future__ import annotations

from dataclasses import replace

from ..models import Node
from . import vmess, vless, trojan, shadowsocks, hysteria, tuic
from ._utils import normalize_server_address

PARSERS = {
    "vmess://": vmess,
    "vless://": vless,
    "trojan://": trojan,
    "ss://": shadowsocks,
    "hy2://": hysteria,
    "hysteria2://": hysteria,
    "tuic://": tuic,
}


class ParseError(Exception):
    pass


def parse_uri(uri: str) -> Node:
    for prefix, module in PARSERS.items():
        if uri.startswith(prefix):
            try:
                node = module.parse(uri)
                try:
                    address = normalize_server_address(node.address)
                except ValueError as e:
                    raise ParseError(f"节点地址不合法: {e}") from e
                return replace(node, address=address)
            except ParseError:
                raise
            except Exception as e:
                raise ParseError(f"解析 {prefix} URI 失败: {e}") from e
    raise ParseError(f"不支持的协议: {uri[:30]}...")
