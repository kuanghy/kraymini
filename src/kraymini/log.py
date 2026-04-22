import logging
import sys
from datetime import datetime


LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

logger = logging.getLogger("kraymini")


class _MicrosecondFormatter(logging.Formatter):
    """时间戳输出到微秒"""

    def formatTime(self, record, datefmt=None):  # noqa: D401 - 父类签名
        fmt = datefmt or LOG_DATE_FORMAT
        return datetime.fromtimestamp(record.created).strftime(fmt)


def setup_logging(level: str = "info", log_file: str = "") -> None:
    log_level = LEVEL_MAP.get(level.lower(), logging.INFO)
    logger.setLevel(log_level)
    logger.handlers.clear()

    formatter = _MicrosecondFormatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    if log_file:
        handler = logging.FileHandler(log_file, encoding="utf-8")
    else:
        handler = logging.StreamHandler(sys.stdout)

    handler.setFormatter(formatter)
    logger.addHandler(handler)
