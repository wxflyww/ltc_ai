"""预填链路的输入归一化与 prompt 参数构造。只被 prefill 链路使用。"""
from langchain_core.messages import BaseMessage

from app.capabilities.contract_review.prefill_response_formats import SCOPE_GROUPS
from app.capabilities.contract_review.prompts import build_prompt


def normalize_contract_text(text: str) -> str:
    """把「一整行 + 字面量 \\n」形态的正文还原为真换行。

    保守策略：仅当文本内**不含任何真换行**时才替换，避免误改正文里本就存在的字面量 "\\n"。
    """
    if "\n" in text:
        return text
    return text.replace("\\n", "\n")


_SCOPE_SCENARIO = {
    "all": "本次请求两组场景的全部字段",
    "d02": "本次请求 D-02（合同管理员预填）字段",
    "d03": "本次请求 D-03（销售预填）字段",
}


def _scope_note(scope: str) -> str:
    """scope 说明：场景描述写死，**字段组名一律从 `SCOPE_GROUPS` 派生**。

    刻意不写成字面量 —— 否则改动分组归属时（如 2026-09-18 把 finance_info 并入 d02）
    说明文字会悄悄与实际 schema 脱节，而模型只按说明办事。
    """
    groups = SCOPE_GROUPS[scope]
    return f"{_SCOPE_SCENARIO[scope]}，只需返回 {'、'.join(groups)} 共 {len(groups)} 组。"

_FIELDS = {
    "contract_info": """1) contract_info（对象，9 个字段）
   - payment_terms 付款条件：分期与条件条款的整段原文
   - payment_method 付款方式：支付手段（如"电汇"）
   - service_content 服务内容及方式：原文
   - service_valid_months 服务有效期限：**原文写法**（去掉【】等填空标记、保留量纲 —— 【两】年 → 两年；绝不折算成 24 等数字）
   - service_sla 服务级别（SLA）：原文
   - service_start_date 服务开始时间：先按**合同名称**判断是否服务类合同；只从服务/售后/质保条款取，
     且只取绝对日期
   - service_end_date 服务结束时间：**非服务类** —— 规则同上，两者必须同为 null 或同为有值，
     不得用开发完成日等其他日期顶替；**服务类**（名称含 服务/运维/运营/维护/技术支持
     之一；⚠️ 开发/咨询/设计/集成/实施/监理/勘察/检测/评估/外包/培训 **都不算**，「技术开发合同」按非服务类）——
     在上列条款取不到绝对日期时，可取合同自身的完成/交付截止日，
     此时**允许只有本字段有值**。名称看不出、或读不到名称 → 按非服务类处理。
     条款只写"事件起算+期限"（如"自初验合格之日起两年"）时**本字段**返回 null，不得折算成具体日期。⚠️ 这条 null 规则**只作用于 service_start_date / service_end_date 两个时间字段**，不作用于 service_valid_months 等期限/时长字段（「之日起【两】年」→ service_valid_months = 两年）
   - onsite_service_count 现场服务次数：原文写法
   - inspection_count 巡检次数：原文写法""",
    "contract_plan": """2) contract_plan（数组，每个付款阶段一项，每项 8 个字段）
   - milestone_name 里程碑标准名 / milestone_code 对应 code
   - milestone_text 里程碑原文描述 / milestone_seq 阶段序号（整数，从 1 起）
   - payment_amount 回款金额：**金额型字段 —— 去掉货币符号、币种词与千分位，但必须保留 "%"、"万/亿"
     与小数位；不要折算**（原文只写比例时返回该比例，如 "50%"）
     以上四项**只从付款条件（分期与条件条款）里拆** —— 原始里程碑节点与金额都在付款条件。
   - plan_finish_date 计划完成时间：按下列顺序找来源，取到即止
     ① 原文有独立的「合同计划 / 进度计划」章节 → 取该章节里本阶段的预计完成时间
     ② 没有该章节 → 取「交付 / 验收」相关条款里本阶段的完成时间
     ③ 两处都没有 → null
     值一律原文写法：可能是"2026年7月31日"，也可能是"自合同签订之日起120天（自然日）内"。
   - plan_payment_date 计划回款时间：**只**从付款条件里取本阶段对应的时间表述
     （如"初验后15个工作日内"），原文写法；付款条件里没有本阶段的时间表述 → null。
   - ⛔ 这两个时间字段**都不要自己算**：不做日期加减、不把"120天"折成具体日期、
     不用完成时间推算回款时间。算不出就返回 null，推算由调用方完成。
   - evidence：该行全部字段的原文出处，按下列三个出处**各给一条、共 3 条**；每个元素是
     {"section": 顶层条款标题原文或 null, "quote": 原文片段（≤300字）}：
     ① 付款条件（里程碑名称与金额的来源）② 合同计划章节或交付/验收条款（完成时间的来源）
     ③ 合同金额条款
     某一条的 quote 在下面两种情况下都固定写 "无"：(a) 该处出处**在原文里确实不存在**；
     (b) 该处章节**存在、但里面没有该字段需要的内容**（如交付/验收条款只写了验收时限、
     没写本阶段的预计完成时间）。两种都写作 {"section": null, "quote": "无"}，
     **绝不能拿该处章节里不相关的原文片段充当 quote**。只有通读全文确认原文没有该处所需内容
     才能写"无"；抽取困难、看不清、不确定都**不算**"无"。""",
    "finance_info": '''3) finance_info（对象，2 个字段）
   - contract_amount 合同额：**金额型字段 —— 去掉货币符号、币种词与千分位，但必须保留 "%"、"万/亿"
     与小数位；不要折算**。⚠️ **阿拉伯数字与中文大写同时出现时，取阿拉伯数字那一处**
     （如「人民币（大写）：【柒拾陆万叁仟贰佰元整】元。（¥：【763200】元」→ 返回 763200，不是大写）；
     只在原文**通篇只有中文大写、无任何阿拉伯数字**时，才返回该大写原文
   - currency 币种：**ISO 4217 三位大写代码**（人民币→CNY、美元→USD、日元→JPY、欧元→EUR），
     不要返回"人民币"这类原文表述，也不要固定写死某一个代码''',
    "guarantee": """4) guarantee（数组，支持多笔、不设上限，无则 []，每项 7 个字段）
   - type 申请类型：只能取 "履约保函" 或 "履约保证金"
   - amount 申请金额：**金额型字段 —— 去掉货币符号、币种词与千分位，但必须保留 "%"、"万/亿"
     与小数位；不要折算**（原文写"按合同金额的5%收取"时返回 "5%"）
   - payee 收款单位/受益人 / bank_name 银行名称 / bank_account 银行账号（甲方开户信息）
   - return_clause 归还条款：原文
   - evidence：同 contract_plan 的 evidence 结构""",
}

