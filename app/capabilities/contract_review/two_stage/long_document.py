from __future__ import annotations

"""Task 8 Step 3：四类标准附件目录分类与全文确定性安全扫描计划。

正式依据：design 第 10 节（四类标准附件安全扫描与边界证明）、spec 7.5、
DEC-LTC-20260911-002（派生式边界证明、强类型 locator）与实施计划 Task 8 Step 3。

边界与职责：
- 扫描资格只从 PreparedDocuments 与 document_key 派生。上传附件须同时存在于
  source_snapshot.attachments 与 markdown_by_document；内嵌附件还须 source_main_document_id
  匹配实际主文身份，且 source_locator 切片与附件 Markdown 完全一致；无法证明即返回 None，
  回退普通完整提取。
- 标准目录分类要求内部身份（文档名称/编号/版本）+ 正文结构交叉印证且无身份冲突；
  文件名、标题、篇幅或宽泛关键词不能单独触发。
- 全文扫描只输出绝对 Markdown 字符坐标 locator，不计算、不裁决、不调用模型；
  扫描、合并或校验失败向上传播为技术失败，不伪装为 coverage。
"""

import re
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.capabilities.contract_review.two_stage.documents import PreparedDocuments
from app.capabilities.contract_review.two_stage.evidence import (
    EvidenceLocationError,
    format_markdown_locator,
    parse_markdown_locator,
)
from app.capabilities.contract_review.two_stage.schemas import (
    DocumentKey,
    MarkdownCharLocator,
    NonBlankStr,
)
from app.core.errors import ModelFormatError


__all__ = [
    "APPROVED_STANDARD_ATTACHMENT_ALIASES",
    "STANDARD_ATTACHMENT_TYPES",
    "SafetyScanPlan",
    "build_standard_attachment_scan_plan",
    "merge_overlapping_ranges",
    "scan_complete_markdown_for_review_facts",
    "validate_scan_plan",
]


STANDARD_ATTACHMENT_TYPES = frozenset(
    {
        "需求说明书",
        "技术规范书",
        "工作说明书",
        "质量标准",
    }
)

# 当前没有经业务审核并进入版本化目录的同义名称；未来只能通过业务确认与版本化变更增加。
APPROVED_STANDARD_ATTACHMENT_ALIASES: dict[str, str] = {}


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SafetyScanPlan(_StrictModel):
    document_key: DocumentKey
    standard_type: NonBlankStr
    scanned_range: MarkdownCharLocator
    candidate_ranges: list[MarkdownCharLocator]
    scan_complete: Literal[True]


# 内部身份证据：文档名称 / 编号 / 版本必须在正文中显式出现。
_DOCUMENT_NAME_RE = re.compile(r"文档名称\s*[：:]\s*(\S+)")
_DOCUMENT_NUMBER_RE = re.compile(r"文档编号\s*[：:]\s*(\S+)")
_DOCUMENT_VERSION_RE = re.compile(r"版本\s*[：:]\s*(\S+)")
_HEADING_RE = re.compile(r"^#{1,6}(?!#)\s*(.+)$", re.MULTILINE)
# 正文分节标题只承认 ## 至 ######；任何 H1 均不计作正文分节（DEC-LTC-20260911-003）。
# 严格层级终止：H7 及更深层标题不得被截断为 H6。
_BODY_HEADING_RE = re.compile(r"^(#{2,6})(?!#)\s*(.+)$")
# 身份元数据行：文档名称 / 编号 / 版本声明，不构成正文分节标题或正文内容。
_IDENTITY_METADATA_RE = re.compile(r"^(?:文档名称|文档编号|版本)\s*[：:]")
_SELF_IDENTIFICATION_RE = re.compile(r"(?:本文档|本文件|此文档)\s*(?:为|是)\s*([^\s，。；、]+)")

