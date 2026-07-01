"""加载 YAML prompt 模板并构造 LangChain 消息。"""
from pathlib import Path
from typing import Optional

import yaml
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

_PROMPT_FILE = Path(__file__).resolve().parents[3] / "prompts" / "translate.yaml"
_template: dict | None = None


def _load_template() -> dict:
    global _template
    if _template is None:
        _template = yaml.safe_load(_PROMPT_FILE.read_text(encoding="utf-8"))
    return _template


def build_translate_prompt(
    text: str, target_lang: str, source_lang: Optional[str]
) -> list[BaseMessage]:
    tpl = _load_template()
    src = source_lang or "auto"
    system = tpl["system"].strip()
    user = tpl["user"].format(text=text, target_lang=target_lang, source_lang=src)
    return [SystemMessage(content=system), HumanMessage(content=user)]
