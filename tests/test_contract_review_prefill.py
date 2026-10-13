import pytest

from app.capabilities.contract_review.prefill_prompts import normalize_contract_text


def test_normalize_single_line_with_literal_backslash_n():
    raw = "第一条 总则\\n第二条 付款方式\\n（一）合同签订后支付30%"
    assert normalize_contract_text(raw) == "第一条 总则\n第二条 付款方式\n（一）合同签订后支付30%"


def test_normalize_keeps_text_with_real_newlines_untouched():
    raw = "第一条 总则\n第二条 付款方式\n"
    assert normalize_contract_text(raw) == raw


def test_normalize_is_idempotent():
    once = normalize_contract_text("甲\\n乙")
    assert normalize_contract_text(once) == once


from app.capabilities.contract_review.prefill_schemas import PrefillData, PrefillPayload


def test_prefill_payload_defaults_are_all_null_and_empty():
    payload = PrefillPayload()
    assert payload.contract_info.payment_terms is None
    assert payload.contract_info.inspection_count is None
    assert payload.contract_plan == []
    assert payload.finance_info.contract_amount is None
    assert payload.guarantee == []


def test_prefill_payload_has_exactly_four_top_level_keys():
    assert list(PrefillPayload().model_dump().keys()) == [
        "contract_info",
        "contract_plan",
        "finance_info",
        "guarantee",
    ]


def test_prefill_data_failed_keeps_full_structure():
    data = PrefillData(prefill_status="failed")
    dumped = data.model_dump()
    assert dumped["mode"] == "prefill"
    assert dumped["prefill_status"] == "failed"
    assert dumped["prefill"]["contract_plan"] == []
    assert dumped["prefill"]["guarantee"] == []


def test_prefill_evidence_requires_quote_allows_null_section():
    from app.capabilities.contract_review.prefill_schemas import PrefillEvidence

    assert PrefillEvidence(quote="合同签订后7个工作日内").section is None
    assert PrefillEvidence(section="第四条 付款方式及条件", quote="…").section == "第四条 付款方式及条件"


from app.capabilities.contract_review.prefill_response_formats import (
    SCOPE_GROUPS,
    get_prefill_response_format,
    get_prefill_top_level_keys,
)

_EXPECTED = {
    "contract_info": [
        "payment_terms", "payment_method", "service_content", "service_valid_months",
        "service_sla", "service_start_date", "service_end_date",
        "onsite_service_count", "inspection_count",
    ],
    "contract_plan": [
        "milestone_name", "milestone_code", "milestone_text", "milestone_seq",
        "plan_finish_date", "plan_payment_date", "payment_amount", "evidence",
    ],
    "finance_info": ["contract_amount", "currency"],
    "guarantee": [
        "type", "amount", "payee", "bank_name", "bank_account", "return_clause", "evidence",
    ],
}


def _schema_of(scope: str) -> dict:
    return get_prefill_response_format(scope)["json_schema"]["schema"]


def test_scope_groups_match_with_design():
    assert SCOPE_GROUPS["d02"] == ("contract_info", "contract_plan", "finance_info")
    assert SCOPE_GROUPS["d03"] == ("finance_info", "guarantee")
    assert SCOPE_GROUPS["all"] == ("contract_info", "contract_plan", "finance_info", "guarantee")
    assert get_prefill_top_level_keys("d03") == ["finance_info", "guarantee"]


def test_finance_info_is_shared_by_d02_and_d03():
    """`finance_info`（合同总额 + 币种）同属两个场景 —— 2026-09-18 定的口径。

    D-02 的 `contract_plan[].payment_amount` 多为比例（如 "50%"），消费方必须有合同总额才能折算，
    所以该组按「基础信息」归属，两个场景都返回。删掉 d02 里的 finance_info 即回归本缺陷。
    """
    assert "finance_info" in SCOPE_GROUPS["d02"]
    assert "finance_info" in SCOPE_GROUPS["d03"]
    assert set(SCOPE_GROUPS["d02"]) | set(SCOPE_GROUPS["d03"]) == set(SCOPE_GROUPS["all"])
    assert "contract_amount" in _schema_of("d02")["properties"]["finance_info"]["properties"]

    from app.capabilities.contract_review.prefill_prompts import build_prefill_messages

    d02_text = "".join(m.content for m in build_prefill_messages("d02", "正文"))
    assert "finance_info" in d02_text
    assert "contract_amount" in d02_text


def test_scope_note_is_derived_from_scope_groups():
    """scope 说明里的组名必须从 `SCOPE_GROUPS` 派生，不能写死。

    写死的话，改分组归属时说明文字会**悄悄与实际 schema 脱节**——模型只按说明办事，
    schema 里有 finance_info 但说明里不提，模型照样不抽。
    """
    from app.capabilities.contract_review.prefill_prompts import _scope_note

    for scope in ("all", "d02", "d03"):
        note = _scope_note(scope)
        for group in SCOPE_GROUPS[scope]:
            assert group in note, f"{scope} 的 scope_note 漏了 {group}"
        assert str(len(SCOPE_GROUPS[scope])) in note


def test_schema_scope_only_exposes_requested_groups():
    assert list(_schema_of("d02")["properties"].keys()) == [
        "contract_info", "contract_plan", "finance_info",
    ]
    assert list(_schema_of("d03")["properties"].keys()) == ["finance_info", "guarantee"]
    assert list(_schema_of("all")["properties"].keys()) == [
        "contract_info", "contract_plan", "finance_info", "guarantee",
    ]
    assert _schema_of("d02")["required"] == ["contract_info", "contract_plan", "finance_info"]


