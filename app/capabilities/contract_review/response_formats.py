from copy import deepcopy
from typing import Any


def _nullable_string() -> dict[str, Any]:
    return {"type": ["string", "null"]}


def _nullable_number() -> dict[str, Any]:
    return {"type": ["number", "string", "null"]}


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


CONTRACT_PARTY_SCHEMA = _object({
    "role": _nullable_string(),
    "name": _nullable_string(),
    "aliases": {"type": "array", "items": {"type": "string"}},
})

B1_OBSERVATION_SCHEMA = _object({
    "result": {"type": "string", "enum": ["PASS", "WARN", "FAIL", "NA"]},
    "block_level": {"type": "string", "enum": ["通过", "提示", "硬阻断", "不适用"]},
    "role": _nullable_string(),
    "baseline_appellation": _nullable_string(),
    "found_appellation": _nullable_string(),
    "evidence_quote": _nullable_string(),
    "evidence_type": {
        "type": ["string", "null"],
        "enum": ["party_appellation", "party_definition", "role_without_definition", "contract_or_project_name", "background_reference", "unknown", None],
    },
})

CHECK_ITEM_SCHEMA = _object({
    "result": {"type": "string", "enum": ["PASS", "WARN", "FAIL", "NA"]},
    "block_level": {"type": "string", "enum": ["通过", "提示", "硬阻断", "不适用"]},
    "reason": _nullable_string(),
})

B4_OBSERVATION_SCHEMA = _object({
    "result": {"type": "string", "enum": ["PASS", "WARN", "FAIL", "NA"]},
    "block_level": {"type": "string", "enum": ["通过", "提示", "硬阻断", "不适用"]},
    "check_type": {"type": "string", "enum": ["total_amount", "other"]},
    "attachment_value": _nullable_number(),
    "attachment_evidence": _nullable_string(),
    "reason": _nullable_string(),
})

RESPONSE_FORMATS: dict[str, dict[str, Any]] = {
    "a1a_party_extraction": {
        "type": "json_schema",
        "json_schema": {
            "name": "contract_review_a1a_party_extraction",
            "strict": True,
            "schema": _object({
                "header": _object({
                    "contract_name": _nullable_string(),
                    "project_name": _nullable_string(),
                    "project_number": _nullable_string(),
                    "contract_number": _nullable_string(),
                    "signing_location": _nullable_string(),
                    "signing_date": _nullable_string(),
                    "parties": {"type": "array", "items": CONTRACT_PARTY_SCHEMA},
                }),
                "signature_parties": {"type": "array", "items": CONTRACT_PARTY_SCHEMA},
                "sections": {
                    "type": "array",
                    "items": _object({
                        "title": _nullable_string(),
                        "content": _nullable_string(),
                    }),
                },
            }),
        },
    },
    "a1b_our_signature": {
        "type": "json_schema",
        "json_schema": {
            "name": "contract_review_a1b_our_signature",
            "strict": True,
            "schema": _object({
                "signature": _object({
                    "role": _nullable_string(),
                    "name": _nullable_string(),
                    "legal_rep_name": _nullable_string(),
                    "signer_id_number": _nullable_string(),
                    "signing_date": _nullable_string(),
                    "bank_name": _nullable_string(),
                    "bank_account": _nullable_string(),
                    "account_holder": _nullable_string(),
                    "address": _nullable_string(),
                    "phone": _nullable_string(),
                    "fax": _nullable_string(),
                    "website": _nullable_string(),
                    "postal_code": _nullable_string(),
                }),
            }),
        },
    },
    "a3_amount_payment": {
        "type": "json_schema",
        "json_schema": {
            "name": "contract_review_a3_amount_payment",
            "strict": True,
            "schema": _object({
                "currency": _nullable_string(),
                "payment_method": _nullable_string(),
                "total_amount_numeric": _nullable_number(),
                "total_amount_evidence": _nullable_string(),
                "total_amount_uppercase": _nullable_string(),
                "total_amount_match": {"type": ["boolean", "null"]},
                "payment_stages": {
                    "type": "array",
                    "items": _object({
                        "stage_name": _nullable_string(),
                        "percentage": _nullable_number(),
                        "amount_numeric": _nullable_number(),
                        "amount_uppercase": _nullable_string(),
                    }),
                },
            }),
        },
    },
    "a4_copies_attachments": {
        "type": "json_schema",
        "json_schema": {
            "name": "contract_review_a4_copies_attachments",
            "strict": True,
            "schema": _object({
                "copies": _object({
                    "total_copies": {"type": ["integer", "string", "null"]},
                    "party_copies": {
                        "type": "array",
                        "items": _object({
                            "role": _nullable_string(),
                            "copies": {"type": ["integer", "string", "null"]},
                        }),
                    },
                }),
                "attachments_declared": {
                    "type": "array",
                    "items": _object({
                        "index": {"type": ["integer", "string", "null"]},
                        "title": _nullable_string(),
                        "content_embedded_in_contract": {"type": ["boolean", "null"]},
                        "section_heading_hint": _nullable_string(),
                    }),
                },
                "total_declared": {"type": ["integer", "string", "null"]},
            }),
        },
    },
    "b1_appellation": {
        "type": "json_schema",
        "json_schema": {
            "name": "contract_review_b1_appellation",
            "strict": True,
            "schema": _object({
                "checks": {"type": "array", "items": B1_OBSERVATION_SCHEMA},
            }),
        },
    },
    "b4_attachment_content": {
        "type": "json_schema",
        "json_schema": {
            "name": "contract_review_b4_attachment_content",
            "strict": True,
            "schema": _object({
                "checks": {"type": "array", "items": B4_OBSERVATION_SCHEMA},
            }),
        },
    },
}


def get_response_format(prompt_name: str) -> dict[str, Any] | None:
    response_format = RESPONSE_FORMATS.get(prompt_name)
    return deepcopy(response_format) if response_format else None
