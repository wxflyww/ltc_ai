from __future__ import annotations

"""Task 8 Step 1-2：四类标准附件安全扫描闭合矩阵（目录识别 + 全文确定性扫描召回）。

本文件只表达正式验收行为，不实现扫描器；扫描能力缺失时在测试体内惰性导入处失败。

闭合矩阵（正式要求 -> 输入 / 扫描计划 -> 候选窗口与坐标 -> 失败边界 -> 稳定性 -> 测试）：

| 正式要求 (spec 7.5 + design 第 10 节) | 输入 / 扫描计划 | 候选窗口与坐标 | 失败边界 | 稳定性 | 测试 |
|---|---|---|---|---|---|
| 首期目录仅需求说明书/技术规范书/工作说明书/质量标准，已批准同义名集为空 | STANDARD_ATTACHMENT_TYPES / APPROVED_STANDARD_ATTACHMENT_ALIASES | - | 目录外名称与近义名不得自动生效 | 目录为确定常量 | test_standard_attachment_directory_is_closed_and_aliases_empty |
| 四类目录各有可靠识别正例（内部身份 + 结构证据 + 无冲突） | build_standard_attachment_scan_plan(documents, document_key) | 计划 standard_type 等于目录类别 | 缺任一条件即回退 | 同输入同判定 | test_each_standard_type_has_reliable_positive |
| 文件名/标题单独命中不足 | build_standard_attachment_scan_plan | - | 返回 None 走普通完整提取 | - | test_name_only_document_does_not_enter_standard_path |
| 上传附件须同时在 source_snapshot.attachments 与 markdown_by_document | build_standard_attachment_scan_plan(documents, document_key) | - | 映射缺失 / 伪造键返回 None | - | test_uploaded_boundary_requires_snapshot_and_markdown |
| 内嵌附件还须 source_locator 主文切片与附件 Markdown 完全一致 | build_standard_attachment_scan_plan(documents, document_key) | scanned_range 覆盖规范化全文 | locator 切片不一致返回 None | - | test_embedded_boundary_requires_matching_locator_slice |
| 补充协议/商务协议/目录外/身份冲突/结构不足回退 | build_standard_attachment_scan_plan | - | 全部返回 None，不得由模型/关键词统计扩充目录 | - | test_out_of_directory_and_conflicting_or_unreliable_fallback |
| 全文扫描覆盖主体定义/称谓、甲乙方义务、签署区、法人/授权人、人员与身份证关系、签署日期、开户银行/账户/户名、地址/电话/传真/网站/邮编 | scan_complete_markdown_for_review_facts(markdown) | 每类标记须落在某个候选窗口的绝对坐标内 | 漏召回即缺口 | 同输入同窗口集合 | test_full_text_scan_recalls_required_fact_categories |
| 输出 0..N 个绝对坐标窗口，scanned_range/candidate_ranges 固定为 MarkdownCharLocator 字符串 | build_standard_attachment_scan_plan -> SafetyScanPlan | 0 <= start <= end <= len(markdown)，scanned_range 覆盖全文 | 越界须失败 | - | test_candidate_windows_are_strict_locators_within_bounds |
| 重叠窗口合并范围，候选数组换序不改变结果 | merge_overlapping_ranges(locators) | 合并为并集坐标 locator | - | 与输入顺序无关且幂等 | test_merge_overlapping_ranges_is_order_independent |
| 单纯技术指标/功能需求/质量指标不得误报为待展开窗口 | scan_complete_markdown_for_review_facts | 无合同事实候选时窗口为空 | - | - | test_scan_does_not_flag_pure_technical_quality_content |
| 可靠扫描无候选时形成"已完整扫描、无局部候选"的合法计划 | build_standard_attachment_scan_plan | candidate_ranges 为空，scan_complete 恒为 True | 技术失败不得伪装为 coverage | - | test_complete_scan_without_candidates_yields_legal_plan |
| 扫描器或坐标校验失败属技术失败，不能伪装为 coverage | validate_scan_plan(plan, markdown) / build_standard_attachment_scan_plan | - | 越界/异常须抛出，不得返回空候选计划 | - | test_scan_or_locator_failure_is_technical_failure_not_coverage |
| 主体定义/称谓与甲乙方义务为各自独立的可识别原文向量 | scan_complete_markdown_for_review_facts | "甲方：某公司" 与 "甲方应/乙方应……" 分别落在候选窗口绝对坐标内 | 以义务句代替主体定义即漏召回 | - | test_subject_definition_and_obligations_are_independent_vectors |
| 扫描入口固定为 (documents, document_key) | inspect.signature(build_standard_attachment_scan_plan) | - | 无 PreparedDocument 单文档入口、boundary_reliable、可变参数或默认重载 | - | test_scan_entry_signature_rejects_legacy_inputs |
| scanned_range/candidate_ranges 强类型 MarkdownCharLocator | SafetyScanPlan(...) / validate_scan_plan(plan, markdown) | 仅接受 markdown-chars:start-end 字符串 | tuple/list/带 start-end 对象须被拒绝，不得兼容转换 | 同输入同拒绝 | test_safety_scan_plan_rejects_non_string_locators |
| 内嵌附件 source_main_document_id 须匹配实际主文身份 | build_standard_attachment_scan_plan(documents, document_key) | - | 身份冲突（即便 locator 切片一致）返回 None，回退普通提取 | - | test_embedded_identity_conflict_falls_back |
| 身份信息完整但缺正文分节结构不得进入标准路径（H1 标题不能替代结构交叉印证） | build_standard_attachment_scan_plan(documents, document_key) | - | 返回 None，回退普通完整提取 | 同输入同判定 | test_identity_complete_without_body_structure_falls_back |
| 任意非同名 H1（如「附件」）不构成正文结构交叉印证；须为通用结构规则而非名称特判 | build_standard_attachment_scan_plan(documents, document_key) | - | 返回 None，回退普通完整提取 | 同输入同判定 | test_identity_complete_with_generic_h1_but_no_body_sections_falls_back |
| 正向层级矩阵：## 至 ###### 正文标题各配非身份正文时均建立扫描计划 | build_standard_attachment_scan_plan(documents, document_key) | standard_type 命中目录，scan_complete 为 True | - | 同输入同判定 | test_body_section_heading_levels_two_to_six_are_accepted |
| 反向结构矩阵：H1、H7+、仅自我身份声明、空正文、仅字段元数据、仅中文编号均不成立 | build_standard_attachment_scan_plan(documents, document_key) | - | 全部返回 None，回退普通完整提取 | 同输入同判定 | test_non_body_structure_forms_fall_back |
| 仅授权合并重叠窗口；端点相接但不相交的窗口保持独立 | merge_overlapping_ranges(locators) | 端点相接的半开区间仍为两个 locator | - | 合并后保持输入顺序稳定 | test_merge_adjacent_ranges_remains_separate |
| 扫描入口 document_key 注解须为既有 DocumentKey 契约，不得为裸 str | inspect.signature(build_standard_attachment_scan_plan, eval_str=True) | - | 裸 str 注解不合规 | 同输入同注解 | test_scan_entry_document_key_annotation_is_document_key_contract |

权威依据：design.md 第 10 节（四类标准附件使用安全扫描）、spec 7.5（四类标准附件只做清单处理、
安全扫描和必要局部提取）、实施计划 Task 8 Step 1-3、DEC-LTC-20260911-002（派生式边界证明 + 强类型 locator）。

入口契约（实施计划 Task 8 Step 3 与 DEC-LTC-20260911-002 声明；Step 1-2 仅消费，不在本批次实现）：
1. 模块 app/capabilities/contract_review/two_stage/long_document.py，当前尚不存在。
2. 目录常量 STANDARD_ATTACHMENT_TYPES（四类）与 APPROVED_STANDARD_ATTACHMENT_ALIASES（当前为空）。
3. 扫描入口 build_standard_attachment_scan_plan(documents: PreparedDocuments, document_key: str)
   -> SafetyScanPlan | None；边界可靠性由 PreparedDocuments 与 document_key 派生，
   不接受旧提取器仅 Markdown 的 PreparedDocument，也不接受 boundary_reliable 参数。
4. 全文扫描入口 scan_complete_markdown_for_review_facts(markdown) 返回绝对坐标 locator，
   合并入口 merge_overlapping_ranges(locators) 与坐标校验入口 validate_scan_plan(plan, markdown)。
5. SafetyScanPlan.scanned_range 与 candidate_ranges 固定为 MarkdownCharLocator 字符串，
   不兼容 tuple、list 或任意带 start/end 的对象；解析只可在先断言字符串 locator 后进行。

本文件在测试体内惰性导入 long_document，因此当前缺失能力时的失败被明确归因为
"标准附件安全扫描能力缺失"，而非收集期导入、fixture 或环境错误；Step 3 实现后同一批断言转为
对真实行为的验收。
"""