def test_schema_fields_match_design_field_list_exactly():
    props = _schema_of("all")["properties"]
    assert list(props["contract_info"]["properties"].keys()) == _EXPECTED["contract_info"]
    assert list(props["contract_plan"]["items"]["properties"].keys()) == _EXPECTED["contract_plan"]
    assert list(props["finance_info"]["properties"].keys()) == _EXPECTED["finance_info"]
    assert list(props["guarantee"]["items"]["properties"].keys()) == _EXPECTED["guarantee"]


_VERBATIM_FIELDS = {
    "contract_info": [
        "service_valid_months", "onsite_service_count", "inspection_count",
        "service_start_date", "service_end_date",
    ],
    "contract_plan": ["payment_amount", "plan_finish_date", "plan_payment_date"],
    "finance_info": ["contract_amount"],
    "guarantee": ["amount"],
}


def test_only_milestone_seq_is_not_a_string():
    """取值契约：除 milestone_seq 外不得再出现 JSON number。

    一旦声明成 number，模型为了满足 JSON 语法就必须去掉货币符号与千分位、
    并按类型补齐或截断小数位 —— 那是**语法约束冒充业务约束**，是本机加工误差的来源。
    """
    props = _schema_of("all")["properties"]
    for group, fields in _VERBATIM_FIELDS.items():
        node = (
            props[group]["items"]["properties"]
            if group in ("contract_plan", "guarantee")
            else props[group]["properties"]
        )
        for name in fields:
            assert node[name]["type"] == ["string", "null"], f"{group}.{name}"
    seq = props["contract_plan"]["items"]["properties"]["milestone_seq"]
    assert seq["type"] == ["integer", "null"]


def test_verbatim_fields_keep_the_original_wording():
    """金额 / 日期保留原文写法：货币符号、千分位、比例、非 ISO 日期一律照抄，不换算。"""
    dumped = PrefillPayload.model_validate({
        "contract_info": {"service_start_date": "2025年3月1日", "service_valid_months": "13.5个月"},
        "contract_plan": [{"milestone_seq": 1, "payment_amount": "10492500.00"}],
        "finance_info": {"contract_amount": "¥4690000元"},
        "guarantee": [{"amount": "5%"}],
    }).model_dump()
    assert dumped["contract_info"]["service_start_date"] == "2025年3月1日"
    assert dumped["contract_info"]["service_valid_months"] == "13.5个月"
    assert dumped["contract_plan"][0]["payment_amount"] == "10492500.00"
    assert dumped["finance_info"]["contract_amount"] == "¥4690000元"
    assert dumped["guarantee"][0]["amount"] == "5%"


def test_model_emitted_number_is_stringified_not_failed():
    """兜底：模型违反 strict schema 吐数字时按原值字符串化，不让 26 个字段一起降级 failed。"""
    payload = PrefillPayload.model_validate({
        "contract_info": {"service_valid_months": 13},
        "finance_info": {"contract_amount": 10492500.0},
    })
    assert payload.contract_info.service_valid_months == "13"
    assert payload.finance_info.contract_amount == "10492500.0"


def test_evidence_is_object_array_with_section_and_quote():
    evidence = _schema_of("all")["properties"]["contract_plan"]["items"]["properties"]["evidence"]
    assert evidence["type"] == "array"
    assert list(evidence["items"]["properties"].keys()) == ["section", "quote"]


def test_evidence_quote_max_length_is_300():
    """quote 长度上限 60 → 300（第十二轮）。上限放宽是供给侧的承诺，两组共用同一份。

    这个值此前没有任何断言（tasks.md §9 把它记为自动化缺口），而它同时是发给模型的
    strict 约束，改错就等于悄悄改了 prompt 的行为面，所以钉死。
    """
    from app.capabilities.contract_review.prefill_response_formats import EVIDENCE_SCHEMA

    assert EVIDENCE_SCHEMA["properties"]["quote"]["maxLength"] == 300
    schema = _schema_of("all")["properties"]
    for group in ("contract_plan", "guarantee"):
        quote = schema[group]["items"]["properties"]["evidence"]["items"]["properties"]["quote"]
        assert quote["maxLength"] == 300
        # 仍然是可空字符串 —— 放宽上限不应改变类型
        assert quote["type"] == ["string", "null"]


def test_schema_is_strict_and_named_per_scope():
    for scope in ("all", "d02", "d03"):
        fmt = get_prefill_response_format(scope)
        assert fmt["type"] == "json_schema"
        assert fmt["json_schema"]["strict"] is True
        assert fmt["json_schema"]["name"] == f"contract_review_prefill_{scope}"


def test_get_prefill_response_format_returns_independent_copies():
    first = get_prefill_response_format("all")
    first["json_schema"]["schema"]["properties"]["contract_info"]["properties"]["payment_terms"] = {}
    assert _schema_of("all")["properties"]["contract_info"]["properties"]["payment_terms"] != {}


def test_prefill_prompt_renders_for_every_scope():
    from app.capabilities.contract_review.prefill_prompts import build_prefill_messages

    for scope in ("all", "d02", "d03"):
        messages = build_prefill_messages(scope, "第一条 总则")
        assert len(messages) == 2
        text = messages[1].content
        assert "第一条 总则" in text
        for key in get_prefill_top_level_keys(scope):
            assert key in text


