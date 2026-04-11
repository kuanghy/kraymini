# kraymini 设计文档

## 1. 项目概述

### 1.1 定位

kraymini 是一个 Xray 服务管理器，负责从订阅源自动拉取代理节点，生成带负载均衡和健康检查的 Xray 配置，并管理 Xray 进程的生命周期。它以持久服务的形式运行，定时刷新订阅并自动重载配置，让用户无需手动维护节点列表和 Xray 配置。

### 1.2 目标

- 从多个订阅源拉取节点，自动合并去重
- 生成完整的 Xray 运行配置，包含 observatory + leastPing 自动选优
- 支持可选的落地代理（链式出站）
- 管理 Xray 子进程的启动、监控和重载
- 定时刷新订阅，节点变更时重新生成 xray 配置并重载 xray
- 支持用户自定义路由规则和 DNS 分流（通过模板文件）
- 跨平台运行：Linux / macOS / OpenWrt

### 1.3 非目标

- 不提供 Web UI 或 HTTP API
- 不实现节点测速和排序（依赖 Xray 内置 observatory）
- 不管理 GeoIP / GeoSite 数据文件的更新
- 不实现 Clash/Surge 等其他代理核心的支持
- 不实现流量统计和监控面板
- 不监听 kraymini 配置文件或模板文件变更；修改后需重启 kraymini 生效

### 1.4 技术栈

| 项目 | 选型 |
|------|------|
| 语言 | Python 3.11+ |
| 配置格式 | TOML（标准库 `tomllib`） |
| CLI | `argparse`（标准库） |
| 进程托管 | 由外部服务管理器（如 systemd / supervisor / procd）管理 kraymini，kraymini 管理 xray |
| 外部依赖 | 尽量仅使用标准库 |

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                      kraymini                           │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ Subscription │  │    Config    │  │    Process    │  │
│  │   Manager    │→│   Generator   │→│    Manager    │  │
│  └─────────────┘  └──────────────┘  └───────────────┘  │
│         ↑                ↑                   │          │
│         │                │                   ↓          │
│    订阅源 URLs      xray 模板文件         xray 进程      │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐                      │
│  │  Scheduler   │  │     CLI     │                      │
│  └─────────────┘  └──────────────┘                      │
└─────────────────────────────────────────────────────────┘
```

### 2.2 模块划分

| 模块 | 职责 | 对应章节 |
|------|------|---------|
| `config` | 加载和校验 kraymini 配置 | 第 3 节 |
| `subscription` | 订阅拉取、URI 解析、去重、缓存 | 第 4 节 |
| `generator` | 从节点列表 + 配置 + 模板生成 xray JSON | 第 5 节 |
| `process` | xray 子进程启动、监控、重载、停止 | 第 6 节 |
| `scheduler` | 定时触发订阅刷新和配置重载 | 第 6 节 |
| `cli` | 命令行入口和参数解析 | 第 7 节 |

### 2.3 数据流

```
订阅 URL ──HTTP GET──→ Base64 文本
                          │
                          ↓ 解码 + 按行分割
                      节点 URI 列表
                          │
                          ↓ 解析 + 去重
                      List[Node]
                          │
          kraymini 配置 ──┤
           xray 模板 ─────┤
                          ↓ 合并生成
                    xray JSON 配置
                          │
                          ↓ xray run -test
                    校验通过的配置文件
                          │
                          ↓
                      xray 进程