import importlib
import inspect
import re

import pytest

from app.capabilities.contract_review.two_stage.documents import PreparedDocuments
from app.capabilities.contract_review.two_stage.evidence import (
    format_markdown_locator,
    parse_markdown_locator,
)
from app.capabilities.contract_review.two_stage.schemas import (
    DocumentKey,
    EmbeddedAttachmentSnapshot,
    MainDocumentSnapshot,
    SourceSnapshot,
    UploadedAttachmentSnapshot,
)


_MODULE_PATH = "app.capabilities.contract_review.two_stage.long_document"
_MISSING = object()

_STANDARD_TYPES = ("需求说明书", "技术规范书", "工作说明书", "质量标准")

_LOCATOR_RE = re.compile(r"^markdown-chars:\d+-\d+$")

# 全文扫描须覆盖的类别与对应标记（标记在样例正文中唯一出现），用于断言绝对坐标覆盖。
_RECALL_VECTORS = (
    ("主体定义/称谓", "甲方：示例科技有限公司"),
    ("甲方义务", "甲方应提供本项目的全部接口说明"),
    ("乙方义务", "乙方应按本标准执行交付"),
    ("签署区", "签署区"),
    ("法人/授权人", "法定代表人：张三"),
    ("人员与身份证关系", "身份证号 110101199001011234"),
    ("签署日期", "签署日期：2026年1月1日"),
    ("开户银行/账户/户名", "开户银行：示例银行"),
    ("地址", "地址：北京市朝阳区示例路1号"),
    ("联系电话", "联系电话：010-12345678"),
    ("传真", "传真：010-87654321"),
    ("网站", "网址：https://example.com"),
    ("邮编", "邮编：100000"),
)