_EXAMPLES = {
    "contract_info": '{"contract_info": {"payment_terms": null, "payment_method": null, '
                     '"service_content": null, "service_valid_months": null, "service_sla": null, '
                     '"service_start_date": null, "service_end_date": null, '
                     '"onsite_service_count": null, "inspection_count": null}}',
    "contract_plan": '{"contract_plan": [{"milestone_name": "启动", "milestone_code": "begin", '
                     '"milestone_text": "合同签订及预付款", "milestone_seq": 1, '
                     '"plan_finish_date": "2026年1月20日", '
                     '"plan_payment_date": "签订生效后10个工作日内", "payment_amount": "30%", '
                     '"evidence": [{"section": "第四条 付款方式及条件", '
                     '"quote": "签订生效后10个工作日内支付合同总金额的30%"}, '
                     '{"section": "第五条 合同计划", "quote": "1 启动 预计完成时间：2026年1月20日"}, '
                     '{"section": "第三条 合同金额", '
                     '"quote": "合同总金额为人民币 ¥3,860,000.00 元"}]}]}',
    # 下面的 "CNY" 只是 JSON 示例值，**不代表该字段固定为 CNY**（币种随合同变化，见 _FIELDS）
    "finance_info": '{"finance_info": {"contract_amount": null, "currency": "CNY"}}',
    "guarantee": '{"guarantee": [{"type": "履约保证金", "amount": null, "payee": null, '
                 '"bank_name": null, "bank_account": null, "return_clause": null, '
                 '"evidence": [{"section": "第八条 履约保证金", "quote": "按合同金额的5%收取"}]}]}',
}


def _json_example(scope: str) -> str:
    """按 scope 组装示例：单组直接返回该组示例，多组拼成一个合法 JSON 对象。

    注意 scope 名（all/d02/d03）与组名（contract_info/…）不是一回事，
    必须经 SCOPE_GROUPS 映射后再取 _EXAMPLES。
    """
    groups = SCOPE_GROUPS[scope]
    if len(groups) == 1:
        return _EXAMPLES[groups[0]]
    inner = ", ".join(_EXAMPLES[name].strip()[1:-1] for name in groups)
    return "{" + inner + "}"


def prefill_prompt_kwargs(scope: str, contract_md: str) -> dict:
    """构造 `build_prompt("prefill", **kwargs)` 所需的全部模板变量。

    真实链路（prefill_service）与测试（build_prefill_messages）共用这一处，
    保证「测到的就是跑到的」。
    """
    groups = SCOPE_GROUPS[scope]
    return {
        "field_spec": "\n\n".join(_FIELDS[name] for name in groups),
        "json_example": _json_example(scope),
        "top_level_keys": "、".join(groups),
        "scope_note": _scope_note(scope),
        "contract_md": contract_md,
    }


def build_prefill_messages(scope: str, contract_md: str) -> list[BaseMessage]:
    return build_prompt("prefill", **prefill_prompt_kwargs(scope, contract_md))
