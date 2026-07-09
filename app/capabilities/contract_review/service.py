from datetime import datetime

from langchain_core.messages import HumanMessage

from app.capabilities.contract_review.attachments import check_copies_and_attachments
from app.capabilities.contract_review.checks import (
    build_review_data,
    check_amount_payment,
    check_seq1,
    check_seq2_11,
    check_seq3,
)
from app.capabilities.contract_review.preset_client import fetch_preset, identify_our_party
from app.capabilities.contract_review.prompts import build_prompt, parse_json_object
from app.capabilities.contract_review.schemas import (
    CheckItem,
    ContractReviewData,
    ContractReviewRequest,
    HeaderInfo,
    SignatureInfo,
)
from app.core.errors import ModelFormatError
from app.models.llm import get_chat_model, invoke_model


def _require_keys(payload: dict, keys: list[str], prompt_name: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise ModelFormatError(f"{prompt_name}模型输出缺少字段：{', '.join(missing)}")


def _invoke_json_prompt(prompt_name: str, **kwargs) -> dict:
    model = get_chat_model()
    messages = build_prompt(prompt_name, **kwargs)
    content, _usage = invoke_model(model, messages)
    try:
        return parse_json_object(content)
    except ModelFormatError as first_error:
        retry_messages = [
            *messages,
            HumanMessage(content=(
                "上一次输出不是合法JSON。请只返回一个JSON对象，"
                "不要解释、不要markdown代码块、不要<think>内容。"
            )),
        ]
        retry_content, _retry_usage = invoke_model(model, retry_messages)
        try:
            return parse_json_object(retry_content)
        except ModelFormatError as second_error:
            raise ModelFormatError(f"{prompt_name}{second_error.message}") from first_error


def _preprocess_request(request: ContractReviewRequest) -> dict:
    attachment_dicts = [item.model_dump() for item in request.attachments]
    full_text_and_attachments = request.contract_md
    if attachment_dicts:
        attachment_text = "\n\n".join(
            f"【附件】{item.get('filename')}\n{item.get('text', '')}"
            for item in attachment_dicts
        )
        full_text_and_attachments = f"{request.contract_md}\n\n{attachment_text}"
    return {
        "full_text": request.contract_md,
        "full_text_and_attachments": full_text_and_attachments,
        "attachments": attachment_dicts,
    }


def _parse_model_checks(payload: dict, item_id: str, item_name: str) -> list[CheckItem]:
    raw_checks = payload.get("checks", [])
    if not isinstance(raw_checks, list):
        raise ModelFormatError(f"{item_id}模型输出checks不是数组")
    items: list[CheckItem] = []
    for raw in raw_checks:
        if not isinstance(raw, dict):
            raise ModelFormatError(f"{item_id}模型输出checks元素不是对象")
        raw.setdefault("id", item_id)
        raw.setdefault("name", item_name)
        items.append(CheckItem.model_validate(raw))
    if not items:
        items.append(CheckItem(id=item_id, name=item_name, result="PASS", block_level="通过", reason=None))
    return items


def _run_b1(full_text_and_attachments: str) -> list[CheckItem]:
    payload = _invoke_json_prompt("b1_appellation", full_text_and_attachments=full_text_and_attachments)
    return _parse_model_checks(payload, "B-1", "称谓一致性")


def _run_b4(resolved_attachments: list[dict], baseline: dict) -> list[CheckItem]:
    items: list[CheckItem] = []
    for attachment in resolved_attachments:
        payload = _invoke_json_prompt(
            "b4_attachment_content",
            baseline=baseline,
            attachment_text=attachment.get("text", ""),
        )
        items.extend(_parse_model_checks(payload, "B-4", f"附件内容一致性-{attachment.get('title') or attachment.get('index')}"))
    if not resolved_attachments:
        items.append(CheckItem(id="B-4", name="附件内容一致性", result="NA", block_level="不适用", reason="无可检查附件"))
    return items


def run_review_pipeline(request: ContractReviewRequest) -> list[CheckItem | dict]:
    prepared = _preprocess_request(request)

    a1a = _invoke_json_prompt("a1a_party_extraction", full_text=prepared["full_text"])
    _require_keys(a1a, ["header", "signature_parties", "sections"], "A-1a")
    header = HeaderInfo.model_validate(a1a["header"])

    our_party, preset = identify_our_party(header.parties, fetch_preset)

    if our_party is not None:
        a1b = _invoke_json_prompt("a1b_our_signature", our_party=our_party.name, full_text=prepared["full_text"])
        _require_keys(a1b, ["signature"], "A-1b")
        signature = SignatureInfo.model_validate({
            **a1b["signature"],
            "signature_parties": a1a.get("signature_parties", []),
        })
    else:
        signature = SignatureInfo(signature_parties=[])

    items: list[CheckItem] = []
    items.extend(check_seq1(header, our_party, preset))
    seq2_items, seq11_items = check_seq2_11(header, signature, our_party, preset)
    items.extend(seq2_items)
    items.append(check_seq3(header, signature, our_party))
    items.extend(seq11_items)

    a3 = _invoke_json_prompt("a3_amount_payment", full_text=prepared["full_text"])
    items.extend(check_amount_payment(a3))

    a4 = _invoke_json_prompt("a4_copies_attachments", full_text=prepared["full_text"])
    _require_keys(a4, ["copies", "attachments_declared"], "A-4")
    attachment_result = check_copies_and_attachments(
        a4,
        a1a.get("sections", []),
        prepared["attachments"],
        prepared["full_text"],
    )
    items.extend(attachment_result["check_results"])

    items.extend(_run_b1(prepared["full_text_and_attachments"]))
    items.extend(_run_b4(attachment_result["resolved_attachments"], {
        "header": header.model_dump(),
        "signature": signature.model_dump(),
        "preset": preset.model_dump() if preset is not None else None,
    }))
    return items


def review_contract(request: ContractReviewRequest, check_time: str | None = None) -> ContractReviewData:
    timestamp = check_time or datetime.now().isoformat(timespec="seconds")
    raw_items = run_review_pipeline(request)
    items = [item if isinstance(item, CheckItem) else CheckItem(**item) for item in raw_items]
    return build_review_data(timestamp, items)