def _module():
    try:
        return importlib.import_module(_MODULE_PATH)
    except ModuleNotFoundError as exc:
        pytest.fail(f"标准附件安全扫描能力缺失: {_MODULE_PATH} 尚未实现 ({exc})")


def _attr(module, name):
    value = getattr(module, name, _MISSING)
    if value is _MISSING:
        pytest.fail(f"标准附件安全扫描能力缺失: {module.__name__}.{name} 尚未实现")
    return value


def _locator_range(locator) -> tuple[int, int]:
    """先断言强类型 MarkdownCharLocator 字符串，再解析为绝对坐标。"""
    assert isinstance(locator, str), f"候选范围必须是 MarkdownCharLocator 字符串, 实际 {locator!r}"
    assert _LOCATOR_RE.match(locator), f"非法 MarkdownCharLocator 字符串: {locator!r}"
    return parse_markdown_locator(locator)


def _main_markdown() -> str:
    """主合同正文（仅作为边界证明来源，不参与标准附件扫描）。"""
    return (
        "# 采购合同\n\n"
        "本采购合同由甲方与乙方签订。\n\n"
        "## 附件一\n"
        "甲方应提供接口说明。\n"
    )


def _standard_markdown(name: str) -> str:
    """具备内部身份（文档名称/编号/版本）与可交叉印证结构的标准附件正文。"""
    return (
        f"# {name}\n\n"
        f"文档名称：{name}\n"
        "文档编号：TS-2026-001\n"
        "版本：V1.0\n\n"
        "## 一、主体定义\n"
        "甲方：示例科技有限公司\n"
        "乙方：示例服务有限公司\n\n"
        "## 二、主体与义务\n"
        "甲方应提供本项目的全部接口说明。\n"
        "乙方应按本标准执行交付。\n\n"
        "## 三、签署区\n"
        "法定代表人：张三\n"
        "授权代表：李四\n"
        "签署日期：2026年1月1日\n\n"
        "## 四、人员与身份\n"
        "项目负责人：王五，身份证号 110101199001011234。\n\n"
        "## 五、账户与联系\n"
        "收款账户名称：示例科技有限公司\n"
        "开户银行：示例银行\n"
        "地址：北京市朝阳区示例路1号\n"
        "联系电话：010-12345678\n"
        "传真：010-87654321\n"
        "网址：https://example.com\n"
        "邮编：100000\n"
    )


def _technical_only_markdown() -> str:
    """内部身份可靠但正文只含技术/功能/质量指标，无合同事实候选。"""
    return (
        "# 技术规范书\n\n"
        "文档名称：技术规范书\n"
        "文档编号：TS-2026-002\n"
        "版本：V2.0\n\n"
        "## 1 技术指标\n"
        "系统支持并发 1000 路，响应时间不超过 200ms。\n\n"
        "## 2 功能需求\n"
        "支持批量导入与导出，支持断点续传。\n\n"
        "## 3 质量指标\n"
        "缺陷率低于 0.1%，可用性不低于 99.9%。\n"
    )


