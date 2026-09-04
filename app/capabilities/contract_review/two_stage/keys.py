from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from app.capabilities.contract_review.two_stage.hashing import canonical_json_bytes


def _canonical_sort_key(value: Any) -> str:
    """列表元素排序键：基于其归一化后的 canonical JSON 表示。"""
    return canonical_json_bytes(_normalize_for_key(value)).decode("utf-8")


def _normalize_for_key(value: Any) -> Any:
    """递归归一化业务坐标，保证稳定键不变量由生产代码承担。

    - dict：键排序由 canonical_json_bytes(sort_keys=True) 处理；
    - list：元素递归归一化后按 canonical JSON 排序，使数组重排不改变键。
    """
    if isinstance(value, Mapping):
        return {key: _normalize_for_key(item) for key, item in value.items()}
    if isinstance(value, list):
        return sorted(
            (_normalize_for_key(item) for item in value),
            key=_canonical_sort_key,
        )
    return value


def stable_key(kind: str, coordinates: Mapping[str, Any]) -> str:
    """生成确定性稳定键。

    生产代码在入口处对 coordinates 做递归归一化（dict 键排序 + list 排序），
    因此数组重排、dict 键顺序变化都不会改变键。调用方无需（也不应）自行排序。
    """
    payload = {
        "kind": kind,
        "coordinates": _normalize_for_key(dict(coordinates)),
    }
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()[:24]
    return f"{kind}:{digest}"


def embedded_document_key(
    main_document_id: str,
    start: int,
    end: int,
    title: str,
) -> str:
    """内嵌附件文档键：仅接受业务身份坐标，模型自由文案不得进入。"""
    return stable_key(
        "embedded",
        {
            "main_document_id": main_document_id,
            "start": start,
            "end": end,
            "title": title,
        },
    )


def uploaded_document_key(attachment_id: str) -> str:
    """上传附件文档键：仅接受业务身份坐标。"""
    return stable_key("uploaded", {"attachment_id": attachment_id})


def preparation_issue_key(code: str, basis: str, document_keys: Sequence[str]) -> str:
    """准备期问题键：document_keys 为无序引用集合，由生产代码归一化。"""
    return stable_key(
        "preparation_issue",
        {
            "code": code,
            "basis": basis,
            "document_keys": list(document_keys),
        },
    )


def evidence_key(document_key: str, start: int, end: int) -> str:
    """证据键：仅接受业务身份坐标（文档 + 位置区间）。"""
    return stable_key(
        "evidence",
        {
            "document_key": document_key,
            "start": start,
            "end": end,
        },
    )