```

### 2.4 项目结构

```
kraymini/
├── kraymini/
│   ├── __init__.py
│   ├── __main__.py        # python -m kraymini 入口
│   ├── cli.py             # 命令行解析
│   ├── config.py          # 配置加载与校验
│   ├── subscription.py    # 订阅拉取与解析
│   ├── parser/            # 各协议 URI 解析器
│   │   ├── __init__.py
│   │   ├── vmess.py
│   │   ├── vless.py
│   │   ├── trojan.py
│   │   ├── shadowsocks.py
│   │   └── hysteria.py
│   ├── generator.py       # xray 配置生成
│   ├── process.py         # xray 进程管理
│   └── scheduler.py       # 定时调度
├── tests/
├── pyproject.toml
└── README.md
```

## 3. kraymini 配置设计

kraymini 使用 TOML 格式的配置文件管理自身参数，与 xray 的运行配置分离。kraymini 配置只关注"管什么"（订阅源、端口、落地代理、刷新策略），不包含 xray 原生的路由规则和 DNS 设置——后者通过独立的 xray 模板文件提供。

### 3.1 配置文件搜索路径

kraymini 按以下顺序查找配置文件，**找到第一个即停止**：

1. CLI 参数 `-c <path>`（最高优先级）
2. `./config.toml`（当前工作目录）
3. `~/.kraymini/config.toml`
4. `/usr/local/etc/kraymini/config.toml`
5. `/etc/kraymini/config.toml`

优先级从高到低：命令行指定 > 当前目录 > 用户级 > 系统级。

kraymini 默认使用 `~/.kraymini/` 作为用户级运行时目录，用于存放默认生成的 xray 配置、节点缓存及其他运行时文件。目录不存在时自动创建。

### 3.2 配置结构

#### `[general]` 基础设置

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `xray_bin` | string | 否 | `"xray"` | xray 二进制路径，默认从 PATH 查找 |
| `output_config` | string | 否 | `"~/.kraymini/xray.json"` | 生成的 xray 配置输出路径 |
| `xray_template` | string | 否 | `""` | xray 模板文件路径，为空则不使用模板 |
| `refresh_interval` | integer | 否 | `3600` | 订阅刷新间隔（秒） |

路径类字段在加载时统一执行 `~` 展开并规范化为绝对路径。

#### `[[subscriptions]]` 订阅源列表

TOML 数组表，支持多个订阅源。

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `url` | string | 是 | — | 订阅地址 |
| `name` | string | 否 | `""` | 源标识名，用于日志和节点 tag 前缀 |

至少需要配置一个订阅源，否则启动时报错退出。

#### `[inbound]` 本地服务端口

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `listen` | string | 否 | `"127.0.0.1"` | 三个 inbound 共用的监听地址 |
| `socks_port` | integer | 否 | `10808` | SOCKS5 代理端口 |
| `http_port` | integer | 否 | `10809` | HTTP 代理端口 |
| `api_port` | integer | 否 | `10810` | xray API 端口（dokodemo-door） |
| `sniffing` | boolean | 否 | `true` | 是否开启流量嗅探 |

默认监听地址为 `127.0.0.1`，避免生成未鉴权的开放代理。若需监听其他地址，必须由用户显式配置。

#### `[landing_proxy]` 落地代理（可选）

不配置此段则所有节点直接出站，不经过落地代理。

基础协议字段：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `protocol` | string | 是 | — | 协议：`vmess` / `vless` / `trojan` / `shadowsocks` |
| `address` | string | 是 | — | 落地代理地址 |
| `port` | integer | 是 | — | 落地代理端口 |
| `uuid` | string | 条件 | — | vmess/vless 使用 |
| `password` | string | 条件 | — | trojan/shadowsocks 使用 |
| `method` | string | 条件 | — | shadowsocks 加密方式 |

`[landing_proxy.transport]`（可选，不配置则使用协议默认传输）：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `network` | string | 否 | `"tcp"` | 传输方式：`tcp` / `ws` / `grpc` / `h2` |

`[landing_proxy.transport.ws]`（当 `network = "ws"` 时可用）：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `path` | string | 否 | `"/"` | WebSocket path |
| `host` | string | 否 | `""` | WebSocket `Host` 头 |

`[landing_proxy.transport.grpc]`（当 `network = "grpc"` 时可用）：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `service_name` | string | 否 | `""` | gRPC serviceName |
| `multi_mode` | boolean | 否 | `true` | 是否启用 gRPC 多路复用 |

`[landing_proxy.transport.h2]`（当 `network = "h2"` 时可用）：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `path` | string | 否 | `"/"` | HTTP/2 path |
| `host` | array[string] | 否 | `[]` | HTTP/2 Host 列表 |

`[landing_proxy.security]`（可选，不配置则使用 `none`）：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `mode` | string | 否 | `"none"` | 安全层：`none` / `tls` / `reality` |
| `server_name` | string | 否 | `""` | TLS/Reality 的 SNI / serverName |
| `allow_insecure` | boolean | 否 | `false` | 是否跳过证书校验 |
| `fingerprint` | string | 否 | `"chrome"` | TLS/Reality 指纹伪装 |
| `alpn` | array[string] | 否 | 自动推导 | ALPN 列表；为空时按传输方式自动补全 |

`[landing_proxy.security.reality]`（当 `mode = "reality"` 时必填）：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `public_key` | string | 是 | — | Reality 公钥 |
| `short_id` | string | 否 | `""` | Reality shortId |
| `spider_x` | string | 否 | `"/"` | Reality spiderX |

为避免 TLS `server_name` 与 WebSocket/HTTP2 `Host` 混淆，安全层字段与传输层字段分开定义，不再复用单个 `host` 字段表达多个语义。

#### `[observatory]` 健康检查

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `probe_url` | string | 否 | `"https://www.google.com/generate_204"` | 探测目标 URL |
| `probe_interval` | string | 否 | `"5m"` | 探测间隔 |
| `strategy` | string | 否 | `"leastPing"` | 负载均衡策略 |

#### `[log]` 日志

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `level` | string | 否 | `"info"` | 日志级别：`debug` / `info` / `warning` / `error` |
| `file` | string | 否 | `""` | 日志文件路径，为空则输出到 stderr |

### 3.3 xray 模板文件

独立的 JSON 文件，包含 xray 原生的 routing、dns 及其他静态配置。kraymini 读取模板后，将动态生成的部分合并进去，输出最终的 xray 运行配置。

**模板中由用户维护的部分：**

- `routing.rules` — 路由规则（CN 直连、广告拦截等）
- `dns` — DNS 分流配置
- `policy` — 策略设置
- `stats` — 统计设置

**模板中由 kraymini 自动生成/覆盖的部分：**

- `log` — 由 kraymini `[log].level` 映射为 xray 的 `loglevel`
- `inbounds` — 根据 `[inbound]` 配置生成
- `outbounds` — 根据订阅节点 + 落地代理生成
- `routing.balancers` — 根据节点列表生成 balancer
- `observatory` — 根据 `[observatory]` 配置生成
- `api` — API inbound 配置

合并规则：模板中的 `routing.rules` 保留不动，kraymini 在首部插入 API 路由规则、在末尾追加兜底 balancer 规则。`inbounds`、`outbounds`、`routing.balancers`、`observatory`、`api` 由 kraymini 完全生成，覆盖模板中的同名字段。`direct` 和 `blocked` outbound 由 kraymini 固定生成，无需在模板中定义。

模板**不支持**新增自定义 outbound 并在 `routing.rules` 中引用。换言之，模板中的 `outbounds` 即使存在也不会保留；可用的固定 outbound 只有 kraymini 自动生成的节点 tag、`landing-proxy`（如启用）、`direct`、`blocked`、`api` 与 `balancer`。

### 3.4 默认值策略

kraymini 的设计原则是**最小配置可运行**。一个最简配置只需要：

```toml
[[subscriptions]]
url = "https://example.com/sub?token=xxx"
```

其余字段全部使用默认值。此时 kraymini 会：
- 从 PATH 查找 xray 二进制
- 自动创建 `~/.kraymini/` 运行时目录
- 在 `127.0.0.1:10808`（SOCKS）/ `127.0.0.1:10809`（HTTP）/ `127.0.0.1:10810`（API）启动服务
- 将生成的 xray 配置写入 `~/.kraymini/xray.json`
- 不使用落地代理
- 不加载模板（生成仅含 inbound + outbound + balancer + observatory 的最简 xray 配置）
- 将节点缓存写入 `~/.kraymini/`
- 每 3600 秒刷新一次订阅

### 3.5 配置校验

kraymini 启动时执行以下校验，不通过则报错退出：

- 至少存在一个 `[[subscriptions]]` 且 `url` 非空
- 端口值在 1-65535 范围内，且三个端口互不冲突
- `[inbound].listen` 如指定，必须是合法的监听地址
- `[landing_proxy]` 如存在，`protocol` / `address` / `port` 必填
- `[landing_proxy]` 的凭证字段按协议校验：`vmess` / `vless` 需要 `uuid`；`trojan` 需要 `password`；`shadowsocks` 需要 `password + method`
- `[landing_proxy.transport]` 如存在，`network` 必须属于 `tcp` / `ws` / `grpc` / `h2`
- 当 `network = "ws"` 时，仅使用 `[landing_proxy.transport.ws]`；当 `network = "grpc"` 时，仅使用 `[landing_proxy.transport.grpc]`；当 `network = "h2"` 时，仅使用 `[landing_proxy.transport.h2]`
- `[landing_proxy.security].mode = "reality"` 时，必须提供 `server_name` 和 `[landing_proxy.security.reality].public_key`
- `xray_template` 如指定，文件必须存在且是合法 JSON
- 模板中的 `routing.rules` 不得依赖模板自定义 outbound tag
- `xray_bin` 指定的二进制必须存在且可执行
- 默认运行时目录 `~/.kraymini/` 不存在时自动创建；创建失败则报错退出

同机多实例部署时，必须显式配置不同的 `output_config`、端口和日志路径，避免互相覆盖。

### 3.6 完整配置示例

```toml
[general]
xray_bin = "/usr/local/bin/xray"
output_config = "~/.kraymini/xray.json"
xray_template = "/etc/kraymini/template.json"
refresh_interval = 1800

