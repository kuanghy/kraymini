from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .log import logger


STOP_TIMEOUT = 5


class XrayError(Exception):
    pass


class XrayProcess:
    def __init__(self, xray_bin: str = "xray"):
        self.xray_bin = xray_bin
        self._process: subprocess.Popen | None = None
        self._log_fh = None

    def _resolve_bin(self) -> str:
        path = Path(self.xray_bin)
        if path.is_absolute():
            if not path.exists():
                raise XrayError(f"xray 二进制不存在: {self.xray_bin}")
            return str(path)
        resolved = shutil.which(self.xray_bin)
        if resolved is None:
            raise XrayError(f"xray 二进制不存在: 在 PATH 中找不到 {self.xray_bin!r}")
        return resolved

    def check_available(self) -> bool:
        try:
            bin_path = self._resolve_bin()
        except XrayError as e:
            logger.error("%s", e)
            return False

        try:
            result = subprocess.run(
                [bin_path, "version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            logger.error("检查 xray 可用性超时: %s", bin_path)
            return False
        except OSError as e:
            logger.error("执行 xray 失败: %s", e)
            return False

        version_output = (result.stdout or result.stderr).strip()
        if result.returncode != 0:
            logger.error("xray 不可用: %s", version_output or bin_path)
            return False

        if version_output:
            version_line = version_output.splitlines()[0]
            logger.info("xray 可用: %s", version_line)
        else:
            logger.info("xray 可用: %s", bin_path)
        return True

    def validate_config(self, config_path: str) -> bool:
        try:
            bin_path = self._resolve_bin()
        except XrayError:
            logger.error("xray 二进制不可用，跳过配置校验")
            return False
        try:
            result = subprocess.run(
                [bin_path, "run", "-test", "-c", config_path],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                logger.info("xray 配置校验通过: %s", config_path)
                return True
            else:
                logger.error("xray 配置校验失败: %s\n%s", config_path, result.stderr)
                return False
        except subprocess.TimeoutExpired:
            logger.error("xray 配置校验超时: %s", config_path)
            return False

    def start(self, config_path: str, log_file: str = "") -> None:
        bin_path = self._resolve_bin()
        self._close_log_fh()
        popen_kwargs: dict = {}
        if log_file:
            self._log_fh = open(log_file, "a", encoding="utf-8")
            popen_kwargs["stdout"] = self._log_fh
            popen_kwargs["stderr"] = subprocess.STDOUT
        self._process = subprocess.Popen([bin_path, "run", "-c", config_path], **popen_kwargs)
        logger.info("xray 已启动 (PID=%d): %s", self._process.pid, config_path)

    def _close_log_fh(self) -> None:
        if self._log_fh is not None:
            self._log_fh.close()
            self._log_fh = None

    def stop(self) -> None:
        if self._process is None:
            self._close_log_fh()
            return
        if self._process.poll() is not None:
            self._process = None
            self._close_log_fh()
            return
        logger.info("正在停止 xray (PID=%d)...", self._process.pid)
        self._process.terminate()
        try:
            self._process.wait(timeout=STOP_TIMEOUT)
        except subprocess.TimeoutExpired:
            logger.warning("xray 未在 %ds 内退出，发送 SIGKILL", STOP_TIMEOUT)
            self._process.kill()
            self._process.wait()
        self._process = None
        self._close_log_fh()

    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    def reload(self, config_path: str, log_file: str = "") -> None:
        self.stop()
        self.start(config_path, log_file)
        logger.info("xray 已重载")

    @property
    def pid(self) -> int | None:
        if self._process and self._process.poll() is None:
            return self._process.pid
        return None

    @property
    def returncode(self) -> int | None:
        if self._process is None:
            return None
        return self._process.poll()
