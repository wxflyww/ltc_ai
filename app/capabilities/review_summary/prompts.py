"""加载 `prompts/review_summary.yaml`、构造 LangChain 消息、抽取模型输出 JSON。

与 `contract_review` / `translate` 零依赖（架构约定：能力之间零依赖）——模板加载、
JSON 抽取与 response_format 定义均在本模块自有实现，只消费 `app/core` 与 `app/models`。

约定：`system` 为静态正文（不做占位符替换，可直接书写 JSON 花括号）；`user` 走
`str.format(**kwargs)`，占位符由各 `*_block` 参数填充。
"""
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.core.errors import ModelFormatError

_PROMPT_FILE = Path(__file__).resolve().parents[3] / "prompts" / "review_summary.yaml"
_template: dict | None = None


def _load_template() -> dict:
    global _template
    if _template is None:
        _template = yaml.safe_load(_PROMPT_FILE.read_text(encoding="utf-8"))
    return _template


def _reset_template() -> None:
    """测试用：清空模板缓存（conftest 不覆盖本模块单例）。"""
    global _template
    _template = None


def build_prompt(name: str, **kwargs) -> list[BaseMessage]:
    """按任务名（`summary` / `opinion`）构造 [SystemMessage, HumanMessage]。"""
    tpl = _load_template()[name]
    return [
        SystemMessage(content=tpl["system"].strip()),
        HumanMessage(content=tpl["user"].format(**kwargs)),
    ]


# --------------------------------------------------------------- response_format
# vLLM guided decoding：strict json_schema，与既有能力同一口径。字段全部 required +
# additionalProperties=false，可空文本用 ["string","null"]。


def _object(properties: dict[str, Any], *, additional_properties: bool = False) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": additional_properties,
        "required": list(properties),
        "properties": properties,
    }


def _string_array() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


_RESPONSE_FORMATS: dict[str, dict[str, Any]] = {
    "summary": {
        "type": "json_schema",
        "json_schema": {
            "name": "review_summary_text",
            "strict": True,
            "schema": _object(
                {
                    "text": {"type": ["string", "null"]},
                    "source_refs": _string_array(),
                }
            ),
        },
    },
    "opinion": {
        "type": "json_schema",
        "json_schema": {
            "name": "review_summary_opinion_details",
            "strict": True,
            "schema": _object(
                {
                    "summaries": {
                        "type": "array",
                        "items": _object(
                            {
                                "index": {"type": "integer"},
                                "summary": {"type": ["string", "null"]},
                                "source_refs": _string_array(),
                            }
                        ),
                    }
                }
            ),
        },
    },
}


def get_response_format(name: str) -> dict[str, Any]:
    """返回该任务的 guided-decoding response_format（深拷贝，调用方改动不污染模板）。"""
    return deepcopy(_RESPONSE_FORMATS[name])


# ------------------------------------------------------------------ JSON 抽取

_THINK_CLOSE_TAG = re.compile(r"</think\s*>", re.IGNORECASE)


def _strip_think_blocks(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.IGNORECASE)
    if _THINK_CLOSE_TAG.search(text):
        # Qwen 关思考失效时偶发只吐闭标签（无开标签）：闭标签之前全是思考草稿，
        # 若整段保留，_extract_json_object 会取到草稿里的 JSON 并静默返回错误结构。
        text = _THINK_CLOSE_TAG.split(text)[-1]
    return text.strip()


def _strip_fenced_block(text: str) -> str:
    match = re.match(r"^```(?:json|JSON)?\s*(.*?)\s*```$", text, re.S)
    return match.group(1).strip() if match else text


def _extract_json_object(text: str) -> dict | None:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def parse_json_object(content: str) -> dict:
    """从模型输出中抽取 JSON 对象；抽不出即 `ModelFormatError`（20003）。"""
    text = _strip_fenced_block(_strip_think_blocks((content or "").strip()))
    if not text:
        raise ModelFormatError("模型输出为空")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        extracted = _extract_json_object(text)
        if extracted is None:
            raise ModelFormatError("模型输出不是合法JSON") from exc
        return extracted
    if not isinstance(parsed, dict):
        raise ModelFormatError("模型输出JSON不是对象")
    return parsed