[[subscriptions]]
url = "https://provider-a.com/sub?token=xxx"
name = "provider-a"

[[subscriptions]]
url = "https://provider-b.com/sub?token=yyy"
name = "provider-b"

[inbound]
listen = "127.0.0.1"
socks_port = 10808
http_port = 10809
api_port = 10810
sniffing = true

[landing_proxy]
protocol = "trojan"
address = "landing.example.com"
port = 443
password = "your-password"

[landing_proxy.transport]
network = "tcp"

[landing_proxy.security]
mode = "tls"
server_name = "landing.example.com"
fingerprint = "chrome"

[observatory]
probe_url = "https://www.google.com/generate_204"
probe_interval = "5m"
strategy = "leastPing"

[log]
level = "info"
file = "~/.kraymini/kraymini.log"
```

## 4. 订阅管理

### 4.1 订阅拉取流程

```
HTTP GET 订阅 URL
    → Base64 解码响应体
    → 按行分割，得到节点 URI 列表
    → 逐条解析 URI 为内部节点数据结构
    → 多源合并 + 去重
    → 缓存到本地
```

多个订阅源按顺序拉取，所有成功的源合并节点列表后统一去重。

### 4.2 支持的协议及 URI 格式

| 协议 | URI 格式 | 备注名来源 |
|------|---------|-----------|
| VMess | `vmess://` + Base64 JSON | JSON 中的 `ps` 字段 |
| VLESS | `vless://uuid@host:port?params#remark` | URL fragment |
| Trojan | `trojan://password@host:port?params#remark` | URL fragment |
| Shadowsocks | `ss://base64@host:port#remark` 或 `ss://base64#remark` | URL fragment |
| Hysteria2 | `hy2://password@host:port?params#remark` | URL fragment |

