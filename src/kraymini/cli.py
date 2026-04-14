from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

from . import __version__
from .config import find_config, load_config, ConfigError
from .log import setup_logging, logger


def _add_common_cli_args(ap: argparse.ArgumentParser, *, for_subparser: bool = False) -> None:
    """根解析器与各子解析器均注册

    子解析器上使用 ``argparse.SUPPRESS``，避免在未重复书写全局参数时，
    用 ``None``/``False`` 覆盖根解析器结果
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


def cmd_check(config_path: str | None) -> int:
    try:
        path = find_config(config_path)
        load_config(path)
        print("OK")
        return 0
    except ConfigError as e:
        print(f"配置校验失败: {e}", file=sys.stderr)
        return 1


def cmd_version() -> int:
    print(f"kraymini {__version__}")
    return 0


def cmd_genconfig(config_path: str | None, output: str | None, offline: bool) -> int:
    try:
        path = find_config(config_path)
        cfg = load_config(path)
    except ConfigError as e:
        print(f"配置错误: {e}", file=sys.stderr)
        return 1

    setup_logging(level=cfg.log.level, log_file=cfg.log.file)

    from .subscription import SubscriptionManager, load_cache, get_cache_path
    from .generator import generate_xray_config, write_xray_config
    from .process import XrayProcess

    runtime_dir = str(Path(cfg.general.output_config).parent)
    Path(runtime_dir).expanduser().mkdir(parents=True, exist_ok=True)
    xray = XrayProcess(cfg.general.xray_bin)

    if offline:
        cache_path = get_cache_path(str(path), runtime_dir)
        nodes = load_cache(cache_path)
        if nodes is None:
            print("离线模式: 缓存不存在", file=sys.stderr)
            return 2
    else:
        if not xray.check_available():
            logger.error("xray 不可用，停止订阅拉取")
            return 2
        mgr = SubscriptionManager(cfg, str(path), runtime_dir=runtime_dir)
        nodes = mgr.refresh()
        if not nodes:
            print("订阅拉取失败且无可用缓存", file=sys.stderr)
            return 2

    xray_config = generate_xray_config(cfg, nodes)

    if output == "-":
        print(json.dumps(xray_config, indent=2, ensure_ascii=False))
    else:
        out_path = output or cfg.general.output_config
        written = write_xray_config(xray_config, out_path)
        if xray.validate_config(written):
            logger.info("配置已生成并校验通过: %s", written)
        else:
            logger.error("配置已生成但校验失败: %s", written)
            return 2

    return 0


def cmd_run(config_path: str | None) -> int:
    try:
        path = find_config(config_path)
        cfg = load_config(path)
    except ConfigError as e:
        print(f"配置错误: {e}", file=sys.stderr)
        return 1

    setup_logging(level=cfg.log.level, log_file=cfg.log.file)
    logger.info("Kraymini version %s, using Python %s",
                __version__, platform.python_version())

    runtime_dir = str(Path(cfg.general.output_config).parent)
    Path(runtime_dir).expanduser().mkdir(parents=True, exist_ok=True)

    from .scheduler import Daemon
    daemon = Daemon(cfg, str(path))
    daemon.run()
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    verbose = bool(getattr(args, "verbose", False))
    config_path = getattr(args, "config", None)

    if verbose:
        setup_logging(level="debug")

    if args.command == "version":
        sys.exit(cmd_version())
    elif args.command == "check":
        sys.exit(cmd_check(config_path))
    elif args.command == "genconfig":
        sys.exit(cmd_genconfig(config_path, args.output, args.offline))
    elif args.command == "run":
        sys.exit(cmd_run(config_path))
    else:
        parser.print_help()
        sys.exit(1)
