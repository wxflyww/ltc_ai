from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.capabilities.contract_review.two_stage.hashing import canonical_json_bytes
from app.capabilities.contract_review.two_stage.prepare_response_formats import (
    PreparePromptName,
    get_prepare_response_format,
)


_PROMPT_FILE = Path(__file__).resolve().parents[4] / "prompts" / "contract_review_prepare.yaml"
_template: dict[str, dict[str, str]] | None = None

PREPARE_PROMPT_NAMES: tuple[PreparePromptName, ...] = (
    "prepare_header_parties_main",
    "prepare_signature_document",
    "prepare_amount_copy_main",
    "prepare_attachment_document",
)


def _load_template() -> dict[str, dict[str, str]]:
    global _template
    if _template is None:
        loaded = yaml.safe_load(_PROMPT_FILE.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("Prepare Prompt 模板格式非法")
        missing = [name for name in PREPARE_PROMPT_NAMES if name not in loaded]
        if missing:
            raise ValueError(f"Prepare Prompt 模板缺少条目: {', '.join(missing)}")
        _template = loaded
    return _template


def build_prepare_prompt(name: PreparePromptName, **kwargs: str) -> list[BaseMessage]:
    template = _load_template()[name]
    return [
        SystemMessage(content=template["system"].strip()),
        HumanMessage(content=template["user"].format(**kwargs).strip()),
    ]


def compute_prepare_prompt_bundle_hash() -> str:
    template = _load_template()
    bundle = []
    for name in sorted(PREPARE_PROMPT_NAMES):
        entry = template[name]
        bundle.append(
            {
                "name": name,
                "system": entry["system"].strip(),
                "user": entry["user"].strip(),
                "response_schema": get_prepare_response_format(name),
            }
        )
    digest = hashlib.sha256(canonical_json_bytes(bundle)).hexdigest()
    return f"sha256:{digest}"