def _source_snapshot(main_markdown, attachments):
    return SourceSnapshot(
        contract_id="c-1",
        revision_id="r-1",
        document_set_hash="sha256:" + "0" * 64,
        main_document=MainDocumentSnapshot(
            document_key="main",
            document_id="doc-main",
            filename="采购合同.md",
            parsed_content_sha256="sha256:" + "0" * 64,
        ),
        attachments=list(attachments),
    )


def _uploaded_snapshot(key: str) -> UploadedAttachmentSnapshot:
    return UploadedAttachmentSnapshot(
        document_key=key,
        source_kind="UPLOADED",
        attachment_id=f"att-{key}",
        filename=f"{key}.md",
        parsed_content_sha256="sha256:" + "0" * 64,
    )


def _embedded_snapshot(key: str, source_locator: str) -> EmbeddedAttachmentSnapshot:
    return EmbeddedAttachmentSnapshot(
        document_key=key,
        source_kind="EMBEDDED",
        source_main_document_id="doc-main",
        source_locator=source_locator,
        title="附件",
        parsed_content_sha256="sha256:" + "0" * 64,
    )


def _prepared(source_snapshot, markdown_by_document) -> PreparedDocuments:
    return PreparedDocuments(
        source_snapshot=source_snapshot,
        markdown_by_document=dict(markdown_by_document),
        preparation_issues=[],
    )


def _uploaded_docs(key: str, markdown: str) -> PreparedDocuments:
    """构造含 main 与该上传附件的合法 PreparedDocuments。"""
    main = _main_markdown()
    return _prepared(
        _source_snapshot(main, [_uploaded_snapshot(key)]),
        {"main": main, key: markdown},
    )


def test_standard_attachment_directory_is_closed_and_aliases_empty():
    """目录只允许四类，且当前已批准同义名集合为空。"""
    module = _module()
    types = _attr(module, "STANDARD_ATTACHMENT_TYPES")
    assert set(types) == set(_STANDARD_TYPES)

    aliases = _attr(module, "APPROVED_STANDARD_ATTACHMENT_ALIASES")
    assert dict(aliases) == {}


@pytest.mark.parametrize("name", _STANDARD_TYPES)
def test_each_standard_type_has_reliable_positive(name):
    """四类目录各有可靠识别正例：内部身份 + 结构交叉印证 + 无冲突即进入标准路径。"""
    module = _module()
    build = _attr(module, "build_standard_attachment_scan_plan")

    markdown = _standard_markdown(name)
    docs = _uploaded_docs("att-std", markdown)

    plan = build(docs, "att-std")
    assert plan is not None
    assert plan.document_key == "att-std"
    assert plan.standard_type == name
    assert plan.scan_complete is True
    assert plan.scanned_range == format_markdown_locator(0, len(markdown))


def test_name_only_document_does_not_enter_standard_path():
    """文件名/标题单独命中不足，回退普通完整提取。"""
    module = _module()
    build = _attr(module, "build_standard_attachment_scan_plan")

    for key, text in (
        ("att-bare-1", "需求说明书\n"),
        ("att-bare-2", "# 技术规范书\n"),
        ("att-bare-3", "质量标准\n"),
    ):
        assert build(_uploaded_docs(key, text), key) is None, key


def test_uploaded_boundary_requires_snapshot_and_markdown():
    """上传附件须同时在 source_snapshot.attachments 与 markdown_by_document 才具扫描资格。"""
    module = _module()
    build = _attr(module, "build_standard_attachment_scan_plan")
    markdown = _standard_markdown("需求说明书")
    main = _main_markdown()

    # 在 markdown_by_document 中但不在 source_snapshot.attachments：不可证明
    only_markdown = _prepared(
        _source_snapshot(main, []), {"main": main, "att-forged": markdown}
    )
    assert build(only_markdown, "att-forged") is None

    # 在 source_snapshot.attachments 中但 markdown 映射缺失：不可证明
    only_snapshot = _prepared(
        _source_snapshot(main, [_uploaded_snapshot("att-missing")]), {"main": main}
    )
    assert build(only_snapshot, "att-missing") is None

    # 映射与快照均无该 document_key：不可证明
    assert build(only_markdown, "att-absent") is None


