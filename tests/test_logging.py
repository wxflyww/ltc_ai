import io
import json

from app.core.logging import setup_logging, get_logger, bind_trace_id, clear_trace_id


def test_log_json_contains_trace_id():
    stream = io.StringIO()
    setup_logging("INFO", stream)
    bind_trace_id("trace-abc")
    logger = get_logger()
    logger.info("hello", extra={"endpoint": "/api/v1/translate", "duration_seconds": 0.5})
    clear_trace_id()
    line = stream.getvalue().strip().splitlines()[-1]
    obj = json.loads(line)
    assert obj["message"] == "hello"
    assert obj["traceId"] == "trace-abc"
    assert obj["endpoint"] == "/api/v1/translate"
    assert obj["duration_seconds"] == 0.5
    assert "timestamp" in obj
    assert obj["level"] == "INFO"


def test_log_without_trace_id():
    stream = io.StringIO()
    setup_logging("INFO", stream)
    clear_trace_id()
    logger = get_logger()
    logger.info("no trace")
    obj = json.loads(stream.getvalue().strip())
    assert obj["traceId"] == ""
