"""LLM 调试事件审计：按请求缓冲事件并可落盘为 HTML。"""
from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime
from html import escape
import json
from pathlib import Path
from threading import Lock
import uuid

from app.core.config import get_settings


_REQUEST_META: ContextVar[dict] = ContextVar("llm_trace_request_meta", default={})
_REQUEST_STORE_LOCK = Lock()
_REQUEST_STORE: dict[str, dict] = {}

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def start_request(trace_id: str, endpoint: str) -> None:
    """初始化当前请求的审计上下文。"""
    request_key = uuid.uuid4().hex
    meta = {
        "request_key": request_key,
        "trace_id": trace_id,
        "endpoint": endpoint,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    _REQUEST_META.set(meta)
    with _REQUEST_STORE_LOCK:
        _REQUEST_STORE[request_key] = {
            "meta": meta,
            "events": [],
        }


def add_event(payload: dict) -> None:
    """向当前请求写入一条结构化事件。"""
    if not payload:
        return
    meta = dict(_REQUEST_META.get())
    request_key = str(meta.get("request_key", "")).strip()
    if not request_key:
        return

    event = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "payload": payload,
    }
    with _REQUEST_STORE_LOCK:
        bucket = _REQUEST_STORE.get(request_key)
        if not bucket:
            bucket = {
                "meta": meta,
                "events": [],
            }
            _REQUEST_STORE[request_key] = bucket
        bucket["events"].append(event)


def finish_request(status_code: int, duration_seconds: float) -> str | None:
    """结束请求并按配置落盘 HTML，返回写入路径（若有）。"""
    settings = get_settings()
    context_meta = dict(_REQUEST_META.get())
    request_key = str(context_meta.get("request_key", "")).strip()
    if request_key:
        with _REQUEST_STORE_LOCK:
            bucket = _REQUEST_STORE.pop(request_key, None)
    else:
        bucket = None

    meta = dict((bucket or {}).get("meta") or context_meta)
    events = list((bucket or {}).get("events") or [])

    try:
        if not settings.debug.llm_trace or not settings.debug.llm_trace_write_html:
            return None
        if not events:
            return None

        output_dir = Path(settings.debug.llm_trace_output_dir)
        if not output_dir.is_absolute():
            output_dir = _PROJECT_ROOT / output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        trace_id = meta.get("trace_id", "")
        endpoint = str(meta.get("endpoint", "unknown")).replace("/", "_").strip("_") or "root"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        file_path = output_dir / f"{stamp}-{endpoint}-{trace_id[:8] or 'no-trace'}.html"
        file_path.write_text(
            _render_html(meta, events, status_code, duration_seconds),
            encoding="utf-8",
        )
        return str(file_path)
    finally:
        _REQUEST_META.set({})


def _render_html(meta: dict, events: list[dict], status_code: int, duration_seconds: float) -> str:
    rows: list[str] = []
    for idx, event in enumerate(events, start=1):
        payload = event.get("payload", {})
        payload_text = json.dumps(payload, ensure_ascii=False, indent=2)
        title = escape(str(payload.get("event", "event")))
        prompt = escape(str(payload.get("prompt_name", "")))
        label = escape(str(payload.get("label", "")))
        time_text = escape(str(event.get("time", "")))
        rows.append(
            """
            <details class=\"event\" open>
              <summary>
                <span class=\"idx\">#{idx}</span>
                <span class=\"name\">{title}</span>
                <span class=\"meta\">{time_text}</span>
              </summary>
              <div class=\"chips\">
                <span>prompt: {prompt}</span>
                <span>label: {label}</span>
              </div>
              <pre>{payload_text}</pre>
            </details>
            """.format(
                idx=idx,
                title=title,
                time_text=time_text,
                prompt=prompt or "-",
                label=label or "-",
                payload_text=escape(payload_text),
            )
        )

    trace_id = escape(str(meta.get("trace_id", "")))
    endpoint = escape(str(meta.get("endpoint", "")))
    started_at = escape(str(meta.get("started_at", "")))

    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <title>LLM Trace Audit</title>
  <style>
    body {{ font-family: Segoe UI, PingFang SC, Microsoft YaHei, sans-serif; margin: 24px; color: #1f2937; background: #f8fafc; }}
    h1 {{ margin: 0 0 12px; font-size: 24px; }}
    .card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px; margin-bottom: 16px; }}
    .kv {{ display: grid; grid-template-columns: 180px 1fr; gap: 8px 12px; font-size: 14px; }}
    .k {{ color: #6b7280; }}
    .event {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 10px 12px; margin-bottom: 10px; }}
    .event summary {{ cursor: pointer; list-style: none; display: flex; gap: 10px; align-items: center; }}
    .event summary::-webkit-details-marker {{ display: none; }}
    .idx {{ color: #2563eb; font-weight: 600; }}
    .name {{ font-weight: 600; }}
    .meta {{ color: #6b7280; margin-left: auto; font-size: 12px; }}
    .chips {{ margin: 8px 0; display: flex; gap: 8px; flex-wrap: wrap; }}
    .chips span {{ background: #eef2ff; color: #3730a3; padding: 4px 8px; border-radius: 999px; font-size: 12px; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #0f172a; color: #e2e8f0; padding: 12px; border-radius: 8px; font-size: 12px; overflow: auto; }}
  </style>
</head>
<body>
  <h1>LLM Trace Audit</h1>
  <section class=\"card\">
    <div class=\"kv\">
      <div class=\"k\">traceId</div><div>{trace_id}</div>
      <div class=\"k\">endpoint</div><div>{endpoint}</div>
      <div class=\"k\">startedAt</div><div>{started_at}</div>
      <div class=\"k\">statusCode</div><div>{status_code}</div>
      <div class=\"k\">durationSeconds</div><div>{duration_seconds:.3f}</div>
      <div class=\"k\">eventCount</div><div>{len(events)}</div>
    </div>
  </section>
  <section>
    {''.join(rows)}
  </section>
</body>
</html>
"""