def test_embedded_boundary_requires_matching_locator_slice():
    """内嵌附件还须 source_locator 对应主文切片与附件 Markdown 完全一致。"""
    module = _module()
    build = _attr(module, "build_standard_attachment_scan_plan")

    segment = _standard_markdown("技术规范书")
    main = "# 采购合同\n\n## 附件一\n" + segment
    start = main.index(segment)
    good_locator = format_markdown_locator(start, start + len(segment))

    good = _prepared(
        _source_snapshot(main, [_embedded_snapshot("att-emb", good_locator)]),
        {"main": main, "att-emb": segment},
    )
    plan = build(good, "att-emb")
    assert plan is not None
    assert plan.standard_type == "技术规范书"

    # locator 指向的主文切片与附件 Markdown 不一致：不可证明
    bad_locator = format_markdown_locator(0, 3)
    assert main[0:3] != segment
    bad = _prepared(
        _source_snapshot(main, [_embedded_snapshot("att-emb", bad_locator)]),
        {"main": main, "att-emb": segment},
    )
    assert build(bad, "att-emb") is None


def test_out_of_directory_and_conflicting_or_unreliable_fallback():
    """补充协议、商务协议、目录外类型、身份冲突与结构不足均回退普通完整提取。"""
    module = _module()
    build = _attr(module, "build_standard_attachment_scan_plan")

    cases = {
        "att-supp": "# 补充协议\n\n文档名称：补充协议\n",
        "att-biz": "# 商务协议\n\n文档名称：商务协议\n",
        "att-novel": _standard_markdown("需求规格说明书"),
        "att-conflict": (
            "# 附件\n\n"
            "文档名称：技术规范书\n"
            "文档编号：TS-2026-003\n\n"
            "## 说明\n"
            "本文档为工作说明书，规定工作范围。\n"
        ),
        "att-nostruct": "技术规范书\n无内部身份与结构。\n",
    }

    for key, text in cases.items():
        assert build(_uploaded_docs(key, text), key) is None, key


def test_identity_complete_without_body_structure_falls_back():
    """身份信息完整（文档名称/编号/版本 + H1 标题）但无正文分节结构时，不得进入标准路径。

    正式依据：实施计划 Task 8 Step 3 与 spec 7.5 要求内部身份、结构交叉印证与无冲突三者同时成立；
    H1 标题不能替代正文分节结构交叉印证。缺任一条件即回退普通完整提取。
    """
    module = _module()
    build = _attr(module, "build_standard_attachment_scan_plan")

    def _identity_only(name: str) -> str:
        return (
            f"# {name}\n\n"
            f"文档名称：{name}\n"
            "文档编号：TS-2026-001\n"
            "版本：V1.0\n"
        )

    for name in _STANDARD_TYPES:
        markdown = _identity_only(name)
        docs = _uploaded_docs("att-identity", markdown)
        # 先证明边界可靠（快照与 Markdown 映射同时存在），使失败只归因于结构判断过宽
        assert any(
            item.document_key == "att-identity" for item in docs.source_snapshot.attachments
        )
        assert "att-identity" in docs.markdown_by_document
        assert build(docs, "att-identity") is None, name


def test_identity_complete_with_generic_h1_but_no_body_sections_falls_back():
    """身份完整但唯一标题是与文档名称不同的泛化 H1（如「附件」）时，仍不得进入标准路径。

    正式依据：design.md 第 10 节要求标准附件资格须「正文结构可交叉印证」；spec 7.5 与
    Task 8 Step 3 要求内部身份、结构交叉印证与无冲突三者同时成立。

    任意非同名 H1 不是正文结构交叉印证：结构证据必须是真正承载正文分节/业务段落的标题，
    不得以「标题不等于文档名称」这类名称特判代替通用结构规则。本用例保留完整身份元数据
    （四类之一的文档名称、文档编号、版本）却无任何真正正文分节。
    """
    module = _module()
    build = _attr(module, "build_standard_attachment_scan_plan")

    def _generic_h1_only(name: str) -> str:
        return (
            "# 附件\n\n"
            f"文档名称：{name}\n"
            "文档编号：TS-2026-004\n"
            "版本：V1.0\n"
        )

    for name in _STANDARD_TYPES:
        markdown = _generic_h1_only(name)
        assert markdown.count("#") == 1, "用例仅允许一个泛化 H1 标题"
        assert f"# {name}" not in markdown, "泛化 H1 不得与文档名称同名"

        docs = _uploaded_docs("att-generic", markdown)
        # 先证明边界可靠（快照与 Markdown 映射同时存在），使失败只归因于结构判断过宽
        assert any(
            item.document_key == "att-generic" for item in docs.source_snapshot.attachments
        )
        assert "att-generic" in docs.markdown_by_document
        assert build(docs, "att-generic") is None, name


_IDENTITY_ONLY_METADATA = (
    "文档名称：需求说明书\n"
    "文档编号：TS-2026-005\n"
    "版本：V1.0\n"
)

# 反向结构矩阵：身份完整（文档名称/编号/版本）但正文结构不成立的样例。
_NON_BODY_STRUCTURE_CASES = {
    # H7+ 不计作正文分节，即便其后有正文
    "h7_heading_with_body": (
        "# 需求说明书\n\n" + _IDENTITY_ONLY_METADATA + "\n"
        "####### 一级标题\n"
        "甲方应提供本项目的全部接口说明。\n"
    ),
    # H2–H6 后仅自我身份声明不构成正文
    "self_identification_only": (
        "# 需求说明书\n\n" + _IDENTITY_ONLY_METADATA + "\n"
        "## 说明\n"
        "本文档为需求说明书\n"
    ),
    # H2–H6 后为空
    "heading_then_empty": (
        "# 需求说明书\n\n" + _IDENTITY_ONLY_METADATA + "\n"
        "## 说明\n\n"
    ),
    # H2–H6 后仅字段式身份元数据
    "heading_then_identity_fields_only": (
        "# 需求说明书\n\n" + _IDENTITY_ONLY_METADATA + "\n"
        "## 身份信息\n" + _IDENTITY_ONLY_METADATA
    ),
    # 仅中文编号段落标题及正文，无 H2–H6
    "chinese_numbered_paragraphs_only": (
        _IDENTITY_ONLY_METADATA + "\n"
        "一、主体定义\n"
        "甲方：示例科技有限公司\n"
    ),
}


@pytest.mark.parametrize("level", (2, 3, 4, 5, 6))
def test_body_section_heading_levels_two_to_six_are_accepted(level):
    """首期正文结构只承认 H2–H6：任意该级别标题后接非身份正文即建立扫描计划。

    正式依据：DEC-LTC-20260911-003 与 design.md 第 10 节的保守 Markdown 正文结构判据；
    H2–H6 任一级别标题后存在非空、非身份元数据正文即满足结构交叉印证。
    """
    module = _module()
    build = _attr(module, "build_standard_attachment_scan_plan")

    markdown = (
        "# 需求说明书\n\n"
        + _IDENTITY_ONLY_METADATA
        + "\n"
        + "#" * level
        + " 主体定义\n"
        + "甲方：示例科技有限公司\n"
    )
    plan = build(_uploaded_docs("att-level", markdown), "att-level")
    assert plan is not None
    assert plan.standard_type == "需求说明书"
    assert plan.scan_complete is True


@pytest.mark.parametrize("case", sorted(_NON_BODY_STRUCTURE_CASES))
def test_non_body_structure_forms_fall_back(case):
    """H1、H7+、自我身份声明、字段元数据、中文编号均不能替代 H2–H6 后的真实非身份正文。

    正式依据：DEC-LTC-20260911-003 与 design.md 第 10 节；首期只准 H2–H6 标题后的真实
    非身份正文构成正文结构交叉印证，其余形态一律回退普通完整提取（返回 None）。
    """
    module = _module()
    build = _attr(module, "build_standard_attachment_scan_plan")

    markdown = _NON_BODY_STRUCTURE_CASES[case]
    docs = _uploaded_docs("att-structure", markdown)
    assert any(
        item.document_key == "att-structure" for item in docs.source_snapshot.attachments
    )
    assert "att-structure" in docs.markdown_by_document
    assert build(docs, "att-structure") is None, case


def test_full_text_scan_recalls_required_fact_categories():
    """全文扫描须召回各类别候选，窗口以绝对坐标覆盖对应类别标记。"""
    module = _module()
    scan = _attr(module, "scan_complete_markdown_for_review_facts")

    markdown = _standard_markdown("需求说明书")
    windows = list(scan(markdown))
    assert windows, "全文安全扫描未召回任何候选窗口"
    ranges = [_locator_range(window) for window in windows]

    for category, marker in _RECALL_VECTORS:
        index = markdown.index(marker)
        covered = any(start <= index < end for start, end in ranges)
        assert covered, f"未覆盖类别 {category}: {marker}"


def test_candidate_windows_are_strict_locators_within_bounds():
    """窗口为 MarkdownCharLocator 字符串、绝对坐标且在文档边界内，scanned_range 覆盖全文。"""
    module = _module()
    build = _attr(module, "build_standard_attachment_scan_plan")

    markdown = _standard_markdown("需求说明书")
    plan = build(_uploaded_docs("att", markdown), "att")
    assert plan is not None

    assert isinstance(plan.scanned_range, str)
    assert _LOCATOR_RE.match(plan.scanned_range)
    assert plan.scanned_range == format_markdown_locator(0, len(markdown))

    assert plan.candidate_ranges, "标准附件正文应至少召回一个候选窗口"
    for locator in plan.candidate_ranges:
        start, end = _locator_range(locator)
        assert 0 <= start <= end <= len(markdown)


def test_merge_overlapping_ranges_is_order_independent():
    """重叠窗口合并为并集坐标，且结果与候选数组顺序无关并幂等。"""
    module = _module()
    merge = _attr(module, "merge_overlapping_ranges")

    forward_input = [
        format_markdown_locator(10, 20),
        format_markdown_locator(15, 30),
        format_markdown_locator(40, 50),
        format_markdown_locator(48, 55),
    ]
    backward_input = list(reversed(forward_input))
    expected = [format_markdown_locator(10, 30), format_markdown_locator(40, 55)]

    forward = list(merge(forward_input))
    backward = list(merge(backward_input))

    for locator in forward:
        _locator_range(locator)
    assert forward == expected
    assert backward == forward
    assert list(merge([])) == []
    assert list(merge(forward)) == expected


def test_merge_adjacent_ranges_remains_separate():
    """仅授权合并重叠窗口；端点相接但不相交的窗口必须保持为两个独立范围。

    正式依据：实施计划 Task 8 Step 3「窗口重叠时合并范围」只覆盖重叠，不覆盖相邻；
    spec 7.5 要求候选窗口保留为规范化 Markdown 的精确半开切片。
    """
    module = _module()
    merge = _attr(module, "merge_overlapping_ranges")

    forward_input = [
        format_markdown_locator(10, 20),
        format_markdown_locator(20, 30),
    ]
    expected = [format_markdown_locator(10, 20), format_markdown_locator(20, 30)]

    forward = list(merge(forward_input))
    backward = list(merge(list(reversed(forward_input))))

    for locator in forward:
        _locator_range(locator)
    assert forward == expected, f"相邻但不重叠的窗口被错误合并: {forward}"
    assert backward == expected, f"换序后相邻窗口合并结果不稳定: {backward}"


def test_scan_does_not_flag_pure_technical_quality_content():
    """单纯技术指标、功能需求、质量指标不得误报为待展开窗口。"""
    module = _module()
    scan = _attr(module, "scan_complete_markdown_for_review_facts")

    assert list(scan(_technical_only_markdown())) == []


def test_complete_scan_without_candidates_yields_legal_plan():
    """可靠标准附件无候选时形成"已完整扫描、无局部候选"的合法计划。"""
    module = _module()
    build = _attr(module, "build_standard_attachment_scan_plan")

    markdown = _technical_only_markdown()
    plan = build(_uploaded_docs("att-tech", markdown), "att-tech")
    assert plan is not None
    assert plan.document_key == "att-tech"
    assert plan.standard_type == "技术规范书"
    assert plan.scan_complete is True
    assert plan.candidate_ranges == []
    assert plan.scanned_range == format_markdown_locator(0, len(markdown))


def test_scan_or_locator_failure_is_technical_failure_not_coverage(monkeypatch):
    """坐标越界与扫描器异常均属技术失败，不得伪装为 coverage 或免检计划。"""
    module = _module()
    build = _attr(module, "build_standard_attachment_scan_plan")
    validate = _attr(module, "validate_scan_plan")
    plan_cls = _attr(module, "SafetyScanPlan")

    markdown = _standard_markdown("需求说明书")

    with pytest.raises(Exception):
        out_of_bounds = plan_cls(
            document_key="att",
            standard_type="需求说明书",
            scanned_range=format_markdown_locator(0, len(markdown)),
            candidate_ranges=[format_markdown_locator(len(markdown), len(markdown) + 5)],
            scan_complete=True,
        )
        validate(out_of_bounds, markdown)

    docs = _uploaded_docs("att", markdown)

    def _boom(_markdown):
        raise RuntimeError("scan backend failure")

    monkeypatch.setattr(module, "scan_complete_markdown_for_review_facts", _boom)
    with pytest.raises(RuntimeError):
        build(docs, "att")


def test_subject_definition_and_obligations_are_independent_vectors():
    """主体定义/称谓与甲乙方义务须为各自独立的可识别原文向量，均被候选窗口绝对坐标覆盖。"""
    module = _module()
    scan = _attr(module, "scan_complete_markdown_for_review_facts")

    markdown = (
        "# 需求说明书\n\n"
        "甲方：示例科技有限公司\n"
        "乙方：示例服务有限公司\n\n"
        "甲方应提供本项目的全部接口说明。\n"
        "乙方应按本标准执行交付。\n\n"
        "## 签署区\n"
        "法定代表人：张三\n"
        "签署日期：2026年1月1日\n"
    )
    ranges = [_locator_range(window) for window in scan(markdown)]
    assert ranges, "全文安全扫描未召回任何候选窗口"

    vectors = (
        ("主体定义/称谓", "甲方：示例科技有限公司"),
        ("甲方义务", "甲方应提供本项目的全部接口说明"),
        ("乙方义务", "乙方应按本标准执行交付"),
    )
    for category, marker in vectors:
        index = markdown.index(marker)
        covered = any(start <= index < end for start, end in ranges)
        assert covered, f"未覆盖 {category}: {marker}"


def test_scan_entry_signature_rejects_legacy_inputs():
    """扫描入口只接受 (documents, document_key)：无单文档入口、boundary_reliable 或可变参数。"""
    module = _module()
    build = _attr(module, "build_standard_attachment_scan_plan")

    signature = inspect.signature(build)
    parameters = list(signature.parameters.values())
    assert [parameter.name for parameter in parameters] == ["documents", "document_key"]
    assert [parameter.kind for parameter in parameters] == [
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ]
    assert all(parameter.default is inspect.Parameter.empty for parameter in parameters)
    assert not any(parameter.name == "boundary_reliable" for parameter in parameters)

    docs = _uploaded_docs("att", _standard_markdown("需求说明书"))
    with pytest.raises(TypeError):
        build(docs)
    with pytest.raises(TypeError):
        build(docs, "att", boundary_reliable=True)


def test_scan_entry_document_key_annotation_is_document_key_contract():
    """扫描入口 document_key 注解必须是既有 DocumentKey 契约，而非裸 str。

    正式依据：实施计划 Task 8 Step 3 与 DEC-LTC-20260911-002 的入口签名声明。
    本测试只新增注解断言，不放宽既有「仅两个无默认参数」的签名要求。
    """
    module = _module()
    build = _attr(module, "build_standard_attachment_scan_plan")

    signature = inspect.signature(build, eval_str=True)
    annotation = signature.parameters["document_key"].annotation
    assert annotation == DocumentKey, (
        f"document_key 注解必须是既有 DocumentKey 契约, 实际 {annotation!r}"
    )
    assert annotation is not str


def test_safety_scan_plan_rejects_non_string_locators():
    """SafetyScanPlan 与 validate_scan_plan 必须拒绝 tuple/list/带 start-end 对象，不得兼容转换。"""
    module = _module()
    plan_cls = _attr(module, "SafetyScanPlan")
    validate = _attr(module, "validate_scan_plan")

    markdown = _standard_markdown("需求说明书")
    full_locator = format_markdown_locator(0, len(markdown))

    class _StartEndRange:
        def __init__(self, start: int, end: int) -> None:
            self.start = start
            self.end = end

    non_string_values = [
        (0, len(markdown)),
        [0, len(markdown)],
        _StartEndRange(0, len(markdown)),
    ]
    for value in non_string_values:
        with pytest.raises(Exception):
            plan_cls(
                document_key="att",
                standard_type="需求说明书",
                scanned_range=value,
                candidate_ranges=[],
                scan_complete=True,
            )
        with pytest.raises(Exception):
            plan_cls(
                document_key="att",
                standard_type="需求说明书",
                scanned_range=full_locator,
                candidate_ranges=[value],
                scan_complete=True,
            )

    forged = plan_cls.model_construct(
        document_key="att",
        standard_type="需求说明书",
        scanned_range=(0, len(markdown)),
        candidate_ranges=[(0, 5)],
        scan_complete=True,
    )
    with pytest.raises(Exception):
        validate(forged, markdown)


def test_embedded_identity_conflict_falls_back():
    """locator 切片一致但 source_main_document_id 与实际主文身份冲突时，仍回退普通完整提取。"""
    module = _module()
    build = _attr(module, "build_standard_attachment_scan_plan")

    segment = _standard_markdown("技术规范书")
    main = "# 采购合同\n\n## 附件一\n" + segment
    start = main.index(segment)
    snapshot = _source_snapshot(
        main,
        [_embedded_snapshot("att-emb", format_markdown_locator(start, start + len(segment)))],
    )
    conflicting_attachment = snapshot.attachments[0].model_copy(
        update={"source_main_document_id": "doc-other"}
    )
    conflicting_snapshot = snapshot.model_copy(
        update={"attachments": [conflicting_attachment]}
    )

    docs = _prepared(conflicting_snapshot, {"main": main, "att-emb": segment})
    assert build(docs, "att-emb") is None
