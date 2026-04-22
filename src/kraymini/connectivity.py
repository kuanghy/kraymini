from __future__ import annotations

import ipaddress
import socket
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from .constants import USER_AGENT


@dataclass(frozen=True)
class ProbeResult:
    """单次 HTTP 连通性探测结果"""

    ok: bool
    latency_ms: int | None = None
    error: str | None = None


def parse_tcp_target(spec: str) -> tuple[str, int]:
    """解析 ``host:port`` 或 ``[IPv6]:port`` 形式的 TCP 目标

    Args:
        spec: 例如 ``223.5.5.5:443`` 或 ``[::1]:443``

    Returns:
        (host, port)，host 为传给 ``socket.create_connection`` 的形式

    Raises:
        ValueError: 格式或端口不合法
    """
    s = spec.strip()
    if not s:
        raise ValueError("空目标")

    if s.startswith("["):
        end = s.find("]")
        if end == -1:
            raise ValueError("缺少 ]")
        inner = s[1:end].strip()
        rest = s[end + 1 :].strip()
        if not rest.startswith(":"):
            raise ValueError("IPv6 后缺少 :port")
        port_s = rest[1:].strip()
        if not port_s.isdigit():
            raise ValueError("端口非数字")
        port = int(port_s)
        try:
            ipaddress.ip_address(inner)
        except ValueError as e:
            raise ValueError(f"非法 IPv6: {inner!r}") from e
        host = inner
    else:
        host_part, sep, port_s = s.rpartition(":")
        if sep != ":" or not port_s.isdigit():
            raise ValueError("应为 host:port")
        host = host_part.strip()
        if not host:
            raise ValueError("主机名为空")
        port = int(port_s)

    if not (1 <= port <= 65535):
        raise ValueError("端口超出范围")
    return host, port


def _http_proxy_base(listen: str, mixed_port: int) -> str:
    """构造本地 mixed 入站的 HTTP 代理 URL（供 urllib 使用）

    监听地址为通配（0.0.0.0 / ::）时回落到回环，避免 urllib 真的去连通配地址
    """
    try:
        addr = ipaddress.ip_address(listen)
    except ValueError:
        return f"http://{listen}:{mixed_port}"

    if addr.version == 6:
        if addr == ipaddress.IPv6Address("::"):
            return f"http://[::1]:{mixed_port}"
        return f"http://[{addr.compressed}]:{mixed_port}"
    if addr == ipaddress.IPv4Address("0.0.0.0"):
        return f"http://127.0.0.1:{mixed_port}"
    return f"http://{addr}:{mixed_port}"


def check_proxy_connectivity(
    *,
    listen: str,
    mixed_port: int,
    probe_url: str,
    timeout: float,
) -> ProbeResult:
    """经本地 HTTP 代理请求 ``probe_url``，测量往返延迟（毫秒）"""
    proxy = _http_proxy_base(listen, mixed_port)
    handlers = [ProxyHandler({"http": proxy, "https": proxy})]
    opener = build_opener(*handlers)
    req = Request(probe_url, headers={"User-Agent": USER_AGENT})
    t0 = time.perf_counter()
    try:
        with opener.open(req, timeout=timeout) as resp:
            resp.read(1)
    except (URLError, HTTPError, OSError, TimeoutError) as e:
        return ProbeResult(ok=False, error=str(e))
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return ProbeResult(ok=True, latency_ms=elapsed_ms)


def check_local_connectivity(targets: list[str], *, timeout: float) -> bool:
    """对多个 ``host:port`` 依次尝试 TCP 连接，任一成功即视为本地网络可用"""
    for raw in targets:
        try:
            host, port = parse_tcp_target(raw)
        except ValueError:
            continue
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False
