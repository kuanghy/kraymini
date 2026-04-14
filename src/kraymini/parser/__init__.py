from __future__ import annotations

from ..models import Node
from . import vmess, vless, trojan, shadowsocks, hysteria, tuic

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
                return module.parse(uri)
            except ParseError:
                raise
            except Exception as e:
                raise ParseError(f"解析 {prefix} URI 失败: {e}") from e
    raise ParseError(f"不支持的协议: {uri[:30]}...")