# 全文安全扫描须覆盖的合同事实类别；每行命中即输出该行的绝对坐标窗口。
_SUBJECT_DEFINITION_RE = re.compile(
    r"^\s*(?:甲方|乙方|丙方|买方|卖方|发包方|承包方|委托方|受托方|供方|需方)\s*[：:]"
)
_PARTY_OBLIGATION_RE = re.compile(
    r"(?:甲方|乙方|丙方|双方)(?:应|须|应当|需要|负责|承担|承诺|不得|可以)"
)
_SIGNATURE_SECTION_RE = re.compile(
    r"(?:签署区|签字区|签署页|签字页|签章区|盖章区|签署栏|签字栏)"
)
_SIGNATORY_RE = re.compile(
    r"(?:法定代表人|法人代表|授权代表|授权代理人|委托代理人|授权委托人|签字人)"
)
_IDENTITY_NUMBER_RE = re.compile(r"(?:身份证|证件号)")
_SIGNING_DATE_RE = re.compile(
    r"(?:签署日期|签订日期|签署时间|签订时间|签署之日|合同生效日期)"
)
_BANK_ACCOUNT_RE = re.compile(
    r"(?:开户银行|开户行|开户账号|银行账号|银行账户|账户名称|账户名|户名|收款账户|账号)"
)
_ADDRESS_RE = re.compile(r"(?:地址|住所|注册地址|办公地址|联系地址)")
_PHONE_RE = re.compile(r"(?:联系电话|电话|手机号|座机|联系方式)")
_FAX_RE = re.compile(r"传真")
_WEBSITE_RE = re.compile(r"(?:网址|网站|https?://|www\.)")
_POSTCODE_RE = re.compile(r"(?:邮编|邮政编码)")

_FACT_PATTERNS = (
    _SUBJECT_DEFINITION_RE,
    _PARTY_OBLIGATION_RE,
    _SIGNATURE_SECTION_RE,
    _SIGNATORY_RE,
    _IDENTITY_NUMBER_RE,
    _SIGNING_DATE_RE,
    _BANK_ACCOUNT_RE,
    _ADDRESS_RE,
    _PHONE_RE,
    _FAX_RE,
    _WEBSITE_RE,
    _POSTCODE_RE,
)


def _find_attachment(documents: PreparedDocuments, document_key: str):
    for item in documents.source_snapshot.attachments:
        if item.document_key == document_key:
            return item
    return None


def _boundary_proven(documents: PreparedDocuments, attachment, markdown: str) -> bool:
    """从 PreparedDocuments 与 document_key 派生边界可靠性；无法证明即不可扫描。"""
    if attachment.source_kind == "UPLOADED":
        return True

    main_document = documents.source_snapshot.main_document
    if attachment.source_main_document_id != main_document.document_id:
        return False

    main_markdown = documents.markdown_by_document.get(main_document.document_key)
    if main_markdown is None:
        return False

    try:
        start, end = parse_markdown_locator(attachment.source_locator)
    except EvidenceLocationError:
        return False
    if end > len(main_markdown):
        return False
    return main_markdown[start:end] == markdown


def _self_identified_standard_types(markdown: str) -> set[str]:
    declared = {match.group(1) for match in _DOCUMENT_NAME_RE.finditer(markdown)}
    declared.update(match.group(1) for match in _SELF_IDENTIFICATION_RE.finditer(markdown))
    declared.update(match.group(1).strip() for match in _HEADING_RE.finditer(markdown))

    standard_types: set[str] = set()
    for value in declared:
        resolved = APPROVED_STANDARD_ATTACHMENT_ALIASES.get(value, value)
        if resolved in STANDARD_ATTACHMENT_TYPES:
            standard_types.add(resolved)
    return standard_types



def _is_identity_metadata(text: str) -> bool:
    """判断一行是否为文档身份元数据（字段式文档名称/编号/版本，或自我身份声明）。"""
    stripped = text.strip()
    return (
        _IDENTITY_METADATA_RE.match(stripped) is not None
        or _SELF_IDENTIFICATION_RE.match(stripped) is not None
    )


def _has_body_section_structure(markdown: str) -> bool:
    """保守 Markdown 正文结构判据（DEC-LTC-20260911-003）。

    仅当存在至少一个非身份元数据的两级至六级正文标题，且该标题之后、下一标题之前
    存在非空且非身份元数据的正文时，才满足结构交叉印证。任何一级标题均不构成正文分节，
    不因其文字是否等于文档名称而改变；首期不兼容中文编号段落标题。
    """
    lines = markdown.splitlines()
    heading_indices = [
        index for index, line in enumerate(lines) if _HEADING_RE.match(line)
    ]
    section_bounds = heading_indices + [len(lines)]

    for position, start in enumerate(heading_indices):
        heading_match = _BODY_HEADING_RE.match(lines[start])
        if heading_match is None:
            continue
        if _is_identity_metadata(heading_match.group(2)):
            continue
        section_end = section_bounds[position + 1]
        for line in lines[start + 1:section_end]:
            stripped = line.strip()
            if stripped and not _is_identity_metadata(stripped):
                return True
    return False


