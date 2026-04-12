from __future__ import annotations

from urllib.parse import unquote


def split_fragment(uri: str) -> tuple[str, str]:
    """拆分 URI 和 fragment（#后的部分），对 fragment 做 URL 解码"""
    if "#" in uri:
        uri_part, fragment = uri.rsplit("#", 1)
        return uri_part, unquote(fragment)
    return uri, ""