#### 解析器扩展机制

`parser/` 目录下每个协议一个模块，每个模块需导出一个 `parse(uri: str) -> Node` 函数。`parser/__init__.py` 维护协议前缀到解析函数的注册表：

```python
PARSERS: dict[str, Callable[[str], Node]] = {
    "vmess://": vmess.parse,
    "vless://": vless.parse,
    "trojan://": trojan.parse,
    "ss://": shadowsocks.parse,
    "hy2://": hysteria.parse,
}
```

新增协议步骤：
1. 在 `parser/` 下新建模块（如 `tuic.py`），实现 `parse(uri: str) -> Node`
2. 在 `PARSERS` 注册表中添加 `"tuic://": tuic.parse`
3. 在 `generator.py` 的 outbound 生成逻辑中添加该协议到 xray outbound JSON 的映射

每种协议的 URI 解析为统一的内部数据结构：

```python
@dataclass
class Node:
    raw_uri: str          # 原始 URI，用于去重
    remark: str           # 节点备注名
    protocol: str         # vmess / vless / trojan / ss / hysteria2
    address: str          # 服务器地址
    port: int             # 服务器端口
    credentials: dict     # 协议特定凭证（uuid / password / method 等）
    transport: dict       # 传输层参数（network / security / path / host 等）
    source: str           # 来源订阅名（用于日志）
```

### 4.3 节点命名

xray outbound 的 `tag` 使用节点自带的备注名。如果备注名重复（同源或跨源），追加数字后缀：

```
香港-01          ← 第一个
香港-01_2        ← 重名的第二个
美国-高速        ← 无重名，原样使用
```

备注名为空时，使用 `<source_name>-<序号>` 兜底（如 `provider-a-0`）。

以下为 kraymini 内部保留的 tag 名称，节点备注名与之冲突时自动追加 `_node` 后缀：

- `landing-proxy`
- `direct`
- `blocked`
- `api`
- `balancer`
- `in-api`、`in-socks`、`in-http`

### 4.4 去重策略

以节点的 **完整原始 URI** 作为去重键。相同 URI 出现在多个订阅源时，保留第一个遇到的，后续丢弃。

选择完整 URI 而非 `address + port` 的原因：同一地址端口可能对应不同用户、不同传输配置。

### 4.5 缓存

每次成功拉取并解析后，将合并去重后的节点列表序列化缓存到 `~/.kraymini/` 下。

- 默认配置路径对应的缓存文件为 `~/.kraymini/nodes-cache.json`
- 若通过 `-c` 指定了其他配置文件路径，则缓存文件名派生为 `nodes-cache-<config_sha256_8>.json`，仍存放在 `~/.kraymini/` 下，避免多实例互相污染
- 运行时目录建议权限为 `0700`，缓存文件权限为 `0600`
- 缓存包含节点凭证和传输参数，仅用于本机恢复，不应共享给其他用户或主机

缓存用于以下场景：
- kraymini 重启时避免立即拉取订阅（直接用缓存生成配置，后台再刷新）
- 订阅拉取失败时作为回退

### 4.6 失败处理

