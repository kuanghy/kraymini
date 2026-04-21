# 配置了 [landing_proxy] 时，链式出站（节点→落地）的 outbound tag 前缀
LANDING_CHAIN_PREFIX = "LP-Via: "

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# mixed inbound tag（与 generator 中 mixed 入站一致，供 stats 查询与日志）
STATS_INBOUND_TAG = "in-mixed"
STATS_LOG_INTERVAL = 300  # 秒，固定 5 分钟输出一次流量
STATS_QUERY_TIMEOUT = 5  # xray api 调用超时
