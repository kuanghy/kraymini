# kraymini

Xray 服务管理器：从订阅源自动拉取代理节点，生成带负载均衡和健康检查的 Xray 配置，并管理 Xray 进程生命周期。

## 安装

```bash
pip install -e .
```

## 快速开始

创建最简配置文件 `config.toml`：

```toml
[[subscriptions]]
url = "https://your-provider.com/sub?token=xxx"
```

启动服务：

```bash
kraymini run -c config.toml
```

## 命令

- `kraymini run` — 长驻运行模式
- `kraymini genconfig` — 仅生成配置文件
- `kraymini nodes` — 查看当前缓存节点，可加 `--refresh` 在线刷新
- `kraymini check` — 校验配置文件
- `kraymini version` — 输出版本信息

## 部署示例

- `deploy/kraymini.supervisor.conf`
- `deploy/kraymini.service`
