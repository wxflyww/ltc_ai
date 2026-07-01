"""翻译业务：组装 prompt、调模型、指数退避重试。重试只在 service 层。"""
import random
import time
from typing import Callable

from app.core.errors import ModelFormatError, ModelInvocationError
from app.core.logging import get_logger
from app.models.llm import get_chat_model, invoke_model
from app.capabilities.translate.prompts import build_translate_prompt
from app.capabilities.translate.schemas import TranslateData, TranslateRequest

logger = get_logger("translate")

MAX_ATTEMPTS = 3  # 1 初始 + 2 重试
BASE_BACKOFFS = [1.0, 2.0]  # 秒，第 1、2 次重试前


def _is_retryable(err: Exception) -> bool:
    """超时、5xx、429 可重试；其他（含 ModelFormatError）不可重试。

    invoke_model 把原生 TimeoutError 转成 ModelTimeoutError（继承 AppError，
    非 TimeoutError 子类），故用类型名兜底匹配；同时兼容 httpx/openai 抛的
    带 status_code 属性的异常。
    """
    # ModelTimeoutError 或任何名字含 Timeout 的异常（httpx.ReadTimeout 等）
    if isinstance(err, (TimeoutError,)) or "Timeout" in type(err).__name__:
        return True
    status = getattr(err, "status_code", None)
    if status is not None and (status == 429 or 500 <= status < 600):
        return True
    return False


def _backoff_with_jitter(attempt: int) -> float:
    base = BASE_BACKOFFS[attempt]
    return base * random.uniform(0.8, 1.2)


def translate(
    request: TranslateRequest,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> TranslateData:
    """执行翻译。失败重试，重试耗尽抛 ModelInvocationError。"""
    messages = build_translate_prompt(
        text=request.text, target_lang=request.target_lang, source_lang=request.source_lang
    )
    model = get_chat_model()
    model_name = getattr(model, "model_name", "") or getattr(model, "model", "unknown")

    last_err: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            content, usage = invoke_model(model, messages)
        except Exception as err:  # noqa: BLE001
            last_err = err
            logger.warning("model call failed, retrying", extra={"attempt": attempt + 1})
            if _is_retryable(err) and attempt < MAX_ATTEMPTS - 1:
                sleep_fn(_backoff_with_jitter(attempt))
                continue
            # 不可重试，或重试耗尽
            if isinstance(err, ModelFormatError):
                raise
            raise ModelInvocationError(str(err)) from err
        # 成功路径
        if not content or not content.strip():
            raise ModelFormatError("model returned empty content")
        return TranslateData(
            translated_text=content.strip(),
            source_lang=request.source_lang or "auto",
            model=model_name,
            token_usage=usage,
        )
    # 理论不可达（循环内已 raise），兜底
    raise ModelInvocationError(str(last_err) if last_err else "unknown model failure")
