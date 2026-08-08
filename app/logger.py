"""
File: logger.py
Chức năng: Cấu hình logging có cấu trúc dùng chung toàn backend
Vai trò: Util - cung cấp get_logger(), cấm dùng print() trong code production
File liên quan: app/config.py, utils/logs/app.log
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import DIR_ROOT, settings

LOG_DIR = DIR_ROOT / "utils" / "logs"


def get_logger(name: str) -> logging.Logger:
    """
    Trả về logger có cấu trúc: ghi cả console lẫn file (rotating 5MB x 3).

    Logic:
      - Nếu logger đã có handler (gọi nhiều lần) thì trả về ngay, tránh log trùng
      - ENV=development bật DEBUG, còn lại INFO
      - Formatter ghi timestamp, tên module, mức độ để dễ trace
      - RotatingFileHandler tự xoay file cũ khi vượt 5MB, giữ 3 file backup
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    level = logging.DEBUG if settings.ENV == "development" else logging.INFO
    logger.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s | %(name)-30s | %(levelname)-8s | %(message)s"
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_DIR / "app.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger
