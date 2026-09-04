from copy import deepcopy

import app.capabilities.contract_review.two_stage.prepare_prompts as prepare_prompts_module
from app.capabilities.contract_review.two_stage.prepare_prompts import (
    PREPARE_PROMPT_NAMES,
    build_prepare_prompt,
    compute_prepare_prompt_bundle_hash,
)
from app.capabilities.contract_review.two_stage.prepare_response_formats import get_prepare_response_format


FORBIDDEN_TERMS = [
    "PASS",
    "WARN",
    "FAIL",
    "check_key",
    "reason_key",
    "issue_key",
    "signing_preset",
    "manual_override",
    "最多三条",
    "Seq",
]


def test_all_prepare_prompt_names_have_system_user_and_response_schema():
    for name in PREPARE_PROMPT_NAMES:
        messages = build_prepare_prompt(
            name,
            markdown="示例正文",
            scope_label="main",
            extraction_input="{}",
        )
        response_schema = get_prepare_response_format(name)

        assert len(messages) >= 2
        assert response_schema["type"] == "json_schema"


def test_prepare_prompts_do_not_include_forbidden_terms():
    for name in PREPARE_PROMPT_NAMES:
        messages = build_prepare_prompt(
            name,
            markdown="示例正文",
            scope_label="main",
            extraction_input="{}",
        )
        response_schema = get_prepare_response_format(name)

        blob = "\n".join(str(item.content) for item in messages) + "\n" + str(response_schema)
        lowered = blob.lower()
        for term in FORBIDDEN_TERMS:
            assert term.lower() not in lowered


def test_attachment_prompt_explicitly_requests_party_mentions():
    messages = build_prepare_prompt(
        "prepare_attachment_document",
        markdown="示例正文",
        scope_label="attachment-1",
        extraction_input="{}",
    )

    assert "主体称谓观察" in "\n".join(str(item.content) for item in messages)


def test_prompt_bundle_hash_changes_when_isolated_prompt_text_changes(monkeypatch):
    baseline = compute_prepare_prompt_bundle_hash()

    cloned = deepcopy(prepare_prompts_module._load_template())
    cloned["prepare_header_parties_main"]["user"] += "\n补充：保持候选可追溯。"
    monkeypatch.setattr(prepare_prompts_module, "_template", cloned)

    changed = compute_prepare_prompt_bundle_hash()

    assert changed != baseline


def test_prompt_bundle_hash_changes_when_isolated_response_schema_changes(monkeypatch):
    baseline = compute_prepare_prompt_bundle_hash()

    original_get_response_format = prepare_prompts_module.get_prepare_response_format

    def _patched_response_format(name: str):
        schema = original_get_response_format(name)
        if name == "prepare_header_parties_main":
            schema["json_schema"]["name"] = schema["json_schema"]["name"] + "_v2"
        return schema

    monkeypatch.setattr(
        prepare_prompts_module,
        "get_prepare_response_format",
        _patched_response_format,
    )

    changed = compute_prepare_prompt_bundle_hash()

    assert changed != baseline