def test_prefill_prompt_carries_the_time_source_rules():
    """两个时间字段的来源规则必须落在 prompt 里 —— 这是第十一轮的口径契约，删掉即回归。"""
    from app.capabilities.contract_review.prefill_prompts import build_prefill_messages

    text = "".join(m.content for m in build_prefill_messages("d02", "第一条 总则"))
    for phrase in ("plan_finish_date", "plan_payment_date", "合同计划", "交付", "不要自己算"):
        assert phrase in text


def test_prefill_prompt_renders_literal_braces_once():
    """user 模板要过 `.format()`：模板里的 `{{...}}` 必须还原成单个 `{...}`。

    踩坑记录：模板里写裸的 `{"section": ...}` 会让 `.format()` 去找名为 "section" 的
    占位符并抛 KeyError；`run_prefill` 的兜底又把异常吞成 `prefill_status=failed`，
    于是**一次 prompt 手误会静默降级成整份预填失败**。这条断言把坑钉死。
    """
    from app.capabilities.contract_review.prefill_prompts import build_prefill_messages

    text = "".join(m.content for m in build_prefill_messages("d02", "正文"))
    assert '{"section": null, "quote": "无"}' in text
    assert "{{" not in text


def test_prefill_prompt_carries_amount_symbol_strip_rules():
    """金额型字段的**删集与留集**必须落在 prompt 里（2026-10-03 第十五轮口径）。

    最关键的是**留集**：`%` 与「万 / 亿」必须在场。若 prompt 被写成"去除非数字字符"，
    `"50%"` 会退化成 `"50"`、「46.9万」会被折算 —— 都属语义灾难。删掉这些短语即回归。
    """
    from app.capabilities.contract_review.prefill_prompts import build_prefill_messages

    text = "".join(m.content for m in build_prefill_messages("all", "正文"))
    for phrase in (
        "去掉货币符号",
        "千分位",
        "payment_amount",
        "contract_amount",
        '不能变成"50"',
        '不能变成"469000"',
    ):
        assert phrase in text, phrase
    # 旧口径的反向断言：prompt 里不得再出现"不去掉符号"
    assert "不要去掉符号" not in text


def test_prefill_prompt_carries_fill_in_blank_marker_rule():
    """`【】` 填空标记的边界规则必须落在 prompt 里。

    背景：同一份合同里，模型对同一个 `【】` 形态给出 4 种互不相同的取值方式，
    「…之日起【两】年」被抽成 `"两"`（丢单位）。根因是**规则缺失**，不是模型能力问题。
    """
    from app.capabilities.contract_review.prefill_prompts import build_prefill_messages

    text = "".join(m.content for m in build_prefill_messages("d02", "正文"))
    assert "【】" in text
    assert "【两】年" in text
    assert "两年" in text
    assert "裸数字" in text or "裸量词" in text


def test_prefill_prompt_carries_service_date_source_rule():
    """服务日期的来源必须限定在服务 / 售后 / 质保条款，且只认绝对日期。

    背景：`service_end_date` 曾被填成履行期限条款里的开发完成日 —— 在**非服务类**合同下
    这是误抓（判据：起止不成对）。
    """
    from app.capabilities.contract_review.prefill_prompts import build_prefill_messages

    text = "".join(m.content for m in build_prefill_messages("d02", "正文"))
    for phrase in ("service_start_date", "service_end_date", "质保", "绝对日期", "事件起算"):
        assert phrase in text, phrase


def test_prefill_prompt_scopes_signing_date_prohibition_to_start_only():
    """「不得用合同签订日顶替」**只约束 `service_start_date`**，不约束 `service_end_date`。

    用户定案（2026-10-12，第十九轮）：东软《技术服务合同》里「2.技术服务期限： 2026年9月4日」
    既是**服务条款内的绝对日期**、又与**签订日同日**。此前模型把"不得用签订日顶替"**误用到了
    `service_end_date`** → 漏抽（返回 `null`）。规则本意：禁令只作用于 start；end 只要**取值来源
    在服务条款内**就应返回，与它是否等于签订日无关。

    ⚠️ 历史误框：我曾把它判为"两条规则冲突、需业务方拍板"，实为**模型误用限制**（详见第十九轮修订记录）。
    下面的断言把"作用域"钉在 prompt 上，防止再次被误读。
    """
    from app.capabilities.contract_review.prefill_prompts import build_prefill_messages

    text = "".join(m.content for m in build_prefill_messages("d02", "正文"))
    flat = text.replace(" ", "").replace("\n", "").replace("*", "")

    # 正向：禁令必须被明确限定在 start 上
    assert "只约束service_start_date" in flat
    assert "不约束" in flat
    # 正向：必须给出"与签订日同日仍应返回"的情形（用本合同真实值）
    assert "2026年9月4日" in flat
    assert "签订日" in flat
    # 正向：判据必须是"来源是否在服务条款内"，而非"是否等于签订日"
    assert "来源是否在服务条款内" in flat
    # 正向（§19.8）：单一日期形态必须被显式处置 —— 该日期只作 end、start 保持 null
    assert "单一绝对日期" in flat
    assert "只作service_end_date" in flat
    assert "service_start_date保持null" in flat
    # 反向：必须禁止"把同一日期对称填充进 start"的读法
    assert "对称" in flat