| 场景 | 行为 |
|------|------|
| 部分订阅源拉取失败 | 使用成功的源继续，日志记录 WARNING |
| 全部订阅源拉取失败 | 保持当前 xray 配置不变，不重载，日志记录 ERROR |
| 首次启动且无缓存时全部失败 | 报错退出（无可用节点） |
| 拉取成功但解析后节点数为 0 | 视同全部失败，保持现有配置 |

### 4.7 拉取参数

| 参数 | 值 |
|------|-----|
| 超时时间 | 10 秒 |
| 重试次数 | 3 次 |
| 重试间隔 | 指数退避，基数 1 秒（1s → 2s → 4s） |
| User-Agent | 模拟常见客户端 UA，避免被订阅商屏蔽 |

## 5. Xray 配置生成

### 5.1 生成流程

```
读取 kraymini 配置
    → 加载 xray 模板文件（如有）
    → 读取节点列表（从缓存或新拉取）
    → 生成 inbounds
    → 生成 outbounds（节点 + 落地代理 + direct + blocked）
    → 生成 balancer + observatory
    → 合并模板中的 routing.rules / dns / policy / stats
    → 追加兜底路由规则
    → 输出完整 xray JSON 配置
    → 调用 xray run -test 校验
    → 校验通过则写入 output_config 路径
```

### 5.2 inbounds 生成

根据 `[inbound]` 配置固定生成三个 inbound：

| tag | 协议 | 地址来源 | 端口来源 | 说明 |
|-----|------|---------|---------|------|
| `in-api` | dokodemo-door | `listen` | `api_port` | xray API |
| `in-socks` | socks | `listen` | `socks_port` | SOCKS5 代理 |
| `in-http` | http | `listen` | `http_port` | HTTP 代理 |

`in-socks` 和 `in-http` 根据 `sniffing` 配置决定是否开启流量嗅探（`destOverride: ["http", "tls"]`）。

默认 `listen = "127.0.0.1"`，避免生成未鉴权开放代理。若用户需要监听其他地址，必须显式修改配置。

### 5.3 outbounds 生成

outbounds 按以下顺序排列：

1. **订阅节点 outbound** — 每个节点生成一个，tag 使用节点备注名（见 4.3）
2. **落地代理 outbound**（如配置了 `[landing_proxy]`）— tag 固定为 `landing-proxy`
3. **`direct` outbound** — 固定生成，protocol `freedom`，`domainStrategy: "UseIP"`
4. **`blocked` outbound** — 固定生成，protocol `blackhole`

#### 节点 outbound 生成规则

从节点的 `Node` 数据结构转换为 xray outbound JSON。URI 中能解析出的参数直接使用，缺失的传输层参数按以下社区推荐值补全：

**TLS 默认值（当 `security` 为 `tls` 时）：**

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `allowInsecure` | `false` | 不跳过证书验证 |
| `fingerprint` | `"chrome"` | TLS 指纹伪装 |
| `alpn` | 根据传输方式自动选择 | ws/tcp → `["http/1.1"]`，grpc/h2 → `["h2"]` |

**WebSocket 默认值（当 `network` 为 `ws` 时）：**

| 字段 | 默认值 |
|------|--------|
| `headers.User-Agent` | 模拟 Chrome 浏览器 UA |
| `headers.Accept-Encoding` | `"gzip, deflate, br"` |
| `headers.Accept-Language` | `"zh-CN,zh;q=0.9"` |

**gRPC 默认值（当 `network` 为 `grpc` 时）：**
- `multiMode` 默认 `true`（开启多路复用）

#### 落地代理挂载

配置了 `[landing_proxy]` 时，**所有订阅节点** outbound 均添加 `proxySettings`：

```json
{
  "tag": "节点备注名",
  "protocol": "vmess",
  "settings": { ... },
  "streamSettings": { ... },
  "proxySettings": {
    "tag": "landing-proxy",
    "transportLayer": true
  }
}
```

`landing-proxy` 自身的 outbound 由 `[landing_proxy]`、`[landing_proxy.transport.*]` 和 `[landing_proxy.security.*]` 映射生成：安全层的 `server_name` 仅用于 TLS/Reality；WebSocket/HTTP2 的 `Host` 头分别来自对应传输子表，不与安全层字段混用。

流量链路：`客户端 → landing-proxy（第一跳） → 订阅节点（第二跳） → 目标`。

`direct` 和 `blocked` outbound 不挂载落地代理。

### 5.4 routing 生成

路由部分由模板和自动生成两部分合并。

**来自模板的部分（保留不动）：**
- `routing.domainStrategy`
- `routing.domainMatcher`
- `routing.rules` 中用户定义的规则（CN 直连、广告拦截等）

**kraymini 自动生成的部分：**

1. **API 路由规则**（插入到 rules 最前面）：

```json
{
  "type": "field",
  "inboundTag": ["in-api"],
  "outboundTag": "api"
}
```

