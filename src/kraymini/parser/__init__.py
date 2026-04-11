from __future__ import annotations

from kraymini.models import Node
from kraymini.parser import vmess, vless, trojan, shadowsocks, hysteria

PARSERS = {
    "vmess://": vmess,
    "vless://": vless,
    "trojan://": trojan,
    "ss://": shadowsocks,
    "hy2://": hysteria,
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
