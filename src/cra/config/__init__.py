"""日志配置：基于 structlog 的结构化日志。"""

from __future__ import annotations

import logging
import sys

import structlog


def setup_logging(level: str = "INFO", fmt: str = "console") -> None:
    """配置结构化日志。

    Args:
        level: 日志级别（DEBUG/INFO/WARNING/ERROR）
        fmt: 格式（console=人类可读 / json=机器可读）
    """
    # 标准 logging 配置
    logging.basicConfig(
        level=level,
        stream=sys.stderr,
        format="%(message)s",
    )

    timestamper = structlog.processors.TimeStamper(fmt="iso")

    if fmt == "json":
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            timestamper,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ]
    else:
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            timestamper,
            structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """获取 logger。"""
    return structlog.get_logger(name)
