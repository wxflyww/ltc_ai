"""结构化 JSON 日志，注入 traceId。"""
import logging
import sys
from contextvars import ContextVar

from pythonjsonlogger.json import JsonFormatter

_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s %(traceId)s %(endpoint)s %(duration_seconds)s %(llm_duration_seconds)s"

# pythonjsonlogger v4 用 LogRecord 标准字段名（asctime/levelname），
# 通过 rename_fields 输出为 timestamp/level，避免与保留属性冲突。
_RENAME = {"asctime": "timestamp", "levelname": "level"}


class _ContextFilter(logging.Filter):
    """把 contextvar 注入到每条日志的 record。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.traceId = _trace_id_var.get()
        if not hasattr(record, "endpoint"):
            record.endpoint = ""
        if not hasattr(record, "duration_seconds"):
            record.duration_seconds = ""
        if not hasattr(record, "llm_duration_seconds"):
            record.llm_duration_seconds = ""
        return True


def setup_logging(level: str = "INFO", stream=None) -> None:
    """配置根 logger 输出 JSON。"""
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter(_FORMAT, rename_fields=_RENAME))
    handler.addFilter(_ContextFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


def get_logger(name: str = "ltc_ai") -> logging.Logger:
    return logging.getLogger(name)


def bind_trace_id(trace_id: str) -> None:
    _trace_id_var.set(trace_id)


def clear_trace_id() -> None:
    _trace_id_var.set("")