def _classify_standard_type(markdown: str) -> str | None:
    """内部身份 + 正文结构 + 无冲突三者同时成立才返回标准附件类别。"""
    name_match = _DOCUMENT_NAME_RE.search(markdown)
    if name_match is None:
        return None
    declared = name_match.group(1)
    standard_type = APPROVED_STANDARD_ATTACHMENT_ALIASES.get(declared, declared)
    if standard_type not in STANDARD_ATTACHMENT_TYPES:
        return None
    if _DOCUMENT_NUMBER_RE.search(markdown) is None:
        return None
    if _DOCUMENT_VERSION_RE.search(markdown) is None:
        return None
    if not _has_body_section_structure(markdown):
        return None

    identified = _self_identified_standard_types(markdown)
    if any(item != standard_type for item in identified):
        return None
    return standard_type


def scan_complete_markdown_for_review_facts(markdown: str) -> list[str]:
    """遍历规范化 Markdown 全文，输出命中合同事实类别的绝对坐标窗口 locator。"""
    windows: list[str] = []
    offset = 0
    for line in markdown.splitlines(keepends=True):
        content = line.rstrip("\n")
        if content.strip() and any(pattern.search(content) for pattern in _FACT_PATTERNS):
            windows.append(format_markdown_locator(offset, offset + len(content)))
        offset += len(line)
    return merge_overlapping_ranges(windows)


def merge_overlapping_ranges(ranges: Iterable[str]) -> list[str]:
    """把真正重叠的 locator 合并为并集；端点相接的相邻区间保持独立，结果与输入顺序无关且幂等。"""
    parsed = sorted(parse_markdown_locator(locator) for locator in ranges)
    merged: list[tuple[int, int]] = []
    for start, end in parsed:
        if merged and start < merged[-1][1]:
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return [format_markdown_locator(start, end) for start, end in merged]


def validate_scan_plan(plan: SafetyScanPlan, markdown: str) -> None:
    """校验 locator 强类型与文档边界；任何不成立都属技术失败并向上抛出。"""
    length = len(markdown)

    scanned_start, scanned_end = _require_locator(plan.scanned_range, "scanned_range", length)
    if scanned_start != 0 or scanned_end != length:
        raise ModelFormatError("SafetyScanPlan.scanned_range 必须覆盖规范化全文")

    for index, locator in enumerate(plan.candidate_ranges):
        _require_locator(locator, f"candidate_ranges[{index}]", length)


def _require_locator(locator, field: str, length: int) -> tuple[int, int]:
    if not isinstance(locator, str):
        raise ModelFormatError(f"SafetyScanPlan.{field} 必须是 MarkdownCharLocator 字符串")
    try:
        start, end = parse_markdown_locator(locator)
    except EvidenceLocationError as exc:
        raise ModelFormatError(f"SafetyScanPlan.{field} 非法 locator: {locator}") from exc
    if end > length:
        raise ModelFormatError(
            f"SafetyScanPlan.{field} 超出文档边界: {locator} (length={length})"
        )
    return start, end


def build_standard_attachment_scan_plan(
    documents: PreparedDocuments,
    document_key: DocumentKey,
) -> SafetyScanPlan | None:
    """为具备扫描资格的四类标准附件构建全文安全扫描计划；无法证明资格时返回 None。"""
    attachment = _find_attachment(documents, document_key)
    if attachment is None:
        return None

    markdown = documents.markdown_by_document.get(document_key)
    if markdown is None:
        return None

    if not _boundary_proven(documents, attachment, markdown):
        return None

    standard_type = _classify_standard_type(markdown)
    if standard_type is None:
        return None

    candidate_ranges = scan_complete_markdown_for_review_facts(markdown)
    plan = SafetyScanPlan(
        document_key=document_key,
        standard_type=standard_type,
        scanned_range=format_markdown_locator(0, len(markdown)),
        candidate_ranges=candidate_ranges,
        scan_complete=True,
    )
    validate_scan_plan(plan, markdown)
    return plan
