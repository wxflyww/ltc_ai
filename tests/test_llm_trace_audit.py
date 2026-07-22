from pathlib import Path

from app.core.config import _reset_settings
from app.core.llm_trace_audit import add_event, finish_request, start_request


def test_llm_trace_audit_writes_html_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LTC_ENV", "dev")
    monkeypatch.setenv("LTC__DEBUG__LLM_TRACE", "true")
    monkeypatch.setenv("LTC__DEBUG__LLM_TRACE_WRITE_HTML", "true")
    monkeypatch.setenv("LTC__DEBUG__LLM_TRACE_OUTPUT_DIR", str(tmp_path))
    _reset_settings()

    start_request("trace-abcdef123456", "/api/v1/contract-review/upload-md")
    add_event({
        "event": "invoke_json_prompt_response",
        "prompt_name": "b4_attachment_content",
        "label": "B-4-附件一.md",
        "content": '{"checks":[{"result":"PASS","block_level":"通过","reason":"一致"}]}',
    })

    output = finish_request(status_code=200, duration_seconds=0.321)
    assert output is not None

    html = Path(output).read_text(encoding="utf-8")
    assert "LLM Trace Audit" in html
    assert "b4_attachment_content" in html
    assert "trace-abcdef123456" in html



def test_llm_trace_audit_skips_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("LTC_ENV", "dev")
    monkeypatch.setenv("LTC__DEBUG__LLM_TRACE", "false")
    monkeypatch.setenv("LTC__DEBUG__LLM_TRACE_WRITE_HTML", "true")
    monkeypatch.setenv("LTC__DEBUG__LLM_TRACE_OUTPUT_DIR", str(tmp_path))
    _reset_settings()

    start_request("trace-disabled", "/api/v1/contract-review")
    add_event({"event": "invoke_json_prompt_response", "prompt_name": "b4_attachment_content"})

    output = finish_request(status_code=200, duration_seconds=0.123)
    assert output is None
    assert list(tmp_path.iterdir()) == []
