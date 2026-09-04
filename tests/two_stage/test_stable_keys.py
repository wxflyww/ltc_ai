from app.capabilities.contract_review.two_stage.keys import (
    embedded_document_key,
    evidence_key,
    preparation_issue_key,
    stable_key,
    uploaded_document_key,
)
from app.capabilities.contract_review.two_stage.schemas import EvidenceItem, PreparationIssue


def test_stable_key_same_coordinates_produce_same_value():
    first = stable_key("amount", {"document_key": "main", "start": 10, "end": 20})
    second = stable_key("amount", {"start": 10, "end": 20, "document_key": "main"})

    assert first == second


def test_stable_key_diff_coordinates_produce_different_values():
    first = stable_key("amount", {"document_key": "main", "start": 10, "end": 20})
    second = stable_key("amount", {"document_key": "main", "start": 11, "end": 20})

    assert first != second


def test_stable_key_has_kind_prefix():
    key = stable_key("signature_block", {"document_key": "main", "ordinal": 1})

    assert key.startswith("signature_block:")


def test_stable_key_candidate_array_reorder_does_not_change_key():
    # 直接攻击生产入口：传入无序数组，不依赖测试侧 sorted()
    first = stable_key(
        "signature_block",
        {"document_key": "main", "candidate_party_keys": ["party:a", "party:b"]},
    )
    second = stable_key(
        "signature_block",
        {"document_key": "main", "candidate_party_keys": ["party:b", "party:a"]},
    )

    assert first == second


def test_stable_key_evidence_return_order_does_not_change_key():
    # 直接攻击生产入口：传入无序数组，不依赖测试侧 sorted()
    first = stable_key(
        "amount",
        {"document_key": "main", "evidence_ids": ["evidence:1", "evidence:2"]},
    )
    second = stable_key(
        "amount",
        {"document_key": "main", "evidence_ids": ["evidence:2", "evidence:1"]},
    )

    assert first == second


def test_stable_key_nested_array_reorder_does_not_change_key():
    # 嵌套数组重排同样不改变键
    first = stable_key(
        "signature_block",
        {
            "document_key": "main",
            "groups": [["party:a", "party:b"], ["party:c"]],
        },
    )
    second = stable_key(
        "signature_block",
        {
            "document_key": "main",
            "groups": [["party:c"], ["party:b", "party:a"]],
        },
    )

    assert first == second


def test_stable_key_business_identity_coordinate_change_changes_key():
    # 真正影响业务身份的坐标变化应改变键
    first = stable_key("amount", {"document_key": "main", "start": 10, "end": 20})
    moved = stable_key("amount", {"document_key": "main", "start": 11, "end": 20})

    assert first != moved


def test_stable_key_relation_change_changes_key():
    # 关系变化（如关联的文档/主体变化）应改变键
    first = stable_key(
        "attachment_relation",
        {"attachment_declaration_key": "decl:1", "candidate_document_keys": ["uploaded:att-001"]},
    )
    changed = stable_key(
        "attachment_relation",
        {"attachment_declaration_key": "decl:1", "candidate_document_keys": ["embedded:main:001"]},
    )

    assert first != changed


def test_embedded_document_key_same_business_entity_same_key():
    # 同一业务实体（同一文档 + 位置 + 标题）产生相同键
    first = embedded_document_key("main", 0, 100, "附件一")
    second = embedded_document_key("main", 0, 100, "附件一")

    assert first == second


def test_embedded_document_key_different_position_different_key():
    # 同一标题但不同业务位置 → 不同键
    first = embedded_document_key("main", 0, 100, "附件一")
    moved = embedded_document_key("main", 200, 300, "附件一")

    assert first != moved


def test_uploaded_document_key_same_attachment_same_key():
    first = uploaded_document_key("att-001")
    second = uploaded_document_key("att-001")

    assert first == second


def test_uploaded_document_key_different_attachment_different_key():
    first = uploaded_document_key("att-001")
    second = uploaded_document_key("att-002")

    assert first != second


def test_evidence_key_same_location_same_key():
    first = evidence_key("main", 0, 4)
    second = evidence_key("main", 0, 4)

    assert first == second


def test_evidence_key_different_location_different_key():
    first = evidence_key("main", 0, 4)
    moved = evidence_key("main", 5, 9)

    assert first != moved


def test_preparation_issue_key_document_keys_reorder_same_key():
    # 直接攻击生产入口：document_keys 无序传入，生产代码归一化
    first = preparation_issue_key(
        "SUSPECTED_DUPLICATE",
        "basis",
        ["uploaded:att-001", "embedded:main:001"],
    )
    second = preparation_issue_key(
        "SUSPECTED_DUPLICATE",
        "basis",
        ["embedded:main:001", "uploaded:att-001"],
    )

    assert first == second


def test_preparation_issue_key_different_basis_different_key():
    first = preparation_issue_key("SUSPECTED_DUPLICATE", "basis-a", ["uploaded:att-001"])
    second = preparation_issue_key("SUSPECTED_DUPLICATE", "basis-b", ["uploaded:att-001"])

    assert first != second


