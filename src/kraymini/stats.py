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


def _parse_statsquery_payload(payload: dict) -> tuple[int, int] | None:
    raw = payload.get("stat")
    if raw is None:
        logger.debug("statsquery 响应缺少 stat 字段")
        return None
    if not isinstance(raw, list):
        logger.debug("statsquery 响应 stat 非列表")
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
        value = item.get("value")
        if not isinstance(name, str):
            continue
        if not isinstance(value, str):
            continue
        try:
            v = int(value)
        except ValueError:
            logger.debug("statsquery 计数器值非整数: %s=%r", name, value)
            continue
        if name.endswith(">>>traffic>>>uplink"):
            uplink = v
        elif name.endswith(">>>traffic>>>downlink"):
            downlink = v

    # 任一计数器缺失都视为查询失败，避免误导性地把缺失值当 0 输出
    if uplink is None or downlink is None:
        logger.debug(
            "statsquery 计数器不完整: uplink=%r downlink=%r", uplink, downlink
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
    """调用 ``xray api statsquery`` 查询指定 inbound 的累计上下行字节数。"""
    bin_path = resolve_xray_bin(xray_bin)
    if not bin_path:
        logger.warning("流量统计: 找不到 xray 可执行文件: %s", xray_bin)
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
        logger.debug("statsquery 超时: %s", cmd)
        return None
    except OSError as e:
        logger.debug("statsquery 执行失败: %s", e)
        return None

    if result.returncode != 0:
        logger.debug(
            "statsquery 非零退出: code=%s stderr=%s",
            result.returncode,
            (result.stderr or "").strip(),
        )
        return None

    stdout = (result.stdout or "").strip()
    if not stdout:
        logger.debug("statsquery 无输出")
        return None

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as e:
        logger.debug("statsquery JSON 解析失败: %s", e)
        return None

    if not isinstance(payload, dict):
        logger.debug("statsquery 根节点非对象")
        return None

    parsed = _parse_statsquery_payload(payload)
    return parsed
