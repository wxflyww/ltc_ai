"""模型适配层：LangChain ChatModel 工厂 + 调用埋点。重试在 service 层。"""
import time

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from openai import APITimeoutError
from prometheus_client import Counter, Histogram

from app.core.config import get_settings
from app.core.errors import ModelOutputTooLongError, ModelTimeoutError
from app.core.logging import get_logger

logger = get_logger("llm")

llm_calls_total = Counter("llm_calls_total", "LLM calls", ["model", "status"])
llm_call_duration_seconds = Histogram("llm_call_duration_seconds", "LLM call latency", ["model"])
llm_tokens_total = Counter("llm_tokens_total", "LLM token usage", ["model", "type"])

_chat_model: BaseChatModel | None = None


def get_chat_model() -> BaseChatModel:
    """构造配置好的 LangChain ChatModel（vLLM OpenAI 兼容）。单例。"""
    global _chat_model
    if _chat_model is not None:
        return _chat_model
    s = get_settings().llm
    _chat_model = ChatOpenAI(
        model=s.model,
        base_url=s.base_url,
        temperature=s.temperature,
        timeout=s.timeout,
        # 禁用 openai SDK 的隐藏重试（默认 DEFAULT_MAX_RETRIES=2）：
        # SDK 会把读超时当可重试错误静默重发，导致一次超时 invoke 实际发出 3 个
        # HTTP 请求、服务端算力 ×3，且总等待膨胀到 timeout×3。重试策略一律交回
        # 业务层（translate/two_stage 各有自建退避；MVP 对超时不重试）。
        max_retries=0,
        api_key=s.api_key or "no-key",
    )
    return _chat_model


def _reset_chat_model() -> None:
    """测试用：重置单例。"""
    global _chat_model
    _chat_model = None


def invoke_model(
    model: BaseChatModel,
    messages: list,
    response_format: dict | None = None,
) -> tuple[str, dict]:
    """调用模型，返回 (content, token_usage)。超时转 ModelTimeoutError，其他错误原样抛出。"""
    model_name = getattr(model, "model_name", "") or getattr(model, "model", "unknown")
    start = time.perf_counter()
    try:
        if response_format is None:
            resp = model.invoke(messages)
        else:
            resp = model.invoke(messages, response_format=response_format)
    except (TimeoutError, APITimeoutError) as e:
        # openai SDK 的读超时抛 APITimeoutError（langchain_openai 再包一层
        # OpenAITimeoutError，同样是 APITimeoutError 子类），它不是内置
        # TimeoutError 的子类，必须显式捕获，否则会穿透成 500/29999。
        llm_calls_total.labels(model=model_name, status="timeout").inc()
        raise ModelTimeoutError(str(e)) from e
    finish_reason = str((getattr(resp, "response_metadata", None) or {}).get("finish_reason", "")).lower()
    if finish_reason == "length":
        llm_calls_total.labels(model=model_name, status="output_length").inc()
        raise ModelOutputTooLongError("finish_reason=length")

    elapsed = time.perf_counter() - start
    llm_call_duration_seconds.labels(model=model_name).observe(elapsed)

    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    usage_meta = getattr(resp, "usage_metadata", None) or {}
    usage = {
        "prompt_tokens": int(usage_meta.get("input_tokens", 0) or usage_meta.get("prompt_tokens", 0)),
        "completion_tokens": int(usage_meta.get("output_tokens", 0) or usage_meta.get("completion_tokens", 0)),
        "total_tokens": int(usage_meta.get("total_tokens", 0)),
    }
    llm_tokens_total.labels(model=model_name, type="prompt").inc(usage["prompt_tokens"])
    llm_tokens_total.labels(model=model_name, type="completion").inc(usage["completion_tokens"])
    llm_calls_total.labels(model=model_name, status="success").inc()
    logger.debug("llm invoked", extra={"llm_duration_seconds": round(elapsed, 3)})
    return content, usage