def test_stable_key_same_business_position_same_key_across_calls():
    # 同值重复：同一业务坐标在多次调用时始终产生同一键，无随机性
    coordinates = {"document_key": "main", "start": 10, "end": 20}
    first = stable_key("amount", coordinates)
    second = stable_key("amount", coordinates)
    third = stable_key("amount", coordinates)

    assert first == second == third


def test_stable_key_same_normalized_value_different_business_position_different_key():
    # 同值不同业务位置：相同的文档但位置区间不同 → 必须是不同键
    first = stable_key("evidence", {"document_key": "main", "start": 10, "end": 20})
    second = stable_key("evidence", {"document_key": "main", "start": 30, "end": 40})

    assert first != second


def test_stable_key_same_normalized_value_same_business_position_same_key():
    # 同值重复：同一业务位置上的同一规范化值 → 稳定键相同（模型措辞不影响键）
    first = stable_key(
        "amount",
        {"document_key": "main", "start": 10, "end": 20, "normalized_value": "100000"},
    )
    second = stable_key(
        "amount",
        {"document_key": "main", "start": 10, "end": 20, "normalized_value": "100000"},
    )

    assert first == second


def test_stable_key_different_normalized_value_different_key():
    # 异值冲突：同一业务位置但规范化值不同 → 键必须不同
    first = stable_key(
        "amount",
        {"document_key": "main", "start": 10, "end": 20, "normalized_value": "100000"},
    )
    second = stable_key(
        "amount",
        {"document_key": "main", "start": 10, "end": 20, "normalized_value": "200000"},
    )

    assert first != second



# ---------- Task 2 剩余覆盖：2.3 真实模型文案变化向量（业务坐标/规范化值/引用不变，仅改展示文案）----------

def _locator_range(locator):
    body = locator[len("markdown-chars:"):]
    start_s, end_s = body.split("-", maxsplit=1)
    return int(start_s), int(end_s)


def test_evidence_key_ignores_quote_wording():
    # 同一证据位置（document_key + source_locator → start/end），仅模型 quote（展示文案）不同
    # → 经实际类型化入口 evidence_key() 生成的键必须不变。
    locator = "markdown-chars:100-120"
    start, end = _locator_range(locator)

    item_a = EvidenceItem(
        evidence_id="evidence:main:header-name",
        document_key="main",
        source_locator=locator,
        quote="第一条视觉展示文案",
    )
    item_b = EvidenceItem(
        evidence_id="evidence:main:header-name",
        document_key="main",
        source_locator=locator,
        quote="完全不相同的另一句视觉展示文案",
    )

    assert item_a.quote != item_b.quote
    key_with_original_quote = evidence_key(item_a.document_key, start, end)
    key_with_rewritten_quote = evidence_key(item_b.document_key, start, end)

    assert key_with_original_quote == key_with_rewritten_quote
    assert key_with_original_quote.startswith("evidence:")


def test_evidence_key_consumes_location_coordinate_not_quote():
    # 对照：业务位置坐标变化必须改变键，而 quote 变化不得改变键，证明只有坐标进入键。
    start, end = _locator_range("markdown-chars:100-120")
    base = evidence_key("main", start, end)
    moved = evidence_key("main", start + 1, end)

    assert base != moved
    assert base.startswith("evidence:")


def test_preparation_issue_key_ignores_message_wording():
    # 同一 code/basis/related_document_keys（业务坐标 + 引用不变），仅 message（展示消息）不同
    # → 经实际类型化入口 preparation_issue_key() 生成的键必须不变。
    docs = ["uploaded:att-001", "embedded:main:001"]

    issue_a = PreparationIssue(
        preparation_issue_key="preparation_issue:dup-a",
        code="SUSPECTED_DUPLICATE",
        message="第一条展示消息",
        related_document_keys=docs,
        evidence_ids=["evidence:main:header-name"],
    )
    issue_b = PreparationIssue(
        preparation_issue_key="preparation_issue:dup-b",
        code="SUSPECTED_DUPLICATE",
        message="完全不相同的另一句展示消息",
        related_document_keys=docs,
        evidence_ids=["evidence:main:header-name"],
    )

    assert issue_a.message != issue_b.message
    key_message_a = preparation_issue_key(issue_a.code, "basis-normalized", issue_a.related_document_keys)
    key_message_b = preparation_issue_key(issue_b.code, "basis-normalized", issue_b.related_document_keys)

    assert key_message_a == key_message_b
    assert key_message_a.startswith("preparation_issue:")


def test_preparation_issue_key_consumes_document_refs_not_message():
    # 对照：引用集合变化必须改变键，而 message 变化不得改变键，证明只有业务坐标/引用进入键。
    docs = ["uploaded:att-001", "embedded:main:001"]
    other_docs = ["uploaded:att-001"]

    key_msg_a = preparation_issue_key("SUSPECTED_DUPLICATE", "basis", docs)
    key_msg_b = preparation_issue_key("SUSPECTED_DUPLICATE", "basis", docs)
    key_doc_changed = preparation_issue_key("SUSPECTED_DUPLICATE", "basis", other_docs)

    assert key_msg_a == key_msg_b
    assert key_msg_a != key_doc_changed
