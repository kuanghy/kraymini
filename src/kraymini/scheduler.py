from __future__ import annotations

import os
import select
import signal
import sys
import time
from pathlib import Path

from .config import KrayminiConfig
from .generator import generate_xray_config, write_xray_config
from .log import logger
from .models import Node
from .process import XrayProcess
from .subscription import SubscriptionManager


POLL_INTERVAL = 5
CRASH_RESTART_DELAY = 3


class CrashMonitor:
    def __init__(self, max_crashes: int = 3, crash_window: float = 30):
        self.max_crashes = max_crashes
        self.crash_window = crash_window
        self._crash_times: list[float] = []
        self.is_suspended = False

    def record_crash(self) -> None:
        now = time.time()
        self._crash_times = [t for t in self._crash_times if now - t < self.crash_window]
        self._crash_times.append(now)
        if len(self._crash_times) >= self.max_crashes:
            self.is_suspended = True

    def reset(self) -> None:
        self._crash_times.clear()
        self.is_suspended = False


class Daemon:
    def __init__(self, config: KrayminiConfig, config_path: str):
        self.config = config
        self.config_path = config_path
        runtime_dir = str(Path(config.general.output_config).parent)
        self.sub_mgr = SubscriptionManager(config, config_path, runtime_dir=runtime_dir)
        self.xray = XrayProcess(config.general.xray_bin)
        self.crash_monitor = CrashMonitor()
        self.current_nodes: list[Node] | None = None
        self._force_refresh = False
        self._running = True
        self._pipe_r, self._pipe_w = os.pipe()
        os.set_blocking(self._pipe_r, False)
        os.set_blocking(self._pipe_w, False)

    def _wakeup(self) -> None:
        try:
            os.write(self._pipe_w, b"\x00")
        except OSError:
            pass

    def _drain_pipe(self) -> None:
        try:
            os.read(self._pipe_r, 1024)
        except OSError:
            pass

    def _close_pipe(self) -> None:
        for fd in (self._pipe_r, self._pipe_w):
            try:
                os.close(fd)
            except OSError:
                pass

    def _wait(self, timeout: float) -> None:
        """可被信号立即唤醒的等待"""
        select.select([self._pipe_r], [], [], timeout)
        self._drain_pipe()

    def _check_xray_before_subscription(self, *, exit_on_fail: bool) -> bool:
        if self.xray.check_available():
            return True

        if exit_on_fail:
            logger.critical("xray 不可用，停止订阅拉取")
            sys.exit(2)

        logger.error("xray 不可用，跳过本次订阅刷新")
        return False

    def initial_start(self) -> None:
        self._check_xray_before_subscription(exit_on_fail=True)
        nodes = self.sub_mgr.refresh()
        if not nodes:
            logger.critical("订阅拉取失败且无可用缓存，无法生成配置")
            sys.exit(2)
        self.current_nodes = nodes
        xray_config = generate_xray_config(self.config, nodes)
        config_path = write_xray_config(xray_config, self.config.general.output_config)
        if not self.xray.validate_config(config_path):
            logger.critical("xray 配置校验失败，无法启动")
            sys.exit(2)
        self.xray.start(config_path, log_file=self.config.log.file)

    def _do_refresh(self) -> None:
        if not self._check_xray_before_subscription(exit_on_fail=False):
            return
        new_nodes = self.sub_mgr.refresh()
        if not new_nodes:
            logger.error("订阅拉取失败或无有效节点，保持当前配置继续运行")
            return
        if (
            not self.sub_mgr.nodes_changed(self.current_nodes, new_nodes)
            and not self.crash_monitor.is_suspended
        ):
            logger.info("节点列表无变化，跳过重载")
            return
        self.current_nodes = new_nodes
        xray_config = generate_xray_config(self.config, new_nodes)
        config_path = write_xray_config(xray_config, self.config.general.output_config)
        if not self.xray.validate_config(config_path):
            logger.error("新配置校验失败，保留旧配置和旧进程")
            tmp = Path(config_path).with_suffix(".tmp")
            if tmp.exists():
                tmp.unlink()
            return
        self.xray.reload(config_path, log_file=self.config.log.file)
        self.crash_monitor.reset()
        logger.info("xray 配置已重载")

    def run(self) -> None:
        self._setup_signals()
        self.initial_start()
        last_refresh = time.time()
        while self._running:
            self._wait(POLL_INTERVAL)
            if not self._running:
                break
            if not self.crash_monitor.is_suspended and not self.xray.is_running():
                self.crash_monitor.record_crash()
                if self.crash_monitor.is_suspended:
                    logger.critical(
                        "xray 连续崩溃 %d 次，暂停重启，等待下次订阅刷新",
                        self.crash_monitor.max_crashes,
                    )
                else:
                    logger.error("xray 意外退出，%ds 后重启", CRASH_RESTART_DELAY)
                    self._wait(CRASH_RESTART_DELAY)
                    if not self._running:
                        break
                    self.xray.start(
                        self.config.general.output_config,
                        log_file=self.config.log.file,
                    )
            need_refresh = self._force_refresh or (
                time.time() - last_refresh >= self.config.general.refresh_interval
            )
            if not need_refresh:
                continue
            self._force_refresh = False
            last_refresh = time.time()
            self._do_refresh()
        self.xray.stop()
        self._close_pipe()
        logger.info("kraymini 已停止")

    def shutdown(self) -> None:
        """停止 daemon（供外部调用）"""
        self._running = False
        self._wakeup()
        self.xray.stop()
        logger.info("kraymini 已停止")

    def _setup_signals(self) -> None:
        signal.set_wakeup_fd(self._pipe_w)

        def handle_term(signum, frame):
            logger.info("收到 %s 信号，正在停止...", signal.Signals(signum).name)
            self._running = False

        def handle_hup(signum, frame):
            logger.info("收到 SIGHUP，触发立即刷新")
            self._force_refresh = True

        signal.signal(signal.SIGTERM, handle_term)
        signal.signal(signal.SIGINT, handle_term)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, handle_hup)