def test_prefill_prompt_carries_contract_type_rule():
    """合同类型必须由**合同名称**判定，且**读不到名称时按非服务类**兜底。

    用户口径（2026-10-05）：判据从宽 —— 能识别就按服务类；识别不出按非服务类走。
    服务类合同允许 `service_end_date` 取合同自身的完成 / 交付截止日。

    用户口径（2026-10-07，两轮收窄）：按**软件公司的服务类合同**缩小范围 ——
    服务性质词只剩 服务 / 运维 / 运营 / 维护 / 技术支持 这 5 个；
    开发 / 咨询 / 设计 / 集成 / 实施 / 监理 / 勘察 / 检测 / 评估 / 外包 / 培训 为**反例**。
    ⚠️ 但反例词**没有否决权**：名称含「服务」二字仍判服务类（如「集成服务合同」）。

    ⚠️ 历史坑（2026-10-05）：词表**曾误收「开发」** → 「技术开发合同」被误判为服务类，
    连带把它的「开发完成日」合法化成 `service_end_date`（= 把一条真缺陷洗成合法）。
    下面的正向/反向断言把这个坑钉住，防止有人再把反例词加回正向词表。
    """
    from app.capabilities.contract_review.prefill_prompts import build_prefill_messages

    text = "".join(m.content for m in build_prefill_messages("d02", "正文"))
    for phrase in ("合同名称", "服务类", "非服务类", "读不到合同名称", "完成 / 交付截止日"):
        assert phrase in text, phrase

    flat = text.replace(" ", "").replace("\n", "").replace("*", "")

    # 正向：5 个服务性质词必须作为词表出现（两轮收窄后的定稿清单）
    assert "服务/运维/运营/维护/技术支持" in flat

    # 反向断言 ①：11 个反例词必须被**显式点名**（而不是简单删掉），且写成否定式
    assert "都不算" in flat
    for word in ("开发", "咨询", "设计", "集成", "实施", "监理", "勘察", "检测", "评估", "外包", "培训"):
        assert word in flat, word
    # 反向断言 ②：「技术开发合同」按非服务类必须写明
    assert "技术开发合同" in flat
    # 反向断言 ③：反例词没有否决权 —— 含「服务」的复合名仍判服务类，必须写明
    assert "集成服务合同" in flat
    # 反向断言 ④：旧词表形态不得复活（反例词曾被并列在正向词表里）
    assert "运维/运营/咨询" not in flat
    assert "服务/运维/运营/咨询" not in flat
    assert "外包/维护/技术支持/实施" not in flat
    assert "实施/集成/培训" not in flat
    assert "技术支持/外包/培训" not in flat


def test_prefill_prompt_carries_payment_terms_trigger_clause():
    """`payment_terms` = **完整的付款触发条件句**，起算锚点必须一并取到。

    用户定案（2026-10-12，第十八轮）：付款触发条件 = 【起算锚点】+【期限】+【付款动作】，
    锚点可为 时间 / 交付 / 验收 / **发票** 四类，**同等对待** —— 不存在"含不含发票"这个维度。

    ⚠️ 历史坑：我曾把疑点框成「`payment_terms` 是否应包含发票条款」（= 付款条件句 vs
    钱流转全部约定的伪二分）。实则「收到增值税专用发票后 30 日内付款」整句**本身就是一个
    付款触发条件**，「收到发票」与「终验合格」语法同构，都是**起算锚点**。

    判定含发票文字是否属触发条件**只看前置/后置**：
      - 前置型（「收到发票后…付款」）= 锚点 → 取；
      - 后置型（「收到付款后开票」）= 付款之后的义务 → 不取。
    下面的正向/反向断言把该口径钉住，防止旧表述（"整段原文"）复活。
    """
    from app.capabilities.contract_review.prefill_prompts import build_prefill_messages

    text = "".join(m.content for m in build_prefill_messages("d02", "正文"))
    flat = text.replace(" ", "").replace("\n", "").replace("*", "")

    # 正向：口径核心句必须出现
    assert "完整的付款触发条件句" in flat
    # 正向：四类起算锚点必须显式列举（时间 / 交付 / 验收 / 发票）
    for anchor in ("合同生效后", "交付验收后", "终验合格后", "收到发票后"):
        assert anchor in flat, anchor
    # 正向：前置/后置判据必须写明
    assert "前置" in flat and "后置" in flat
    # 正向：非触发条件的排除项必须写明
    assert "银行账号" in flat

    # 反向断言：旧的"整段原文"口径不得复活
    assert "分期与条件条款的整段原文" not in flat


def test_prefill_request_has_no_contract_type_field():
    """请求参数里**没有**合同类型字段 —— 类型只能由服务端从合同名称推断。

    这条钉住设计前提：若将来有人往请求里加 `contract_type`，本测试会红，
    提醒他同步改 prompt（否则该参数会被静默忽略、与响应值不一致）。
    """
    from app.capabilities.contract_review.schemas import ContractReviewRequest as _Req

    fields = set(_Req.model_fields)
    assert "contract_type" not in fields
    assert fields == {"contract_md", "attachments", "mode", "prefill_scope"}


