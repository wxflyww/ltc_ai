from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal


PreparePromptName = Literal[
    "prepare_header_parties_main",
    "prepare_signature_document",
    "prepare_amount_copy_main",
    "prepare_attachment_document",
]

_MENTION_KIND_VALUES = ["PARTY_DEFINITION", "PARTY_APPELLATION", "ROLE_REFERENCE"]


def _nullable_string() -> dict[str, Any]:
    return {"type": ["string", "null"]}


def _nullable_enum(values: list[str]) -> dict[str, Any]:
    return {"enum": [*values, None]}


def _nullable_bool() -> dict[str, Any]:
    return {"type": ["boolean", "null"]}


def _array(items: dict[str, Any], *, min_items: int | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "array",
        "items": items,
    }
    if min_items is not None:
        schema["minItems"] = min_items
    return schema


def _object(
    properties: dict[str, Any],
    required: list[str] | None = None,
    *,
    additional_properties: bool = False,
) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": additional_properties,
        "required": required if required is not None else list(properties),
        "properties": properties,
    }


SOURCE_GAP_ITEM_SCHEMA = _object({
    "affected_fact_kinds": _array({"type": "string", "minLength": 1}, min_items=1),
    "message": {"type": "string", "minLength": 1},
    "quote": _nullable_string(),
    "document_key": _nullable_string(),
})


HEADER_PARTIES_CANDIDATE_SCHEMA = _object({
    "candidate_ref": {"type": "string", "minLength": 1},
    "candidate_kind": {
        "type": "string",
        "enum": [
            "CONTRACT_NAME",
            "CONTRACT_NUMBER",
            "PROJECT_NAME",
            "PROJECT_NUMBER",
            "SIGNING_LOCATION",
            "SIGNING_DATE",
            "CANONICAL_PARTY",
            "PARTY_MENTION",
        ],
    },
    "document_key": {"type": "string", "minLength": 1},
    "quote": {"type": "string", "minLength": 1},
    "contract_name": _nullable_string(),
    "contract_number": _nullable_string(),
    "project_name": _nullable_string(),
    "project_number": _nullable_string(),
    "signing_location": _nullable_string(),
    "signing_date": _nullable_string(),
    "party_role": _nullable_string(),
    "party_name": _nullable_string(),
    "party_aliases": _array({"type": "string"}),
    "mention_text": _nullable_string(),
    "mention_kind": _nullable_enum(_MENTION_KIND_VALUES),
})


SIGNATURE_CANDIDATE_SCHEMA = _object({
    "candidate_ref": {"type": "string", "minLength": 1},
    "candidate_kind": {
        "type": "string",
        "enum": [
            "SIGNATURE_BLOCK",
            "SIGNER_NAME",
            "IDENTITY_NUMBER",
            "SIGNING_DATE",
            "BANK_NAME",
            "BANK_ACCOUNT",
            "ACCOUNT_HOLDER",
            "ADDRESS",
            "PHONE",
            "FAX",
            "WEBSITE",
            "POSTAL_CODE",
        ],
    },
    "document_key": {"type": "string", "minLength": 1},
    "quote": {"type": "string", "minLength": 1},
    "party_name": _nullable_string(),
    "role_text": _nullable_string(),
    "signer_name": _nullable_string(),
    "identity_number": _nullable_string(),
    "signing_date": _nullable_string(),
    "bank_name": _nullable_string(),
    "bank_account": _nullable_string(),
    "account_holder": _nullable_string(),
    "address": _nullable_string(),
    "phone": _nullable_string(),
    "fax": _nullable_string(),
    "website": _nullable_string(),
    "postal_code": _nullable_string(),
    "block_ref": _nullable_string(),
    "continues_ref": _nullable_string(),
    "alternative_of_ref": _nullable_string(),
    "purpose_text": _nullable_string(),
})


