from __future__ import annotations

import json
import subprocess

from .log import logger
from .process import resolve_xray_bin


def format_bytes(n: int) -> str:
    """1024 进制，保留两位小数（字节为整数）。"""
    n = max(0, n)
    if n < 1024:
        return f"{n} B"
    val = n / 1024.0
    for unit in ("KB", "MB", "GB", "TB"):
        if val < 1024 or unit == "TB":
            return f"{val:.2f} {unit}"
        val /= 1024
    # 理论不可达：循环最后一轮一定命中 TB 分支
    return f"{val:.2f} TB"


def format_traffic_log(uplink: int, downlink: int) -> str:
    return f"流量统计: 上行 {format_bytes(uplink)}, 下行 {format_bytes(downlink)}"


def _coerce_counter_value(raw) -> int | None:
    """xray 不同版本对 statsquery 计数器值的类型不一致：
    早期版本序列化为字符串（``"100"``），26.x 之后直接是 JSON 数字（``100``）。
    这里对两种形态都做兼容，失败时返回 None 交由上层打 warning。
    """
    if isinstance(raw, bool):  # bool 是 int 的子类，显式排除
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        try:
            return int(raw)
        except ValueError:
            return None
    return None


def _parse_statsquery_payload(
    payload: dict, *, endpoint: str, inbound_tag: str
) -> tuple[int, int] | None:
    raw = payload.get("stat")
    if raw is None:
        logger.warning(
            "流量统计查询失败: 响应缺少 stat 字段 (tag=%s, endpoint=%s)",
            inbound_tag, endpoint,
        )
        return None
    if not isinstance(raw, list):
        logger.warning(
            "流量统计查询失败: stat 字段非列表 (tag=%s, endpoint=%s)",
            inbound_tag, endpoint,
        )
        return None
    if len(raw) == 0:
        # xray 刚启动、还没有任何流量经过 in-mixed 时 stat 为空，视作零流量
        return 0, 0

    uplink: int | None = None
    downlink: int | None = None
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str):
            continue
        v = _coerce_counter_value(item.get("value"))
        if v is None:
            logger.warning(
                "流量统计计数器值不可解析: %s=%r (tag=%s, endpoint=%s)",
                name, item.get("value"), inbound_tag, endpoint,
            )
            continue
        if name.endswith(">>>traffic>>>uplink"):
            uplink = v
        elif name.endswith(">>>traffic>>>downlink"):
            downlink = v

    # 任一计数器缺失都视为查询失败，避免误导性地把缺失值当 0 输出
    if uplink is None or downlink is None:
        logger.warning(
            "流量统计查询失败: 计数器不完整 uplink=%r downlink=%r (tag=%s, endpoint=%s)",
            uplink, downlink, inbound_tag, endpoint,
        )
        return None
    return uplink, downlink


def query_inbound_traffic(
    xray_bin: str,
    api_endpoint: str,
    inbound_tag: str,
    *,
    timeout: float,
) -> tuple[int, int] | None:
    """调用 ``xray api statsquery`` 查询指定 inbound 的累计上下行字节数。

    任何失败路径都会通过 ``logger.warning`` 输出具体原因（带 tag 与 endpoint），
    便于运行时直接定位，不必再开启 DEBUG 日志。
    """
    bin_path = resolve_xray_bin(xray_bin)
    if not bin_path:
        logger.warning(
            "流量统计查询失败: 找不到 xray 可执行文件 %r (tag=%s, endpoint=%s)",
            xray_bin, inbound_tag, api_endpoint,
        )
        return None

    pattern = f"inbound>>>{inbound_tag}>>>traffic"
    cmd = [
        bin_path,
        "api",
        "statsquery",
        f"--server={api_endpoint}",
        "-pattern",
        pattern,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.warning(
            "流量统计查询失败: 超过 %ss 超时 (tag=%s, endpoint=%s)",
            timeout, inbound_tag, api_endpoint,
        )
        return None
    except OSError as e:
        logger.warning(
            "流量统计查询失败: 执行 xray 出错 %s (tag=%s, endpoint=%s)",
            e, inbound_tag, api_endpoint,
        )
        return None

    if result.returncode != 0:
        logger.warning(
            "流量统计查询失败: xray 非零退出 code=%s stderr=%s (tag=%s, endpoint=%s)",
            result.returncode,
            (result.stderr or "").strip(),
            inbound_tag,
            api_endpoint,
        )
        return None

    stdout = (result.stdout or "").strip()
    if not stdout:
        logger.warning(
            "流量统计查询失败: xray 无输出 (tag=%s, endpoint=%s)",
            inbound_tag, api_endpoint,
        )
        return None

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as e:
        logger.warning(
            "流量统计查询失败: JSON 解析失败 %s (tag=%s, endpoint=%s)",
            e, inbound_tag, api_endpoint,
        )
        return None

    if not isinstance(payload, dict):
        logger.warning(
            "流量统计查询失败: 响应根节点非对象 (tag=%s, endpoint=%s)",
            inbound_tag, api_endpoint,
        )
        return None

    return _parse_statsquery_payload(
        payload, endpoint=api_endpoint, inbound_tag=inbound_tag
    )