def test_prefill_prompt_carries_currency_iso_rule():
    """`currency` 归一为 ISO 4217，且必须写明**不固定为某一取值**。

    踩坑记录：曾据文档措辞误判该字段恒为 `"CNY"`（实为按合同币种变化）——
    这条断言把"不固定"钉在 prompt 上。
    """
    from app.capabilities.contract_review.prefill_prompts import build_prefill_messages

    text = "".join(m.content for m in build_prefill_messages("d03", "正文"))
    for phrase in ("ISO 4217", "CNY", "USD", "JPY", "不要固定写死"):
        assert phrase in text, phrase


def test_prefill_prompt_carries_evidence_third_state():
    """`evidence` 的**第三种态**必须写在 prompt 里：该处章节存在、但不含所需事实。"""
    from app.capabilities.contract_review.prefill_prompts import build_prefill_messages

    text = "".join(m.content for m in build_prefill_messages("d02", "正文"))
    assert "确实不存在" in text
    assert "没有该字段需要的内容" in text
    assert "不能拿该处章节里不相关的原文片段充当 quote" in text


def test_prefill_amount_rule_reaches_every_scope():
    """金额规则写在共用的 system 段里，故三个 scope 都看得到。

    防的是将来把规则挪进 `_FIELDS` 后漏组 —— 那样 `d03`（只含 finance_info + guarantee）
    就会拿不到规则，而 `d02` 仍然正常，属**静默的半失效**。
    """
    from app.capabilities.contract_review.prefill_prompts import build_prefill_messages

    for scope in ("all", "d02", "d03"):
        text = "".join(m.content for m in build_prefill_messages(scope, "正文"))
        assert "去掉货币符号" in text, scope
        assert "ISO 4217" in text, scope


def test_currency_schema_max_length_is_three():
    """`currency` 口径为 ISO 4217 三位码，schema 上限由 8 收紧为 3（2026-10-05）。"""
    schema = get_prefill_response_format("d03")["json_schema"]["schema"]
    currency = schema["properties"]["finance_info"]["properties"]["currency"]
    assert currency["maxLength"] == 3
    assert currency["type"] == ["string", "null"]


from app.capabilities.contract_review.schemas import ContractReviewRequest


def test_request_defaults_to_review_mode():
    req = ContractReviewRequest(contract_md="正文")
    assert req.mode == "review"
    assert req.prefill_scope == "all"


def test_request_accepts_prefill_scope_values():
    for scope in ("all", "d02", "d03"):
        assert ContractReviewRequest(contract_md="正文", mode="prefill", prefill_scope=scope).prefill_scope == scope


from unittest.mock import patch

from app.capabilities.contract_review.prefill_service import run_prefill


def _request(scope="all", md="正文"):
    return ContractReviewRequest(contract_md=md, mode="prefill", prefill_scope=scope)


def _ok_payload():
    """模拟当前取值口径下模型的输出：除 `milestone_seq` 外一律字符串。

    默认口径为原文原样；**三个金额型字段例外 —— 已剥离货币符号与千分位**
    （2026-10-03 第十五轮），故 `contract_amount` 用 `"10492500.00"` 而非 `"¥10,492,500.00"`。
    服务端对取值**零加工**，下面的断言校验的正是**原样透传**。
    """
    return {
        "contract_info": {"payment_terms": "分期", "payment_method": "电汇"},
        "contract_plan": [
            {"milestone_name": "终验", "milestone_seq": 3, "payment_amount": "10%"},
            {"milestone_name": "启动", "milestone_seq": 1, "payment_amount": "50%"},
        ],
        "finance_info": {"contract_amount": "10492500.00", "currency": "CNY"},
        "guarantee": [{"type": "履约保证金", "amount": "5%"}],
    }


def test_run_prefill_all_returns_four_groups_ok():
    with patch("app.capabilities.contract_review.prefill_service._invoke_json_prompt", return_value=_ok_payload()):
        data = run_prefill(_request("all"))
    dumped = data.model_dump()
    assert dumped["prefill_status"] == "ok"
    assert dumped["prefill"]["finance_info"]["contract_amount"] == "10492500.00"
    assert dumped["prefill"]["contract_plan"][0]["payment_amount"] == "50%"
    assert dumped["prefill"]["guarantee"][0]["amount"] == "5%"
    assert len(dumped["prefill"]["guarantee"]) == 1


def test_run_prefill_d03_blanks_unrequested_groups():
    with patch("app.capabilities.contract_review.prefill_service._invoke_json_prompt", return_value=_ok_payload()):
        dumped = run_prefill(_request("d03")).model_dump()
    assert dumped["prefill"]["contract_info"]["payment_terms"] is None
    assert dumped["prefill"]["contract_plan"] == []
    assert dumped["prefill"]["finance_info"]["currency"] == "CNY"


def test_run_prefill_d02_keeps_contract_amount_but_blanks_guarantee():
    """d02 必须带回合同总额（用于把 payment_amount 的比例折算成金额），但保证金属 d03。"""
    with patch("app.capabilities.contract_review.prefill_service._invoke_json_prompt", return_value=_ok_payload()):
        dumped = run_prefill(_request("d02")).model_dump()
    assert dumped["prefill"]["finance_info"]["contract_amount"] == "10492500.00"
    assert dumped["prefill"]["finance_info"]["currency"] == "CNY"
    assert dumped["prefill"]["guarantee"] == []
    assert dumped["prefill"]["contract_plan"][0]["payment_amount"] == "50%"


