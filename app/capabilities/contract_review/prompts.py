import json
import re
from pathlib import Path

import yaml
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.core.errors import ModelFormatError

_PROMPT_FILE = Path(__file__).resolve().parents[3] / "prompts" / "contract_review.yaml"
_template: dict | None = None


def _load_template() -> dict:
    global _template
    if _template is None:
        _template = yaml.safe_load(_PROMPT_FILE.read_text(encoding="utf-8"))
    return _template


def build_prompt(name: str, **kwargs) -> list[BaseMessage]:
    tpl = _load_template()[name]
    return [
        SystemMessage(content=tpl["system"].strip()),
        HumanMessage(content=tpl["user"].format(**kwargs)),
    ]


def _strip_think_blocks(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I).strip()


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
    text = _strip_fenced_block(_strip_think_blocks(content.strip()))
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        extracted = _extract_json_object(text)
        if extracted is not None:
            return extracted
        raise ModelFormatError("模型输出不是合法JSON") from exc
    if not isinstance(parsed, dict):
        raise ModelFormatError("模型输出JSON不是对象")
    return parsed