2. **兜底规则**（追加到 rules 最后面）：

```json
{
  "type": "field",
  "network": "tcp,udp",
  "balancerTag": "balancer"
}
```

3. **balancer**：

```json
{
  "tag": "balancer",
  "selector": ["节点tag-1", "节点tag-2", ...],
  "strategy": {
    "type": "leastPing"
  }
}
```

`selector` 包含所有订阅节点的 tag，`strategy.type` 取自 `[observatory].strategy`。

**无模板时的路由：** 仅生成 API 规则 + 兜底 balancer 规则，不含直连和拦截规则。

### 5.5 observatory 生成

```json
{
  "subjectSelector": ["节点tag-1", "节点tag-2", ...],
  "probeURL": "https://www.google.com/generate_204",
  "probeInterval": "5m"
}
```

`probeURL` 和 `probeInterval` 取自 `[observatory]` 配置。`subjectSelector` 与 balancer 的 `selector` 保持一致。

### 5.6 API 配置

固定生成，用于支持 observatory 和管理：

```json
{
  "tag": "api",
  "services": [
    "HandlerService",
    "LoggerService",
    "StatsService",
    "RoutingService",
    "ObservatoryService"
  ]
}
```

### 5.7 合并与输出

合并优先级：**kraymini 生成的部分覆盖模板中的同名顶层字段**。具体规则：

| 顶层字段 | 来源 |
|---------|------|
| `log` | kraymini `[log].level` 映射为 xray 的 `loglevel` |
| `api` | kraymini 生成 |
| `inbounds` | kraymini 生成 |
| `outbounds` | kraymini 生成 |
| `routing.rules` | 模板规则 + kraymini 在首尾插入自动规则 |
| `routing.balancers` | kraymini 生成 |
| `routing.domainStrategy` | 模板（如有），否则默认 `"IPOnDemand"` |
| `observatory` | kraymini 生成 |
| `dns` | 模板（如有），否则不生成 |
| `policy` | 模板（如有），否则不生成 |
| `stats` | 模板（如有），否则不生成 |

模板中的 `inbounds`、`outbounds`、`api`、`observatory`、`routing.balancers` 均不会保留，`routing.rules` 也不得依赖这些被覆盖掉的模板字段。

### 5.8 配置校验

输出 JSON 前，调用 `xray run -test -c <生成的配置路径>` 校验合法性。

| 校验结果 | 行为 |
|---------|------|
| 通过 | 写入 `output_config` 路径 |
| 失败 | 不写入，保留旧配置，日志记录 ERROR 并附上 xray 的错误输出 |

## 6. 进程管理与调度

### 6.1 进程管理架构

```
外部服务管理器（可选，如 systemd / supervisor / procd）
  └── kraymini（持久服务，长驻运行）
        └── xray（子进程，由 kraymini 启动和管理）
```

外部服务管理器只负责守护 kraymini 进程，并不是 kraymini 的运行前提。kraymini 负责管理 xray 子进程的完整生命周期：启动、监控、重载、停止。

### 6.2 启动流程

```
kraymini 启动
  → 加载并校验配置
  → 优先读取节点缓存（如有）
  → 有缓存：生成 xray 配置 + xray run -test 校验 → 启动 xray 子进程
  → 无缓存：拉取订阅 → 生成 xray 配置 + xray run -test 校验 → 启动 xray 子进程
  → 进入主循环（定时刷新 + 子进程监控）
```

首次启动时如果无缓存且订阅拉取全部失败，kraymini 报错退出（无法生成有效配置）。若通过缓存启动，进入主循环后应尽快执行首轮订阅刷新。

### 6.3 xray 子进程管理

kraymini 通过 `subprocess.Popen` 启动 xray：

```
<xray_bin> run -c <output_config>
```

并持有子进程引用，持续监控其状态。

| 操作 | 实现方式 |
|------|---------|
| 启动 | `subprocess.Popen([xray_bin, "run", "-c", config_path])` |
| 停止 | 发送 `SIGTERM`，等待 5 秒，超时则 `SIGKILL` |
| 重载 | 停止旧进程 → 启动新进程（使用新配置） |
| 状态检查 | `process.poll()` 检查进程是否存活 |

#### 重载流程

```
检测到需要重载（订阅节点变更）
  → xray run -test 校验新配置
  → 校验通过：SIGTERM 停止旧 xray → 启动新 xray
  → 校验失败：保留旧进程和旧配置，日志记录 ERROR
```

重载期间存在短暂的服务中断（旧进程停止到新进程就绪之间）。这在实际使用中通常只有毫秒级，可接受。

### 6.4 子进程异常处理

kraymini 主循环中持续监控 xray 进程状态：