def test_run_prefill_d02_asks_model_for_three_groups():
    with patch("app.capabilities.contract_review.prefill_service._invoke_json_prompt", return_value=_ok_payload()) as mocked:
        run_prefill(_request("d02"))
    kwargs = mocked.call_args.kwargs
    assert kwargs["required_keys"] == ["contract_info", "contract_plan", "finance_info"]
    assert kwargs["response_format"]["json_schema"]["name"] == "contract_review_prefill_d02"


def test_run_prefill_sorts_plan_by_milestone_seq():
    with patch("app.capabilities.contract_review.prefill_service._invoke_json_prompt", return_value=_ok_payload()):
        dumped = run_prefill(_request("d02")).model_dump()
    assert [row["milestone_seq"] for row in dumped["prefill"]["contract_plan"]] == [1, 3]


def test_run_prefill_asks_model_for_scope_specific_schema_and_keys():
    with patch("app.capabilities.contract_review.prefill_service._invoke_json_prompt", return_value=_ok_payload()) as mocked:
        run_prefill(_request("d03"))
    kwargs = mocked.call_args.kwargs
    assert kwargs["required_keys"] == ["finance_info", "guarantee"]
    assert kwargs["response_format"]["json_schema"]["name"] == "contract_review_prefill_d03"


def test_run_prefill_normalizes_newlines_before_prompt():
    captured = {}

    def fake(prompt_name, **kwargs):
        captured.update(kwargs)
        return _ok_payload()

    with patch("app.capabilities.contract_review.prefill_service._invoke_json_prompt", side_effect=fake):
        run_prefill(_request("d03", md="第一条 总则\\n第二条 付款"))
    assert captured["contract_md"] == "第一条 总则\n第二条 付款"


def test_run_prefill_returns_failed_on_model_error():
    with patch(
        "app.capabilities.contract_review.prefill_service._invoke_json_prompt",
        side_effect=RuntimeError("boom"),
    ):
        dumped = run_prefill(_request("all")).model_dump()
    assert dumped["prefill_status"] == "failed"
    assert dumped["prefill"]["contract_plan"] == []
    assert dumped["prefill"]["finance_info"]["contract_amount"] is None


def _client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app(register_middleware=False))


def test_router_routes_prefill_by_mode():
    with patch("app.capabilities.contract_review.router.run_prefill") as prefill, patch(
        "app.capabilities.contract_review.router.review_contract"
    ) as review:
        prefill.return_value = PrefillData(prefill_status="ok")
        _client().post("/api/v1/contract-review", json={"contract_md": "正文", "mode": "prefill"})
    assert prefill.call_count == 1
    assert review.call_count == 0


def test_router_keeps_review_path_for_default_mode():
    from app.capabilities.contract_review.schemas import CheckItem, ContractReviewData

    fake = ContractReviewData(
        overall_result="PASS",
        check_time="2026-09-16T10:00:00",
        checks=[CheckItem(id="序号1", name="合同首页完整性", result="PASS", block_level="通过")],
    )
    with patch("app.capabilities.contract_review.router.review_contract", return_value=fake) as review, patch(
        "app.capabilities.contract_review.router.run_prefill"
    ) as prefill:
        _client().post("/api/v1/contract-review", json={"contract_md": "正文"})
    assert review.call_count == 1
    assert prefill.call_count == 0


def test_prefill_response_data_has_only_three_keys():
    with patch("app.capabilities.contract_review.router.run_prefill", return_value=PrefillData(prefill_status="ok")):
        body = _client().post(
            "/api/v1/contract-review", json={"contract_md": "正文", "mode": "prefill"}
        ).json()
    assert body["code"] == 0
    assert set(body["data"].keys()) == {"mode", "prefill_status", "prefill"}
    assert body["data"]["mode"] == "prefill"
    assert set(body["data"]["prefill"].keys()) == {
        "contract_info", "contract_plan", "finance_info", "guarantee",
    }


def test_prefill_response_never_contains_review_keys():
    with patch("app.capabilities.contract_review.router.run_prefill", return_value=PrefillData(prefill_status="failed")):
        body = _client().post(
            "/api/v1/contract-review", json={"contract_md": "正文", "mode": "prefill"}
        ).json()
    for key in ("overall_result", "check_time", "checks", "metrics"):
        assert key not in body["data"]
    assert body["data"]["prefill_status"] == "failed"


def test_prefill_scope_d03_returns_blank_unrequested_groups():
    with patch("app.capabilities.contract_review.router.run_prefill", return_value=PrefillData(prefill_status="ok")):
        body = _client().post(
            "/api/v1/contract-review",
            json={"contract_md": "正文", "mode": "prefill", "prefill_scope": "d03"},
        ).json()
    assert body["data"]["prefill"]["contract_plan"] == []
    assert body["data"]["prefill"]["contract_info"]["payment_terms"] is None


def test_review_response_shape_is_unchanged_and_has_no_mode_key():
    from app.capabilities.contract_review.schemas import CheckItem, ContractReviewData

    fake = ContractReviewData(
        overall_result="PASS",
        check_time="2026-09-16T10:00:00",
        checks=[CheckItem(id="序号1", name="合同首页完整性", result="PASS", block_level="通过")],
    )
    with patch("app.capabilities.contract_review.router.review_contract", return_value=fake):
        body = _client().post("/api/v1/contract-review", json={"contract_md": "正文"}).json()
    assert set(body["data"].keys()) == {"overall_result", "check_time", "checks", "metrics"}
    assert "mode" not in body["data"]


