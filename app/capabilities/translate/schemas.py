"""翻译请求/响应 Pydantic 模型。"""
from typing import Optional

from pydantic import BaseModel, Field


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, description="源文本")
    target_lang: str = Field(..., min_length=1, description="目标语言代码")
    source_lang: Optional[str] = Field(default=None, description="源语言代码，不传则模型自识别")


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class TranslateData(BaseModel):
    translated_text: str
    source_lang: str
    model: str
    token_usage: TokenUsage