| 场景 | 行为 |
|------|------|
| xray 进程意外退出 | 等待 3 秒后自动重启，日志记录 ERROR |
| 连续崩溃（30 秒内崩溃 3 次） | 停止重启尝试，日志记录 CRITICAL，kraymini 继续运行等待下次订阅刷新后重试 |
| kraymini 收到 SIGTERM/SIGINT | 先停止 xray 子进程，再退出自身 |

### 6.5 定时刷新调度

kraymini 主循环中按 `refresh_interval` 周期执行刷新：

```
等待 refresh_interval 秒
  → 拉取订阅
  → 与当前节点列表比对
  → 有变更：重新生成配置 → 重载 xray
  → 无变更：跳过，继续等待
```

变更判定：将新节点列表的 URI 集合与当前集合比较，有差异则视为变更。

kraymini **只**监听订阅刷新，不监听 kraymini 配置文件或模板文件变化。配置文件和模板文件修改后，需要重启 kraymini 才会生效。

### 6.6 主循环伪代码

```python
POLL_INTERVAL = 5
CRASH_WINDOW = 30
MAX_CRASHES = 3

def main_loop():
    config = load_config()
    nodes, loaded_from_cache = load_cache_or_fetch(config)
    xray_config = generate_xray_config(config, nodes)
    xray_proc = start_xray(xray_config)
    last_refresh = 0 if loaded_from_cache else time.time()
    crash_times: list[float] = []

    while True:
        sleep(POLL_INTERVAL)

        if xray_proc.poll() is not None:
            now = time.time()
            crash_times = [t for t in crash_times if now - t < CRASH_WINDOW]
            crash_times.append(now)

            if len(crash_times) >= MAX_CRASHES:
                log.critical("xray 连续崩溃 %d 次，暂停重启", MAX_CRASHES)
            else:
                log.error("xray 意外退出，3 秒后重启")
                sleep(3)
                xray_proc = start_xray(xray_config)

        if time.time() - last_refresh < config.refresh_interval:
            continue

        last_refresh = time.time()
        crash_times.clear()  # 新一轮刷新，重置崩溃计数
        new_nodes = fetch_subscriptions(config)
        if new_nodes is None:
            continue

        if nodes_changed(nodes, new_nodes):
            nodes = new_nodes
            new_config = generate_xray_config(config, nodes)
            if validate_xray_config(new_config):
                xray_proc = reload_xray(xray_proc, new_config)
                xray_config = new_config
```

### 6.7 信号处理

| 信号 | 行为 |
|------|------|
| `SIGTERM` | 优雅关闭：停止 xray 子进程 → kraymini 退出 |
| `SIGINT` | 同 SIGTERM |

### 6.8 supervisor 配置示例（部署示例）

```ini
[program:kraymini]
command = /usr/bin/python3 -m kraymini run -c /etc/kraymini/config.toml
autostart = true
autorestart = true
startsecs = 5
startretries = 3
stopwaitsecs = 10
redirect_stderr = true
stdout_logfile = /var/log/kraymini/supervisor.log
```

`stopwaitsecs` 设为 10 秒，给 kraymini 足够时间停止 xray 子进程后再退出。若运行在 systemd 或 OpenWrt procd 下，可按各自服务管理器的方式做等价配置。

## 7. CLI 设计

### 7.1 命令风格

kraymini 使用子命令风格的 CLI 接口：

```
kraymini <command> [options]
```

### 7.2 子命令列表

#### `kraymini run`

长驻运行模式。拉取订阅、生成配置、启动 xray、进入主循环。

```
kraymini run [-c <config_path>]
```

| 参数 | 说明 |
|------|------|
| `-c, --config` | 指定配置文件路径，不指定则按搜索路径查找 |

这是 kraymini 的主命令，通常由外部服务管理器或用户手动启动。

#### `kraymini genconfig`

仅生成 xray 配置文件，不启动 xray 进程。用于调试和验证。

```
kraymini genconfig [-c <config_path>] [-o <output_path>]
```

| 参数 | 说明 |
|------|------|
| `-c, --config` | 指定 kraymini 配置文件路径 |
| `-o, --output` | 输出路径，不指定则使用配置中的 `output_config`；指定为 `-` 则输出到 stdout |

流程：加载配置 → 拉取订阅（或使用缓存） → 生成 xray 配置 → `xray run -test` 校验 → 输出。不启动 xray，执行完即退出。

| 参数 | 说明 |
|------|------|
| `--offline` | 跳过订阅拉取，仅使用 `~/.kraymini/` 下的本地缓存生成配置。缓存不存在时报错退出 |

#### `kraymini check`

校验 kraymini 配置文件的合法性。

