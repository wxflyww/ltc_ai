import re
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


def test_amount_copy_prompt_explicitly_requests_stage_amount_fields():
    """prepare_amount_copy_main 任务段必须显式锁定 PAYMENT_STAGE：
    1) 要求输出 stage_amount_numeric 与 stage_amount_uppercase；
    2) 两字段仅在原文明示时填写；
    3) 原文未明示时显式为 null；
    4) 不得由比例、总额或其他字段推导、计算或补写数字/大写阶段金额。"""
    messages = build_prepare_prompt(
        "prepare_amount_copy_main",
        markdown="示例正文",
        scope_label="main",
        extraction_input="{}",
    )
    task_segments = [
        str(item.content)
        for item in messages
        if "提取主合同金额、付款、份数候选" in str(item.content)
    ]
    assert task_segments, "未取到 prepare_amount_copy_main 任务段，断言落空"
    task_text = "\n".join(task_segments)

    start = task_text.index("8)")
    end = task_text.index("9)")
    clause = re.sub(r"\s+", " ", task_text[start:end])

    # 1) 明确要求输出两个阶段金额字段
    assert "stage_amount_numeric" in clause
    assert "stage_amount_uppercase" in clause
    assert re.search(r"保留原文\s*数字金额", clause)
    assert re.search(r"保留原文\s*大写金额", clause)

    # 2) 仅在原文明示时填写
    assert re.search(r"仅在原文[^；。]*明示时填写", clause)

    # 3) 原文未明示时显式为 null
    assert re.search(r"未\s*明示的字段显式输出\s*null", clause)

    # 4) 不得推导、计算或补写阶段金额
    assert "不得计算阶段金额" in clause
    assert re.search(r"不得由比例、总额\s*或其他字段推导金额", clause)
    assert "不得自动补写大写金额" in clause


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


def test_header_parties_prompt_explicitly_requires_unique_nonblank_candidate_ref():
    """prepare_header_parties_main 任务段必须显式约束 candidate_ref：
    1) 每条候选输出非空 candidate_ref；
    2) 仅在单次输出内彼此唯一；
    3) 仅为本次输出内的临时内部引用，装配后消失。"""
    messages = build_prepare_prompt(
        "prepare_header_parties_main",
        markdown="示例正文",
        scope_label="main",
        extraction_input="{}",
    )
    task_segments = [
        str(item.content)
        for item in messages
        if "提取主合同首部与签约方候选" in str(item.content)
    ]
    assert task_segments, "未取到 prepare_header_parties_main 任务段，断言落空"
    task_text = "\n".join(task_segments)

    start = task_text.index("要求：")
    end = task_text.index("scope_label:")
    clause = re.sub(r"\s+", " ", task_text[start:end])

    # 1) 明确要求输出 candidate_ref，而且必须非空
    assert "candidate_ref" in clause
    assert re.search(r"非空[^；。]*candidate_ref|candidate_ref[^；。]*非空", clause)
    # 2) 仅在单次输出内彼此唯一
    assert re.search(r"次输出内[^；。]*唯一", clause)
    # 3) 仅为临时内部引用，装配后消失
    assert re.search(r"临时内部引用", clause)
    assert re.search(r"装配后[^；。]*消失", clause)
