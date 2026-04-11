from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import kraymini
from kraymini.config import find_config, load_config, ConfigError
from kraymini.log import setup_logging, logger


def _add_common_cli_args(ap: argparse.ArgumentParser, *, for_subparser: bool = False) -> None:
    """根解析器与各子解析器均注册，以支持 ``kraymini -c x run`` 与 ``kraymini run -c x``。

    子解析器上使用 ``argparse.SUPPRESS``，避免在未重复书写全局参数时用 ``None``/``False`` 覆盖根解析器结果。
    """
    if for_subparser:
        ap.add_argument("-c", "--config", help="配置文件路径", default=argparse.SUPPRESS)
        ap.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="启用 DEBUG 日志",
            default=argparse.SUPPRESS,
        )
    else:
        ap.add_argument("-c", "--config", help="配置文件路径", default=None)
        ap.add_argument("-v", "--verbose", action="store_true", help="启用 DEBUG 日志")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kraymini", description="Xray 服务管理器")
    _add_common_cli_args(parser)

    subparsers = parser.add_subparsers(dest="command")
    run_p = subparsers.add_parser("run", help="长驻运行模式")
    _add_common_cli_args(run_p, for_subparser=True)

    genconfig = subparsers.add_parser("genconfig", help="仅生成 xray 配置")
    _add_common_cli_args(genconfig, for_subparser=True)
    genconfig.add_argument("-o", "--output", help="输出路径，- 表示 stdout", default=None)
    genconfig.add_argument("--offline", action="store_true", help="跳过订阅拉取，仅使用缓存")

    check_p = subparsers.add_parser("check", help="校验配置文件")
    _add_common_cli_args(check_p, for_subparser=True)

    ver_p = subparsers.add_parser("version", help="输出版本信息")
    _add_common_cli_args(ver_p, for_subparser=True)

    return parser


def cmd_check(config_path: str | None) -> None:
    try:
        path = find_config(config_path)
        load_config(path)
        print("OK")
        sys.exit(0)
    except ConfigError as e:
        print(f"配置校验失败: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_version() -> None:
    print(f"kraymini {kraymini.__version__}")
    sys.exit(0)


def cmd_genconfig(config_path: str | None, output: str | None, offline: bool) -> None:
    try:
        path = find_config(config_path)
        cfg = load_config(path)
    except ConfigError as e:
        print(f"配置错误: {e}", file=sys.stderr)
        sys.exit(1)

    setup_logging(level=cfg.log.level, log_file=cfg.log.file)

    from kraymini.subscription import SubscriptionManager, load_cache, get_cache_path
    from kraymini.generator import generate_xray_config, write_xray_config
    from kraymini.process import XrayProcess

    runtime_dir = str(Path(cfg.general.output_config).parent)
    Path(runtime_dir).expanduser().mkdir(parents=True, exist_ok=True)

    if offline:
        cache_path = get_cache_path(str(path), runtime_dir)
        nodes = load_cache(cache_path)
        if nodes is None:
            print("离线模式: 缓存不存在", file=sys.stderr)
            sys.exit(2)
    else:
        mgr = SubscriptionManager(cfg, str(path), runtime_dir=runtime_dir)
        nodes = mgr.refresh()
        if nodes is None or len(nodes) == 0:
            print("订阅拉取失败且无可用缓存", file=sys.stderr)
            sys.exit(2)

    xray_config = generate_xray_config(cfg, nodes)

    if output == "-":
        print(json.dumps(xray_config, indent=2, ensure_ascii=False))
    else:
        out_path = output or cfg.general.output_config
        written = write_xray_config(xray_config, out_path)
        xray = XrayProcess(cfg.general.xray_bin)
        if xray.validate_config(written):
            logger.info("配置已生成并校验通过: %s", written)
        else:
            logger.error("配置已生成但校验失败: %s", written)
            sys.exit(2)

    sys.exit(0)


def cmd_run(config_path: str | None) -> None:
    try:
        path = find_config(config_path)
        cfg = load_config(path)
    except ConfigError as e:
        print(f"配置错误: {e}", file=sys.stderr)
        sys.exit(1)

    setup_logging(level=cfg.log.level, log_file=cfg.log.file)

    runtime_dir = str(Path(cfg.general.output_config).parent)
    Path(runtime_dir).expanduser().mkdir(parents=True, exist_ok=True)

    from kraymini.scheduler import KrayminiDaemon
    daemon = KrayminiDaemon(cfg, str(path))
    daemon.run()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    verbose = bool(getattr(args, "verbose", False))
    config_path = getattr(args, "config", None)

    if verbose:
        setup_logging(level="debug")

    if args.command == "version":
        cmd_version()
    elif args.command == "check":
        cmd_check(config_path)
    elif args.command == "genconfig":
        cmd_genconfig(config_path, args.output, args.offline)
    elif args.command == "run":
        cmd_run(config_path)
    else:
        parser.print_help()
        sys.exit(1)