AMOUNT_COPY_CANDIDATE_SCHEMA = _object({
    "candidate_ref": {"type": "string", "minLength": 1},
    "candidate_kind": {
        "type": "string",
        "enum": [
            "CURRENCY",
            "PAYMENT_METHOD",
            "TOTAL_AMOUNT",
            "AMOUNT_PAIR",
            "PAYMENT_STAGE",
            "COPY_TOTAL",
            "COPY_ALLOCATION",
        ],
    },
    "document_key": {"type": "string", "minLength": 1},
    "quote": {"type": "string", "minLength": 1},
    "currency": _nullable_string(),
    "payment_method": _nullable_string(),
    "total_amount_numeric": _nullable_string(),
    "total_amount_uppercase": _nullable_string(),
    "amount_label": _nullable_string(),
    "amount_numeric": _nullable_string(),
    "amount_uppercase": _nullable_string(),
    "stage_name": _nullable_string(),
    "stage_ratio": _nullable_string(),
    "stage_amount_numeric": _nullable_string(),
    "stage_amount_uppercase": _nullable_string(),
    "copies_total": _nullable_string(),
    "copy_role": _nullable_string(),
    "copy_count": _nullable_string(),
    "amount_role": _nullable_string(),
    "tax_treatment": _nullable_string(),
    "relation_kind": _nullable_string(),
    "stage_order": _nullable_string(),
    "stage_trigger_condition": _nullable_string(),
    "stage_payment_term": _nullable_string(),
    "stage_payment_method": _nullable_string(),
    "copy_allocation_semantics": _nullable_string(),
})


ATTACHMENT_CANDIDATE_SCHEMA = _object({
    "candidate_ref": {"type": "string", "minLength": 1},
    "candidate_kind": {
        "type": "string",
        "enum": [
            "PARTY_MENTION",
            "DECLARED_ATTACHMENT",
            "LOGICAL_ATTACHMENT",
            "ATTACHMENT_RELATION",
            "DECLARED_TOTAL",
        ],
    },
    "document_key": {"type": "string", "minLength": 1},
    "quote": {"type": "string", "minLength": 1},
    "mention_text": _nullable_string(),
    "party_name": _nullable_string(),
    "party_role": _nullable_string(),
    "mention_kind": _nullable_enum(_MENTION_KIND_VALUES),
    "declared_index": _nullable_string(),
    "declared_title": _nullable_string(),
    "declared_total": _nullable_string(),
    "content_embedded": _nullable_bool(),
    "section_heading_hint": _nullable_string(),
    "logical_title": _nullable_string(),
    "relation_declaration_ref": _nullable_string(),
    "relation_target_document_keys": _array({"type": "string"}),
    "relation_state": _nullable_enum(["LINKED", "UNCERTAIN"]),
})


def _envelope_schema(candidates_item_schema: dict[str, Any]) -> dict[str, Any]:
    return _object({
        "candidates": _array(candidates_item_schema),
        "source_gaps": _array(SOURCE_GAP_ITEM_SCHEMA),
    })


_PREPARE_RESPONSE_FORMATS: dict[PreparePromptName, dict[str, Any]] = {
    "prepare_header_parties_main": {
        "type": "json_schema",
        "json_schema": {
            "name": "contract_review_prepare_header_parties_main",
            "strict": True,
            "schema": _envelope_schema(HEADER_PARTIES_CANDIDATE_SCHEMA),
        },
    },
    "prepare_signature_document": {
        "type": "json_schema",
        "json_schema": {
            "name": "contract_review_prepare_signature_document",
            "strict": True,
            "schema": _envelope_schema(SIGNATURE_CANDIDATE_SCHEMA),
        },
    },
    "prepare_amount_copy_main": {
        "type": "json_schema",
        "json_schema": {
            "name": "contract_review_prepare_amount_copy_main",
            "strict": True,
            "schema": _envelope_schema(AMOUNT_COPY_CANDIDATE_SCHEMA),
        },
    },
    "prepare_attachment_document": {
        "type": "json_schema",
        "json_schema": {
            "name": "contract_review_prepare_attachment_document",
            "strict": True,
            "schema": _envelope_schema(ATTACHMENT_CANDIDATE_SCHEMA),
        },
    },
}


def get_prepare_response_format(prompt_name: PreparePromptName) -> dict[str, Any]:
    return deepcopy(_PREPARE_RESPONSE_FORMATS[prompt_name])