def test_invalid_mode_returns_10001():
    response = _client().post(
        "/api/v1/contract-review", json={"contract_md": "正文", "mode": "review_prefill"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == 10001


def test_invalid_prefill_scope_returns_10001():
    response = _client().post(
        "/api/v1/contract-review", json={"contract_md": "正文", "mode": "prefill", "prefill_scope": "d01"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == 10001


def test_prefill_ignores_attachments():
    with patch("app.capabilities.contract_review.router.run_prefill", return_value=PrefillData(prefill_status="ok")):
        response = _client().post(
            "/api/v1/contract-review",
            json={
                "contract_md": "正文",
                "mode": "prefill",
                "attachments": [{"filename": "附件一.md", "text": "附件正文"}],
            },
        )
    assert response.status_code == 200


def test_prefill_call_carries_strict_schema_and_thinking_off():
    from app.capabilities.contract_review import service as svc

    seen = {}

    def fake_invoke(model, messages, response_format=None):
        seen["model"] = model
        seen["response_format"] = response_format
        return ('{"finance_info": {"contract_amount": "¥1.00", "currency": "CNY"}, "guarantee": []}', {})

    with patch("app.capabilities.contract_review.service.invoke_model", fake_invoke):
        run_prefill(_request("d03"))

    assert seen["response_format"]["json_schema"]["strict"] is True
    assert seen["response_format"]["json_schema"]["name"] == "contract_review_prefill_d03"
    assert seen["model"].kwargs.get("extra_body") == {"chat_template_kwargs": {"enable_thinking": False}}


def test_prefill_requires_all_scope_top_level_keys():
    from app.capabilities.contract_review.service import _invoke_json_prompt
    from app.core.errors import ModelFormatError

    with patch(
        "app.capabilities.contract_review.service.invoke_model",
        return_value=('{"finance_info": {"contract_amount": "¥1.00", "currency": "CNY"}}', {}),
    ):
        with pytest.raises(ModelFormatError):
            _invoke_json_prompt(
                "prefill",
                required_keys=["finance_info", "guarantee"],
                response_format=get_prefill_response_format("d03"),
                field_spec="x", json_example="y", top_level_keys="a", scope_note="z",
                contract_md="正文",
            )


def test_prefill_prompt_carries_twentieth_round_rules():
    """第二十轮（2026-10-12）口径全部落到 prompt：Q2 / Q4 / Q6 / Q7 / Q8 / Q9 / Q10 + A1 / A2。

    背景：东软 + 26年运维两合同复核暴露 9 项问题，业务方（吴钢/王晓丽）+ 用户逐条定案：
      - Q2   `evidence.section` 必须**逐字照抄**原文标题（含原文空格与标点，不规范化）；
      - Q4①  `service_valid_months` **按语义取**（2026-10-13 补正）：「合同（的）有效期 / 本合同有效期为 N 年」**计入**、服务类合同尤其；仍**排除**质保期 / 保修期 / 缺陷责任期 / 保密期；⚠️ 字段名 `months` 仅为命名，**不折算为月数**；
      - Q4②  `inspection_count` 接受**频次表述**且**整句保留**（不是只写数字）；
      - Q7   服务期以**起止区间**给出 → `service_valid_months` 返回 null，**不推算**；
      - Q6   与主句并列、直接约束"能否付款"的条款**应一并取入** `payment_terms`；
      - Q8   `guarantee.type` 新增 **"预付款保函"**（金额等于预付款额者）；
      - Q9   `payment_method` **原文原样**（含主语 / 修饰词，不得精简）；
      - Q10  多阶段付款**全部取**、按原文顺序拼接；
      - A1   金额 / 比例数值**逐字照抄本合同原文**，禁套示例值 / 行业惯例（示例值已从 "5%" 改掉）；
      - A2   `payment_terms` 取句**保留完整主语**、不得截断。

    断言把口径钉在 prompt 上，防止回退。
    """
    from app.capabilities.contract_review.prefill_prompts import build_prefill_messages

    text = "".join(m.content for m in build_prefill_messages("all", "正文"))
    flat = text.replace(" ", "").replace("\n", "").replace("*", "")

    # Q2：section 逐字照抄（含空格/标点）
    assert "逐字照抄" in flat
    assert "含原文的空格与标点" in flat
    # 反向：诱导规范化的旧示例「第四条 付款方式及条件」（带空格、无冒号）不得复活
    assert "第四条 付款方式及条件" not in text

    # Q4① / Q7：service_valid_months 按语义取（含「合同有效期」）、排除质保期类、区间不推算、不折算月数
    assert "按语义取" in flat
    assert "本合同有效期为两年" in flat
    assert "质保期" in flat and "缺陷责任期" in flat
    assert "绝不由区间推算" in flat
    assert "绝不折算成月数" in flat
    # 反向护栏：原文就是"13.5个月"时照抄，不得改写成"1年" —— 换算双向禁止
    assert "两个方向都不许换算" in flat
    assert "13.5个月" in flat
    # Q4②：inspection_count 频次表述整句保留
    assert "整句保留" in flat
    assert "每周1次系统运行情况检查" in flat

    # Q6：约束付款的并列条款也要取
    assert "约束付款的并列条款" in flat
    # Q10：多阶段全部取
    assert "多阶段付款必须全部取" in flat
    # Q8：预付款保函
    assert "预付款保函" in flat
    # Q9：payment_method 原文原样（含主语/修饰词，不提炼、不编造）
    assert "甲方自带汇票/电汇/支票" in flat
    assert "转账方式" in flat
    assert "绝不凭示例或常识编造" in flat
    # A1：数值逐字照抄原文；且 amount 示例值不再是 5%
    assert "逐字照抄本合同原文" in flat
    assert "按合同金额的5%收取" not in text
    # A2：取句保留完整主语
    assert "取句必须保留完整主语" in flat


def test_guarantee_type_enum_includes_prepayment_bond():
    """`guarantee.type` 取值集合 —— Q8（2026-10-12）放宽 + 第三轮补充（2026-10-13）扩至保函种类表全量。

    Q8：新增「预付款保函」（金额 = 预付款额、挂付款条款者）。
    第三轮补充：扩为 `履约保函` / `履约保证金` / `预付款保函` / `投标保函` / `质量保函` /
    `质保保函` / `支付保函` —— 覆盖业务方「保函种类表」全部类型（表内「质量·质保保函」为
    `质量保函` / `质保保函` 两种、说明相同）；`履约保证金` 表内无此项，按合同实务常见概念保留。

    属取值集合放宽 —— 不新增字段、不改名、不改字段集合、不改类型（仍是 string|null）。
    ⚠️ 下游若对 type 做严格枚举解析，需同步认知**全部**新增值。
    """
    from app.capabilities.contract_review.prefill_response_formats import get_prefill_response_format

    rf = get_prefill_response_format("d03")
    enum = (
        rf["json_schema"]["schema"]["properties"]["guarantee"]["items"]
        ["properties"]["type"]["enum"]
    )
    assert enum == [
        "履约保函", "履约保证金", "预付款保函",
        "投标保函", "质量保函", "质保保函", "支付保函",
        None,
    ]


def test_prefill_prompt_carries_third_round_rules():
    """第三轮复核定案（2026-10-13）落到 prompt：Q3/B7 里程碑命名 + B-1 保函 type 判别 + A3 负向。

    背景：吉林银行 + 中汇两合同复核；业务方给出「保函种类表」并答复里程碑口径：
      - Q3 / B7  里程碑命名 —— 付款条件**无成果物**约定 → 视为**预付款** → 取 `启动(begin)`；
                 **有成果物** → 按成果物取 `交付(deliver)` 或 `验收`；`contract_plan`
                 **只从付款条件拆**，不得自造无付款金额的收尾 / 验收项；
      - B-1      保函 `type` 按**保函种类表**判别（担保时间段 / 核心保障 / 常见金额），
                 预付款保函 = 金额等于预付款额、挂付款条款作预付款前提；**不得默认归履约保函**；
      - A3       **违约责任 / 违约赔偿 / 违约金**条款**不构成担保** —— 无独立担保条款时 `guarantee` 必须 `[]`。

    断言把口径钉在 prompt 上，防止回退。
    """
    from app.capabilities.contract_review.prefill_prompts import build_prefill_messages

    text = "".join(m.content for m in build_prefill_messages("all", "正文"))
    flat = text.replace(" ", "").replace("\n", "").replace("*", "")

    # Q3 / B7：里程碑命名口径（无成果物 → 预付款 → 启动）
    assert "里程碑命名口径" in flat
    assert "成果物" in flat
    assert "视为预付款" in flat
    assert "不得自行追加" in flat
    assert "收尾" in flat

    # B-1：保函 type 判别按保函种类表，且禁默认归履约保函
    assert "保函种类表" in flat
    assert "担保时间段" in flat
    assert "预付款可追回" in flat
    assert "不得默认归「履约保函」" in flat

    # A3：违约金 / 赔偿金不构成担保
    assert "违约赔偿" in flat
    assert "不属于保函或保证金" in flat
    assert "凭空生成" in flat


def test_prefill_prompt_carries_guarantee_type_catalog():
    """第三轮补充（2026-10-13）：`guarantee.type` 扩到「保函种类表」全量 + 实务保留值，落到 prompt。

    业务方口径：
      - 表内「质量·质保保函」实为 **质量保函 / 质保保函** 两种（说明相同）；
      - `履约保证金`（表内无此项）按**合同实务常见概念**保留；
      - d03 实际命中 `履约保函` / `履约保证金` **两种**；`预付款保函` 与其余各类**地位相同**，均为**兼容覆盖**。

    反向断言：旧的「其余种类不在本字段可选值内 / 取值集合是否扩充待业务方确认」表述不得复活。
    """
    from app.capabilities.contract_review.prefill_prompts import build_prefill_messages

    text = "".join(m.content for m in build_prefill_messages("all", "正文"))
    flat = text.replace(" ", "").replace("\n", "").replace("*", "")

    # 新增四类取值均出现在 prompt 的 type 判别里
    for value in ("投标保函", "质量保函", "质保保函", "支付保函"):
        assert value in flat, value
    # 履约保证金按实务常见概念保留
    assert "履约保证金" in flat
    assert "实务常见概念" in flat
    # 反向断言：不再把这些类型声明为「不可作为取值 / 待业务方确认」
    assert "不在本字段可选值内" not in flat
    assert "取值集合是否扩充待业务方确认" not in flat
