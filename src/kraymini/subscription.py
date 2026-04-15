from __future__ import annotations

import base64
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from .config import KrayminiConfig
from .constants import USER_AGENT
from .log import logger
from .models import Node
from .parser import parse_uri, ParseError

RESERVED_TAGS = {
    "landing-proxy", "direct", "blocked", "api", "balancer",
    "in-api", "in-socks", "in-http",
}


class FetchError(Exception):
    pass


def fetch_subscription(
    url: str,
    timeout: int = 10,
    retries: int = 3,
) -> list[str]:
    last_error: Exception | None = None

    for attempt in range(retries):
        if attempt > 0:
            wait = 2 ** (attempt - 1)
            logger.debug("重试订阅拉取 (%d/%d), 等待 %ds: %s", attempt + 1, retries, wait, url)
            time.sleep(wait)

        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=timeout) as resp:
                body = resp.read()
        except (URLError, HTTPError, OSError) as e:
            last_error = e
            logger.warning("订阅拉取失败 (%d/%d): %s - %s", attempt + 1, retries, url, e)
            continue

        try:
            decoded = base64.b64decode(body).decode("utf-8")
        except Exception:
            decoded = body.decode("utf-8")

        uris = [line.strip() for line in decoded.splitlines() if line.strip()]
        logger.info("订阅拉取成功: %s, 共 %d 条 URI", url, len(uris))
        return uris

    raise FetchError(f"订阅拉取失败 (已重试 {retries} 次): {url} - {last_error}")


def deduplicate_nodes(nodes: list[Node]) -> list[Node]:
    seen: set[str] = set()
    result: list[Node] = []
    for node in nodes:
        if node.dedup_key not in seen:
            seen.add(node.dedup_key)
            result.append(node)
    return result


def assign_names(nodes: list[Node]) -> list[Node]:
    result: list[Node] = []
    for i, node in enumerate(nodes):
        name = node.remark
        if not name:
            prefix = node.source if node.source else "sub"
            name = f"{prefix}-{i}"
        if name in RESERVED_TAGS:
            name = f"{name}_node"
        result.append(replace(node, remark=name))

    name_count: dict[str, int] = {}
    final: list[Node] = []
    for node in result:
        name = node.remark
        if name in name_count:
            name_count[name] += 1
            final.append(replace(node, remark=f"{name}_{name_count[name]}"))
        else:
            name_count[name] = 1
            final.append(node)

    return final


def _keyword_matches_node(node: Node, keyword: str) -> bool:
    """子串匹配节点备注或地址（不区分大小写）。"""
    k = keyword.lower()
    return k in node.remark.lower() or k in node.address.lower()


def filter_nodes(
    nodes: list[Node],
    include: list[str],
    exclude: list[str],
) -> list[Node]:
    result = nodes
    if include:
        result = [
            n for n in result
            if any(_keyword_matches_node(n, kw) for kw in include)
        ]
    if exclude:
        result = [
            n for n in result
            if not any(_keyword_matches_node(n, kw) for kw in exclude)
        ]
    return result


def get_cache_path(config_path: str, runtime_dir: str = "~/.kraymini") -> Path:
    config_abs = str(Path(config_path).expanduser().resolve())
    hash8 = hashlib.sha256(config_abs.encode()).hexdigest()[:8]
    return Path(runtime_dir).expanduser() / f"nodes-cache-{hash8}.json"


def save_cache(nodes: list[Node], path: Path) -> None:
    data = {
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "nodes": [node.to_dict() for node in nodes],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp_path.rename(path)
    logger.info("节点缓存已保存: %s (%d 个节点)", path, len(nodes))


def load_cache_payload(path: Path) -> tuple[list[Node], str | None] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            nodes_data = data
            saved_at = None
        elif isinstance(data, dict):
            nodes_data = data.get("nodes")
            saved_at = data.get("saved_at")
        else:
            raise ValueError("缓存数据格式错误")
        if not isinstance(nodes_data, list):
            raise ValueError("缓存节点数据格式错误")
        nodes = [Node.from_dict(d) for d in nodes_data]
        logger.info("已加载节点缓存: %s (%d 个节点)", path, len(nodes))
        return nodes, saved_at if isinstance(saved_at, str) and saved_at else None
    except Exception as e:
        logger.warning("缓存文件损坏，将忽略: %s - %s", path, e)
        return None


def load_cache(path: Path) -> list[Node] | None:
    payload = load_cache_payload(path)
    if payload is None:
        return None
    nodes, _saved_at = payload
    return nodes


def _log_node(node: Node) -> None:
    transport_network = node.transport.get("network", "unknown")
    logger.debug(
        "节点: [%s] %s @ %s:%d (%s)",
        node.protocol, node.remark, node.address, node.port, transport_network,
    )


class SubscriptionManager:
    def __init__(
        self,
        config: KrayminiConfig,
        config_path: str,
        runtime_dir: str = "~/.kraymini",
    ):
        self.config = config
        self.cache_path = get_cache_path(config_path, runtime_dir)

    def refresh(self) -> list[Node] | None:
        all_uris: list[tuple[str, str]] = []
        errors: list[str] = []

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(fetch_subscription, sub.url): sub
                for sub in self.config.subscriptions
            }
            for future in as_completed(futures):
                sub = futures[future]
                try:
                    uris = future.result()
                    for u in uris:
                        all_uris.append((u, sub.name))
                except FetchError as e:
                    errors.append(f"{sub.name or sub.url}: {e}")
                    logger.warning("订阅源拉取失败: %s", e)

        nodes: list[Node] = []
        for uri, source in all_uris:
            try:
                node = parse_uri(uri)
                node = replace(node, source=source)
                _log_node(node)
                nodes.append(node)
            except ParseError as e:
                logger.warning("节点解析失败, 跳过: %s", e)

        if not nodes:
            if errors or not all_uris:
                logger.warning("所有订阅源拉取失败或无有效节点，尝试加载缓存")
                cached = load_cache(self.cache_path)
                if cached:
                    logger.warning("已回退到缓存节点 (%d 个)", len(cached))
                    return cached
                return None

        nodes = deduplicate_nodes(nodes)
        nodes = filter_nodes(
            nodes,
            include=self.config.general.node_include,
            exclude=self.config.general.node_exclude,
        )
        logger.info(
            "过滤后保留 %d 个节点 (include=%s, exclude=%s)",
            len(nodes),
            self.config.general.node_include or "无",
            self.config.general.node_exclude or "无",
        )
        nodes = assign_names(nodes)
        save_cache(nodes, self.cache_path)
        return nodes

    @staticmethod
    def nodes_changed(old: list[Node] | None, new: list[Node] | None) -> bool:
        if old is None or new is None:
            return old is not new
        old_uris = {n.dedup_key for n in old}
        new_uris = {n.dedup_key for n in new}
        return old_uris != new_uris