```
kraymini check [-c <config_path>]
```

校验内容同 3.5 节。通过则输出 `OK` 并以 exit code 0 退出，失败则输出错误信息并以 exit code 1 退出。

#### `kraymini version`

输出版本信息。

```
kraymini version
```

输出格式：

```
kraymini 0.1.0
```

### 7.3 全局参数

| 参数 | 说明 |
|------|------|
| `-c, --config` | 所有子命令共享，指定配置文件路径 |
| `-v, --verbose` | 提高日志输出级别至 DEBUG |
| `-h, --help` | 显示帮助信息 |

### 7.4 退出码

| 退出码 | 含义 |
|-------|------|
| 0 | 正常退出 |
| 1 | 配置错误（解析失败、校验不通过） |
| 2 | 运行时错误（订阅全部失败且无缓存、xray 二进制不存在等） |

### 7.5 实现

使用 Python 标准库 `argparse` 实现，不引入额外 CLI 框架依赖。

## 8. 验收与测试矩阵

### 8.1 测试层次

| 层次 | 目标 | 典型对象 |
|------|------|---------|
| 单元测试 | 校验纯逻辑与边界条件 | 配置解析、URI 解析、去重、命名、模板合并 |
| 集成测试 | 校验模块协作 | 订阅拉取 + 缓存、生成配置 + `xray run -test`、进程重载 |
| 端到端验收 | 校验可交付行为 | `run` / `genconfig` / `check` 命令、定时刷新、崩溃恢复 |

集成测试中建议使用本地 mock HTTP 服务模拟订阅源，使用可替换的假 xray 二进制模拟 `run -test` 和运行态进程，避免依赖真实网络环境。

### 8.2 功能验收矩阵

| 编号 | 场景 | 类型 | 预期结果 |
|------|------|------|---------|
| A01 | 仅配置一个订阅 URL 的最简配置启动 | 端到端 | 自动创建 `~/.kraymini/`，生成 `xray.json`，默认监听 `127.0.0.1`，成功启动 xray |
| A02 | 配置文件搜索路径优先级 | 单元/集成 | `-c` > `./config.toml` > `~/.kraymini/config.toml` > `/usr/local/etc/kraymini/config.toml` > `/etc/kraymini/config.toml` |
| A03 | 非法端口、冲突端口、非法监听地址 | 单元 | `check` 失败并返回 exit code 1 |
| A04 | `landing_proxy` 缺少协议必填字段 | 单元 | 配置校验失败并给出明确错误信息 |
| A05 | `landing_proxy` 的 `ws` / `grpc` / `h2` / `tls` / `reality` 配置映射 | 单元/集成 | 生成的 outbound JSON 与配置语义一致，`server_name` 与各类 `Host` 字段不混淆 |
| A06 | 多订阅源合并与按原始 URI 去重 | 单元 | 相同 URI 仅保留首个节点，不同 URI 即使地址端口相同也保留 |
| A07 | 节点重名、空备注、保留 tag 冲突 | 单元 | 自动追加序号、生成兜底名称或追加 `_node` 后缀 |
| A08 | 部分订阅源失败 | 集成 | 使用成功源继续生成节点并记录 WARNING |
| A09 | 全部订阅失败但本地有缓存 | 集成 | 保持当前 xray 配置和进程不变，不重载 |
| A10 | 首次启动全部订阅失败且无缓存 | 端到端 | 启动失败并返回运行时错误 exit code 2 |
| A11 | `genconfig --offline` 且缓存存在 | 端到端 | 仅使用 `~/.kraymini/` 缓存生成并校验配置，不访问网络 |
| A12 | 模板合并保留 `routing.rules` / `dns` / `policy` / `stats` | 集成 | 这些字段按规则保留，自动生成字段覆盖同名模板字段 |
| A13 | 模板引用自定义 outbound tag | 单元/集成 | 校验失败，明确提示模板不支持自定义 outbound |
| A14 | 节点集合无变化的定时刷新 | 集成 | 不重写配置、不重载 xray |
| A15 | 节点集合有变化的定时刷新 | 集成 | 重新生成配置，通过校验后重载 xray |
| A16 | xray 子进程异常退出 | 集成 | 3 秒后自动重启；达到连续崩溃阈值后暂停重启并记录 CRITICAL |
| A17 | `SIGTERM` / `SIGINT` 终止 | 端到端 | 优雅停止 xray 后退出 kraymini |

### 8.3 平台验收要求

| 平台 | 最低要求 |
|------|---------|
| Linux | 通过全部单元测试、集成测试和端到端验收 |
| macOS | 通过全部单元测试与主要端到端验收 |
| OpenWrt | 至少完成启动、订阅刷新、配置生成和进程托管的冒烟验证 |
