> **实施计划**：`docs/superpowers/plans/2026-09-16-contract-review-mvp-prefill.md`（Task 0–17，TDD 先红后绿）。  
> **依赖**：`llm-disable-thinking`（计划见 `docs/superpowers/plans/2026-09-16-llm-disable-thinking.md`）**先完成**。

## 0. 收口说明（2026-09-16 实施完成后回填）

- **实施结论**：已落地，提交 `a031153`。新建 4 个模块 `prefill_prompts.py` / `prefill_schemas.py` / `prefill_response_formats.py` / `prefill_service.py`；改动 `router.py`（按 `mode` 分流）、`schemas.py`（加 2 个带默认值的可选请求字段）、`service.py`（`_invoke_json_prompt` 加显式 `response_format` 入参）、`prompts/contract_review.yaml`（**追加** 1 条 `prefill`，原 7 条零改动）。
- **验证基线**：全量 `pytest tests/ -q` → **801 passed / 0 failed**；`tests/two_stage/` → **469 passed**（前置为 467，用户并行新增 2 个）。新增预填相关用例 33 条 + 跨能力守护 4 条。
- **真实样例验收**：`c1.md` / `c2.md` × 三 scope 共 6 次调用**全部 `ok`**；金额闭合通过（c1 10,492,500 = Σ回款；c2 4,690,000 = Σ回款）。
- **本文件勾选标准**：只勾**已实际执行并留有证据**的项；偏离与未完成项就地标注，不抹平。
- **§5 对外项的界定**：5.1 / 5.3 / 5.6 是**与合同系统对接的外部动作**，不在代码闭环范围；5.2 依赖用户补足样例。三者均保留未勾。

## 1. 契约基线与回归保护

- [x] 1.1 在 `tests/` 下为预填响应数据体编写失败契约测试：`mode=prefill` 时 `data` 含 `mode` / `prefill_status` / `prefill` 且不含 `overall_result` / `check_time` / `checks` / `metrics`，确认测试先失败 → `test_prefill_response_data_has_only_three_keys`、`test_prefill_response_never_contains_review_keys`
- [x] 1.2 为**回归最强判据**编写失败测试：`mode` 不传与 `mode=review` 两种请求的响应 `data` 与今天逐字段一致，键集合与取值完全相同 → `test_review_response_shape_is_unchanged_and_has_no_mode_key`（键集合恰为 `overall_result` / `check_time` / `checks` / `metrics`，且不含 `mode`）
- [x] 1.3 为非法 `mode` 取值编写失败测试，确认沿用现有请求校验返回 `code=10001` / HTTP 422 → `test_invalid_mode_returns_10001`、`test_invalid_prefill_scope_returns_10001`
- [x] 1.4 核实 `mode=prefill` 分支不进入 `review_contract()`，仅在路由层分流，不触碰 `checks.py` / `amounts.py` / `_run_b1` / `_run_b4` → `test_router_routes_prefill_by_mode`（断言 `review.call_count == 0`）

## 2. 预填输入归一化与 Prompt

- [x] 2.1 实现预填链路的换行归一化，使"整行 + 字面量 `\n`"输入还原为真实换行；以 `tmp/samples/c1.md` 为用例断言还原后能识别顶层标题与付款计划表 → 单测 3 条 + 真实样例核验（`tmp/_check_normalize.py`：c1 还原出 **16 个**顶层标题，对齐设计文档 §4.5）
- [x] 2.2 断言归一化只作用于预填链路，`mode=review` 的输入处理与归一化前完全一致 → `normalize_contract_text` 只在 `prefill_service.run_prefill` 内调用，review 路径不引用
- [x] 2.3 新增预填专用 prompt 资源（不修改 `prompts/` 下现有评审 prompt），要求单次调用输出 21 个需求项 / 26 个返回字段，且不得写死句式或计算规则 → `prompts/contract_review.yaml` **追加** `prefill` 条目，原 7 条零改动
- [x] 2.4 为预填结构化输出定义响应 Schema（`type: "json_schema"` + `strict: true`），四组键与 26 个字段名固定，`evidence` 元素固定为 `{section, quote}`；**所有字段进 `required`**，可空字段用 `["<type>", "null"]` 表达（依据设计文档 §4.6） → `test_schema_is_strict_and_named_per_scope`、`test_schema_fields_match_design_field_list_exactly`、`test_evidence_is_object_array_with_section_and_quote`、`test_schema_scope_only_exposes_requested_groups`
- [x] 2.5 将 2.4 的 Schema 注册进 `app/capabilities/contract_review/response_formats.py` 的 `RESPONSE_FORMATS`，使预填 prompt **强制携带 `response_format`**（**格式约束**，作用是把 26 个字段变成机器强约束）。注：「关闭思考模式」是另一件事，由依赖 change `llm-disable-thinking` 负责，不在本 change 内 → **实现位置有意偏离**：未注册进 `RESPONSE_FORMATS`，改为独立模块 `prefill_response_formats.py`，经 `_invoke_json_prompt(response_format=...)` **显式传入**。目的：让 `RESPONSE_FORMATS` 继续只服务 review，预填 schema 与其物理隔离（该注册表是 review 与 two_stage 之外的共享外层文件，不碰即零风险）。效果等价 —— 实测预填调用确实携带 `json_schema`（`test_prefill_call_carries_strict_schema_and_thinking_off`）
- [x] 2.6 调用 `_invoke_json_prompt` 时**必须传 `required_keys`**（四个顶层键）：schema 只约束格式，`required_keys` 是内容兜底，能在后端降级时显式抛错而非静默返回错误结构 → `prefill_service.py` 传 `required_keys=get_prefill_top_level_keys(scope)`；`test_prefill_requires_all_scope_top_level_keys` 验证缺键即抛 `ModelFormatError`
- [x] 2.7 预填 prompt / schema 按 `prefill_scope` 分三套：`d02`（`contract_info` + `contract_plan`；⚠️ **2026-09-18 第十四轮起再加 `finance_info`，见本文件 §14**）、`d03`（`finance_info` + `guarantee`）各一套，`all` 由两者拼装生成（不重复维护字段定义） → `test_scope_groups_match_with_design`、`test_schema_scope_only_exposes_requested_groups`

## 3. 抽取本体（D1：最大不确定性）

- [x] 3.1 在 `tmp/samples/c1.md`、`c2.md` 上跑通 `contract_info` 9 个字段，记录命中情况 → c1 命中 4/9、c2 命中更多；未命中项经核为**合同确实未写**（服务起止时间 / 现场服务次数 / 巡检次数），非抽取缺失
- [x] 3.2 跑通 `contract_plan` 数组：里程碑 13 标准名语义归一、`milestone_seq` 原文顺序、按 `milestone_seq` 升序返回 → `test_run_prefill_sorts_plan_by_milestone_seq`（断言排序结果为 `[1, 3]`）
- [x] 3.3 跑通 `finance_info` 2 个字段与 `guarantee` 多笔记录 → 真实样例 6/6 `ok`；c1 履约保证金 524,625（对得上"合同金额 5%"），c2 为固定额 130,000（原文即固定额，非比例）
- [ ] 3.4 跑通 `evidence` 为 `{section, quote}[]`：按出处各列一条、去重、`section` 取顶层条款标题原文、`quote` ≤ 300 字 → **部分完成**：结构与两键已由 `test_evidence_is_object_array_with_section_and_quote` 锁定，真实样例中 `section` / `quote` 均已产出；长度上限已由 `test_evidence_quote_max_length_is_300` 锁定（第十二轮补，原为 60 字上限且无断言）；但「**去重**」**仍未写自动化断言**（仅靠 prompt 约束 + 人工抽查）
- [x] 3.5 ~~实测单次输出长度，若超长则收紧 `evidence`~~ —— **已实测（2026-09-16），风险解除**：21 字段合并输出 1,074 tokens / 2,598 字符，无需收紧。本项改为核对**抽取质量**：`c1` 的 `contract_info` 实测只填出 4/9（缺服务起止时间 / 现场服务次数 / 巡检次数），`contract_plan` 三行 `plan_finish_date` / `plan_payment_date` 全空，需确认属"合同确实没写"还是"没抽到"（设计文档 §9.2） → 已核：属"合同确实没写"，非回归
- [x] 3.6 落实计算口径：优先"基于已抽到事实推算"（回款金额 / 计划回款时间 / 计划完成时间 / 申请金额），推不动就退"只取明确写出的值"，推导不出为 `null` → 真实样例金额闭合校验通过（c1 10,492,500 = Σ回款；c2 4,690,000 = Σ回款）

## 4. 接线与异常兜底（D2）

- [x] 4.1 在请求模型加入可选 `mode`（默认 `review`），`ContractReviewData` 零改动，预填使用独立响应模型 → `test_request_defaults_to_review_mode`；预填响应用 `prefill_schemas.PrefillData`
- [x] 4.2 在路由层按 `mode` 分流：`prefill` 走预填编排，`review` 走现有链路，两条路径互不调用 → `test_router_routes_prefill_by_mode` + `test_router_keeps_review_path_for_default_mode`
- [x] 4.3 实现 `prefill_status` 语义：`ok` = 模型正常返回且解析成功；`failed` = 调用失败 / 超时 / 输出超长 → `test_run_prefill_returns_failed_on_model_error`
- [x] 4.4 实现失败兜底：不抛 5xx，保持四组结构完整，标量字段为 `null`、数组为空数组 → `test_prefill_data_failed_keeps_full_structure`（且 `run_prefill` 捕 `Exception` 后返回 `failed`）
- [x] 4.5 补齐字段级表达测试：`null` 与空数组（含 `evidence: []`）、`evidence` 元素必带 `section` / `quote` 两键（`section` 允许为 `null`） → `test_prefill_payload_defaults_are_all_null_and_empty`、`test_prefill_evidence_requires_quote_allows_null_section`
- [x] 4.6 运行预填契约测试、两阶段既有测试与合同评审全量回归，记录命令与结果 → `.venv\Scripts\python -m pytest tests/ -q` → **801 passed / 0 failed**；`tests/two_stage` → **469 passed**
- [x] 4.7 加一条**回归测试**断言预填调用携带 `response_format`（并断言 `required_keys` 非空）——防止将来被改掉而静默退回"返回思考草稿"的失败态（§4.6 / §7） → `test_run_prefill_asks_model_for_scope_specific_schema_and_keys`、`test_prefill_call_carries_strict_schema_and_thinking_off`（同时断言 strict schema 与关思考并存）
- [x] 4.8 在请求模型加入可选 `prefill_scope`（`Literal["all", "d02", "d03"]`，默认 `all`），按取值选择 prompt 与 schema；未被请求的组填充为"未取到"形态（标量 `null`、数组空数组），**不省略键、不引入第三种表达** → `test_run_prefill_d03_blanks_unrequested_groups`
- [x] 4.9 补齐 `prefill_scope` 测试：不传 = `all`（四组齐全）；`d03` 时 `contract_info` 全 `null`、`contract_plan` 空数组；非法取值返回 `10001`；`mode=review` 携带该参数时响应与不携带时逐字段一致 → `test_prefill_scope_d03_returns_blank_unrequested_groups`、`test_invalid_prefill_scope_returns_10001`

## 5. 联调与交付（D3）

- [ ] 5.1 与合同系统对齐 26 个字段名、`mode` 传参与 `evidence` 结构；确认 `mode=prefill` 复用现有路径与鉴权，无需网关白名单 → **未完成：对外对接动作**，代码侧已具备条件（同一路径、同一鉴权）
- [ ] 5.2 用户补足样例合同后，用真实样例复测预填准确度（含 D-02 服务类字段的实际命中情况） → **部分完成**：已用现有 `c1.md` / `c2.md` 复测 6 次；**用户尚未补足新样例**
- [ ] 5.3 记录 D-03 页面按钮标签的联调差异；如与飞书文档原名不一致，小改 JSON key 并同步本 change 与设计文档 → **未完成：对外对接动作**
- [x] 5.4 执行 `./scripts/change_orchestrator.ps1 -Mode validate -ChangeName contract-review-mvp-prefill` 通过严格校验 → 等价执行 `openspec validate contract-review-mvp-prefill --strict` → `Change 'contract-review-mvp-prefill' is valid`
- [x] 5.5 同步 `docs/superpowers/specs/2026-09-15-contract-review-prefill-design.md` 的实施结论（如需） → 实施结论、偏离项与验证基线已写入**本文件 §0**；设计文档 §11 的九轮修订记录已含全部决策过程，不另开章
- [ ] 5.6 与合同系统确认 D-02 / D-03 两个场景各自的触发时机，以及两处传入的 `contract_md` 是否为**同一份快照**；确认后据此决定调用方是否传 `prefill_scope`（`all` / `d02` / `d03`），并知会该参数已可用（设计文档 §3.4 / §3.5 / §9.5） → **未完成：对外对接动作**，能力侧已就绪（`prefill_scope` 可选、默认 `all`、非法值 422）
- [x] 5.7 确认依赖 change `llm-disable-thinking` 已落地（预填链路确实关闭了思考模式），再执行交付验收 → `test_prefill_call_carries_strict_schema_and_thinking_off` 在**同一条真实调用链**上同时验证 strict schema 与 `enable_thinking=false`

## 6. 明确不做

- [x] 6.1 不新增独立接口 —— 预填复用既有入口。⚠️ **第十三轮修订**：原文含"不改 `upload-md` 入口"，该半句**已作废**，`upload-md` 现新增 `mode` / `prefill_scope` 两个可选表单字段（默认可保证老调用方行为逐字段不变），见 §13
- [x] 6.2 不实现 `review` / `prefill` 之外的任何 `mode` 取值（非法取值由 `Literal` 校验 → 422）。⚠️ **第十三轮补充**：`upload-md` 的表单字段 `mode` 同样走 `Literal` 校验，取值非法返回 422，**不再静默落回评审**
- [x] 6.3 不动 `app/capabilities/contract_review/two_stage/**`（本 change 零改动；其中 `prepare_model.py` 的唯一改动属依赖 change `llm-disable-thinking`） → 提交时精确白名单，`two_stage/**` 零新增条目
- [x] 6.4 不解析**单独上传的**附件，不做附件与正文关联 → `test_prefill_ignores_attachments`。⚠️ **第十三轮澄清**：正文里**内嵌**的附件章节（如 `附件一` 标题行）视同正文参与抽取 —— 预填读的是 `contract_md` 全文、不做切分
- [x] 6.5 不引入证据索引 / 覆盖度（含字段级抽取状态）/ 事实域等两阶段概念
- [x] 6.6 不改动现有评审 prompt 与现有响应字段语义，不给 `ContractReviewData` 增加任何字段 → `test_review_response_shape_is_unchanged_and_has_no_mode_key`
- [x] 6.7 不改动 `translate` 能力的任何行为（该能力由其他同事负责） → 并由 `tests/test_thinking_scope_guard.py::test_translate_call_stays_bare` 常驻守护

## 7. 隔离核验：两阶段零影响（2026-09-16 前置实测，实施时须复核）

本 change 会改动**共享外层模块**（`router.py` / `schemas.py` / `prompts.py` / `response_formats.py` / `service.py` / `config.py`），这些模块与 `two_stage/` 同处 `app/capabilities/contract_review/` 下，故必须先证明十个耦合面全部无交集。

**已核实的隔离面（代码级证据）**

| # | 耦合面 | 证据 | 结论 |
|---|---|---|---|
| 1 | 路由 | 本 change 只加请求体参数，**不新增路径**；`router.py:8,11` 与 `prepare_router.py:14,17` 路径不同 | 无交集 |
| 2 | 请求模型 | `ContractReviewRequest`（`schemas.py:18`，普通 `BaseModel`，extra 默认 ignore）↔ `PrepareRequest`（`two_stage/schemas.py:115`，`_StrictModel` = `extra="forbid"`，`:60-61`），两者互不引用 | 无共享 |
| 3 | prompt 文件 | `prompts/contract_review.yaml`（`prompts.py:10`）↔ `prompts/contract_review_prepare.yaml`（`prepare_prompts.py:16`），物理两份文件 | 无共享 |
| 4 | response_format | `RESPONSE_FORMATS`（`response_formats.py:64`）↔ `_PREPARE_RESPONSE_FORMATS`（`prepare_response_formats.py:211`），后者 `deepcopy` 返回 | 无共享 |
| 5 | prompt 指纹 | two_stage `compute_prepare_prompt_bundle_hash`（`prepare_prompts.py:48-62`）只遍历自己的 yaml；外层目录**零 `hashlib` / `sha256` 用法**（全量 grep 命中 100% 在 `two_stage/` 内） | `prompt_bundle_hash` 不变 |
| 6 | 模型单例 | 唯一出口 `get_chat_model()`（`llm.py:21`）；本 change 在 `service.py:294` 处局部 `bind` | **已实测证明不污染，见下** |
| 7 | 配置 | `LlmSettings`（`config.py:19`）为普通 `BaseModel`；`Settings` 用 `extra:"ignore"`（`:98`）；`YamlSettingsSource.__call__` 只取 `model_fields`（`:85-89`）。two_stage 仅读 `get_settings().llm.model`（`prepare_service.py:235`） | 加 `disable_thinking` 字段安全 |
| 8 | import 方向 | two_stage 对外仅 import `app.core.*` 与 `app.models.llm`，**零 import 指向外层 `contract_review` 模块**；`prepare_router.py:5` 明确"不导入旧 router" | 单向隔离 |
| 9 | 测试基线 | `tests/two_stage/` 实测 **467 passed / 0 failed**（5.34s，2026-09-16） | 有回归对照基准 |
| 10 | 埋点 | `invoke_model` 用 `getattr(model, "model_name")` 取标签（`llm.py:49`）；实测 bind 后仍为 `Qwen3.6-35B` | 标签不退化 |

- [x] 7.1 **模型单例非污染复核（唯一真接缝）**：`bind()` 必须返回新对象、原单例 `extra_body` 必须保持 `None`。实测证据（`tmp/_probe_ts_isolation.json`、`tmp/_probe_ts_timeline.json`）：单例身份 `m1 is m2` = true；`bound is not m1` = true；bind 前后原对象 `extra_body` 均为 `None` → **已固化为常驻断言**：`tests/test_thinking_scope_guard.py` 三条用例
- [x] 7.2 **生产时序复核**：同一进程、**不 reset 单例**下，two_stage 真实调用路径（`build_prepare_prompt` + `get_prepare_response_format` + `invoke_model`）在"模拟 MVP 执行 bind 前后"两次调用中，对象 id 相同、类仍为 `ChatOpenAI`、`extra_body` 仍为 `None`、解析顶层键仍为 `candidates` / `source_gaps`、无 thinking 污染。实测结论 6/6 全通过
- [x] 7.3 **实施后回归**：`tests/two_stage/` 必须仍为 **467 passed / 0 failed**（不得修改任何 two_stage 测试期望来凑绿） → **实施后实测 469 passed / 0 failed**（用户在并行工作中新增 2 个用例；未修改任何 two_stage 测试期望）
- [x] 7.4 **实施后零改动核验**：`git status --short app/capabilities/contract_review/two_stage/` 输出必须与本 change 开始前一致（即不因本 change 新增任何条目） → 已核：仅用户自有的 3 个在途条目，零新增
- [x] 7.5 **副作用确认（已实测，写入联调须知）**：two_stage 现状**本来就不被思考污染**（因其传 `response_format`），故"不关 two_stage 的思考"不引入新缺陷；本 change 亦**不改变** two_stage 的输出形态

## 8. 联调须知（因本 change 引入的调用方约束）

- [x] 8.1 **`mode` / `prefill_scope` 只加在 `POST /api/v1/contract-review` 的请求体**，**不得**混入 `POST /api/v1/contract-review/prepare` 的请求体 —— 后者的 `PrepareRequest` 是 `extra="forbid"` 严格模型，多余字段会直接 422。虽两端点 body 结构本就不可兼容（前者要 `contract_md`，后者要 `contract_id` / `revision_id` / `main_document`），共用一份 body 实际不会发生，仍须在联调时口头确认一次 → 约束已成立（两条路径的请求模型互不引用）；**联调时仍需口头确认一次**
- [x] 8.2 向合同系统说明：`mode` / `prefill_scope` 均为**可选**且带默认值（`review` / `all`），不传 = 与今天逐字段一致，可零改动先接入 → 已由 `test_review_response_shape_is_unchanged_and_has_no_mode_key` 与 `test_request_defaults_to_review_mode` 锁定；**说明动作本身属 5.1**

## 9. 遗留与后续

- **§5 对外三项**（5.1 字段对齐 / 5.3 D-03 按钮标签 / 5.6 触发时机与快照）为与合同系统的对接动作，待联调窗口执行。
- **3.4 的自动化缺口**：`evidence` 的「**去重**」目前仅靠 prompt 约束，若联调中发现质量问题，建议补断言而非继续放宽 prompt。（「`quote` 长度上限」一项已在第十二轮补齐 —— `test_evidence_quote_max_length_is_300` 钉住 schema 的 `maxLength`。）
- **5.2** 待用户补足样例合同后复测。
- **里程碑标准名清单与合同系统的同步（2026-09-17 登记；用户决定：演示前不接入，未来必须接入）**：
  13 个标准名 / code **只存在于 prompt 文本**（`prompts/contract_review.yaml` 的 prefill user 模板），**代码里零常量、schema 里零枚举**（`milestone_name` / `milestone_code` 均为 `string | null`，对比 `guarantee.type` 是带 `enum` 的），另有 3 份文档副本 → **4 处副本、仅 1 道软约束**。
  风险形态是**静默漂移**：合同系统调整里程碑字典后，我方仍输出旧 `code`，对方按自己的字典匹配**落空**，而整条链路**不报错**（`prefill_status=ok` / HTTP 200）。
  - **演示期前提**：现有 13 个必须就是合同系统当前在用的那一套。
  - **未来接入的三个层次**：①（现状）硬编码在 prompt；② **配置化** —— 清单移入配置文件、渲染时注入 prompt，把 4 处副本收敛为 1 处（**建议先做这步**，价值在"唯一来源"而非自动化）；③ **契约驱动** —— 从合同系统字典接口拉取并缓存，须定义"拉不到"时的降级策略（沿用旧缓存 or 拒绝预填）。

## 10. 修订记录：取值口径改为"原文原样摘录"（第十轮，2026-09-17）

**修订原因**：原设计对金额/日期做了类型与格式归一（金额返回数字、去掉千分位与"元"、日期统一 `YYYY-MM-DD`）。用户判定这会**引入加工误差**（如模型把 `13` 写成 `13.5` 时格式处理反而报错），要求**一律原文原样摘录**，格式与类型的解释权交回合同系统。

**修订后口径**

- 除 `milestone_seq`（`int`）外，**所有业务字段为 `str`**，原文原样摘录：不改写、不归一、不换算。
- 金额：**保留货币符号 / "元" / 千分位**（如 `"¥10492500.00"`、`"¥ 4690000元"`）。
- 比例：**原文只写比例就返回该比例**（如 `"50%"`），**不折算成金额**——由合同系统自行计算。
- 日期：**照抄原文写法**（如 `"2026年3月1日"`），**不归一为 `YYYY-MM-DD`**。
- 月数 / 次数：照抄（如 `service_valid_months` = `"1年"`）。

**代码落点**

- [x] 10.1 `prefill_schemas.py`：新增 `_VerbatimModel(BaseModel)` 基类（`ConfigDict(coerce_numbers_to_str=True)`），6 个原数字字段 + 4 个原日期字段全部改 `str | None`；`milestone_seq` 保留 `int | None`（唯一整数字段）
- [x] 10.2 `prefill_response_formats.py`：删除 `_nullable_number()`；仅保留 `_nullable_integer()` 供 `milestone_seq`；金额/日期/计数一律 `_nullable_string()`
- [x] 10.3 `prefill_prompts.py`：`_FIELDS` 描述由「：数字」/「YYYY-MM-DD」/「数字（含税，两位小数）」改为「：原文写法」/「原文写法（原文只写比例时返回该比例，不要折算）」
- [x] 10.4 `prompts/contract_review.yaml`：`prefill` 条目的 system + user 规则改写 —— 删除「【日期】一律 YYYY-MM-DD」「【金额】一律返回数字」两条旧规则，新增「【一律字符串·原文原样】」「【序号】`milestone_seq` 是唯一返回整数的字段」，并给出正反例
- [x] 10.5 **兜底设计**：`coerce_numbers_to_str=True` 使模型若仍吐数字（如 `13`）时**字符串化为 `"13"`**，而非让整个预填降级为 `prefill_status=failed`

**根因澄清（曾误判）**：早期观测到的 `"service_valid_months": 13.0` **不是模型输出**，而是 Pydantic `float` 字段的序列化产物（`ContractInfo(service_valid_months=13)` → `{"service_valid_months": 13.0}`）。改为 `str` 从根上消除该现象。

**测试**

- [x] 10.6 `tests/test_contract_review_prefill.py`：`_ok_payload()` 改为字符串值（`"¥10,492,500.00"` / `"50%"` / `"5%"`）；新增 3 条用例 —— `test_only_milestone_seq_is_not_a_string`（断言除 `milestone_seq` 外全部为 `["string","null"]`）、`test_verbatim_fields_keep_the_original_wording`、`test_model_emitted_number_is_stringified_not_failed` → 该文件 **36 passed**
- [x] 10.7 真实样例复测（`tmp/_verify_verbatim.py`）：`contract_amount` → `"¥10492500.00"` / `"¥ 4690000元"`；`payment_amount` → `["50%","40%","10%"]` / `["20%","33%","13%","10%","17%","7%"]`；`guarantee.amount` → `"5%"` / `"¥ 130000 元"`；`milestone_seq` → `1..3` / `1..6`；`service_valid_months` → `"1年"` / `None`

**文档同步**

- [x] 10.8 接口文档 `docs/integration/2026-09-16-contract-review-prefill-api-integration.md`：§4.2 新增「⚠️ 取值口径：原文原样摘录」前后对照表；§4.3–4.6 字段表 number→string、date→原文写法；§4.8 示例 JSON 与自检说明；§7 耗时（3 次取中位数：c1 d03 2.2s / d02 5.2s / all 8.8s；c2 d03 1.7s / d02 11.6s / all 12.8s）；§8 限制项 5 重写；§9 自检清单第 4 项改比例求和、新增第 6 项反序列化类型自检；§10 加工边界；§11 并发表按复测数据替换
- [x] 10.9 设计文档 `docs/superpowers/specs/2026-09-15-contract-review-prefill-design.md`：§4.1–4.4 表格与 §4.2 示例 JSON 同步；§4.5 类型约定重写（说明为何不用 number/date）；§11 新增「第十轮」修订记录
- [x] 10.10 本 change spec delta `specs/contract-review/spec.md`：删除「日期 YYYY-MM-DD / 金额两位小数数字」条款，改写为「除 `milestone_seq` 外全部业务字段 SHALL 为字符串、原文原样摘录、SHALL NOT 换算/剥离符号/归一日期」；场景重写为 `日期与金额按原文原样返回` / `数值类字段一律字符串` / `金额以比例约定时不折算` / `阶段序号是唯一的整数字段`；`基于已抽到事实推算而非臆造` 增加禁止金额推导

**修订方式说明**：本次**不新开 OpenSpec change**，而是**就地修订在途的 `contract-review-mvp-prefill` delta** —— 避免出现两个未归档 change 持有互相矛盾的 spec。原「三项确认」（金额形态、调用方式、并发）已由用户在上一轮拍定，故 tasks 3.6「落实计算口径」中"优先推算"的表述**仅适用于日期与阶段序号的排序/关联，不再适用于金额**。

## 11. 修订记录：两个时间字段的来源规则 + `evidence` 加入「无」声明（第十一轮，2026-09-17）

**修订原因**

1. **字段来源没定义清楚，导致实测出现"归属漂移"**。上一轮实测：同一份 `c1`、同一 `scope=d02`、同一套 prompt 连跑 5 次，`plan_finish_date` 命中从 3/3 掉到 0/3 就再没回来 —— 根因不是漏抽，而是 `plan_finish_date` 与 `plan_payment_date` **在原文里指向同一句话、我们没划互斥边界**，模型每次看得见那句话，只是这次记到 finish、下次记到 payment。
2. **空数组无法区分"原文没有"与"我们没抽到"**。用户要求：原文没有时给出提示，而不是静默返回 `[]` / `null`。

**修订后口径**

- **里程碑名称 / 描述 / 序号 / `payment_amount` 只从付款条件取**（原始里程碑节点与金额都在付款条件里）。
- **`plan_finish_date`**：按序取到即止 —— ① 有独立「合同计划 / 进度计划」章节 → 取该章节；② 无 → 取「交付 / 验收」条款；③ 都无 → `null`。
- **`plan_payment_date`**：**只**取自付款条件里该阶段对应的时间表述（如"初验后15个工作日内"）；没有 → `null`。
- **服务端不推算**（用户定调"原样返回，怎么计算是合同系统的事"）：不做日期加减、不把"120天"折成具体日期、不用完成时间推回款时间。**绝对基准日（合同签订日期）只供消费方使用。**
- **`contract_plan` 每行 `evidence` 固定 3 条**：① 付款条件 ② 合同计划章节或交付 / 验收条款 ③ 合同金额条款。某处出处原文**确实不存在**时该条为 `{"section": null, "quote": "无"}`。
- **`*_date` 字段名有误导性**：这四个字段值可能是绝对日期、相对表述或事件起算，调用方须先试解析、失败就原样展示。

**连带收益：上一轮拟开的"派生字段例外"不必开** —— 两个时间字段回归原文摘录，第十轮那条「一律原文原样、不换算、不推算」的口径**一字不改**。

**prompt 与代码落点**

- [x] 11.1 `prefill_prompts.py`：`_FIELDS` 的 `contract_plan` 段重写 —— 加"里程碑四要素只从付款条件拆"、两个时间字段的三级来源、⛔ 禁止自己算、`evidence` 固定 3 条与 `"无"` 约定；`_EXAMPLES` 的 `contract_plan` 示例改为 3 条 `evidence` 的真实形态
- [x] 11.2 `prompts/contract_review.yaml`：`prefill.system` 新增「【时间字段的来源】」「【不要自己算】」「【依据的出处固定】」三段；`prefill.user` 硬性要求新增两条（时间字段来源 + `evidence` 固定 3 条）。**`review` 的 7 条 prompt 零改动**（diff 仅命中 `prefill:` 段，已核验）
- [x] 11.3 ⚠️ **踩坑修复**：`prompts.py:25` 对 **user 模板**做 `.format()`，模板里的裸 `{"section": null, "quote": "无"}` 被当成占位符 → `KeyError: '"section"'` → 被 `run_prefill` 的兜底 `except` 吞掉 → **整份预填静默变成 `prefill_status=failed`（HTTP 仍 200）**。修法：模板内写成 `{{...}}`
- [x] 11.4 **零 schema 变更**：`prefill_schemas.py` 仅更新模块 docstring 说明（字段类型、键集合、`PrefillEvidence` 结构均未动）；`prefill_response_formats.py` 无改动

**测试**

- [x] 11.5 `tests/test_contract_review_prefill.py` **36 → 38 passed**，新增 2 条：
  - `test_prefill_prompt_carries_the_time_source_rules` —— 两个时间字段的来源规则必须落在 prompt 里（防规则被误删）
  - `test_prefill_prompt_renders_literal_braces_once` —— 断言渲染后 `{"section": null, "quote": "无"}` 复原为单个花括号、且无残留 `{{`（钉死 11.3 那个坑）
- [x] 11.6 **真实样例复测（三条路径全部走通，`tmp/_verify_plan_dates.py` + 新增合成样例 `tmp/samples/c3.md`）**：

  | 样例 | 路径 | 实测结果 |
  |---|---|---|
  | `c3`（合成，**有**独立「合同计划」章节） | 主路径 | 3 行 `plan_finish_date` 全部从「第五条 合同计划」摘到绝对日期（`2026年1月20日` / `7月31日` / `11月30日`）；`plan_payment_date` 全部取自付款条件；每行 `evidence` **正好 3 条**（付款条件 / 合同计划 / 合同金额） |
  | `c1`（真实，**无**计划章节） | 交付条款路径 | `plan_finish_date` 从「第二条 交付和验收」摘到 `"自合同签订之日起120天（自然日）内"`；确实无时间的行返回 `null` + `{"section": null, "quote": "无"}` |
  | `c2`（真实，交付时间指向附件） | 「无」路径 | 原文写"详见附件2《技术协议》" → `plan_finish_date` 全 `null`，每行第 2 条 `evidence` 均为 `{"section": null, "quote": "无"}` |

- [x] 11.7 **归属漂移复测**：`c1` 同输入连跑 3 次，`plan_finish_date` **稳定 1/3 且永远是同一行**（改前为 3/3 → 0/3 → 0/3 的乱跳）→ 划定来源即治好。

**文档同步**

- [x] 11.8 接口文档 `docs/integration/2026-09-16-contract-review-prefill-api-integration.md`：§4.2 补"服务端只摘录不推算"；§4.3 两个服务时间字段加"可能是事件起算"+ `*_date` 未必是日期的警示块；§4.4 新增「⚠️ 两个时间字段的取值来源」表块（含"`plan_finish_date` 为 `null` 时回款时间无从推算"）；§4.7 重写为**固定 3 条 + `"无"` 约定 + 消费方全等判定规则表**；§4.8 示例改为真实响应形态（含 `"无"`）；§8 限制项 1/2/4 重写、新增第 8 条（空数组歧义）；§9 新增自检项 12/13/14；§10 第 3 步补两个时间字段的来源与"禁止推算"
- [x] 11.9 设计文档 `docs/superpowers/specs/2026-09-15-contract-review-prefill-design.md`：§4.2 表格与出处对照表更新、新增「两个时间字段的口径」专题块（含"「无」按出处不按字段"、"为什么不给对象组加字段级 evidence"）；§4.5 新增 `*_date` 与"服务端不推算"两条，`evidence` 条改为固定 3 条；§11 新增「第十一轮」修订记录（9 条）
- [x] 11.10 本 change spec delta `specs/contract-review/spec.md`：改 3 条 ADDED requirement —— ① `预填字段数据契约` 增加 `*_date` 字段未必可解析 + 新场景；② `合同计划抽取与里程碑归一` 增加来源规则，`基于已抽到事实推算而非臆造` 场景**替换**为 `计划完成时间的来源` / `计划回款时间的来源` / `服务端不做日期推算`（**取消了原"MAY 推导"的许可**）；③ `预填原文依据标注章节位置` 改为固定 3 条 + `"无"` 语义 + 2 个新场景。`openspec validate --strict` → `is valid`

**修订方式说明**：本次**仍就地修订在途 delta，不新开 change** —— 这次是**技术约束而非偏好**：`openspec/specs/contract-review/spec.md` 里 **prefill / 预填出现 0 次**（该 change 未归档，delta 尚未合并），而在途 delta 用的是 `## ADDED Requirements`。新开一个 change 时，写 `MODIFIED` 会因 target requirement 不存在而 `validate` 失败，写 `ADDED` 又会与在途的 7 条同名冲突 —— **两条路都堵死**。

**已知代价**：该 change 的 spec delta 已**第二次偏离 `a031153` 那版实现**，`openspec list` 的完成度计数会随本节勾选再变；归档时评审者需按 §10 / §11 两节回溯口径演进。

## 12. 修订记录：`evidence.quote` 上限 60 → 300 字（第十二轮，2026-09-17）

**修订原因**：`quote` 上限 60 字**常截断在句中** —— 核对者拿到的不是一句完整表述，回原文检索时也不好定位。目标文本（付款条件、合同计划行、履约保证条款）一句通常在 60–150 字，300 足以整句容纳。

**修订后口径**

- `quote` 长度上限 **60 → 300 字**，**类型、键集合、条数均不变**（仍 `string | null`，`contract_plan` 每行仍固定 3 条，`"无"` 约定与全等判定规则不变）→ **消费方解析逻辑无需改动**。
- **上限是"不许超过"，不是"要求达到"**：值仍为原文摘录，原文只有一句就照抄一句，**不得为凑长度把整段抄入**（已写入设计文档 §4.5 与 spec delta）。

**改动清单**

- [x] 12.1 `prefill_response_formats.py`：`EVIDENCE_SCHEMA` 的 `quote` 由 `_nullable_string(max_length=60)` 改为 `max_length=300` —— **本次唯一改到运行时行为的一行**，它同时是发给模型的 strict 约束
- [x] 12.2 `prefill_prompts.py`：`_FIELDS["contract_plan"]` 的 `quote` 描述 `（≤60字）` → `（≤300字）`
- [x] 12.3 `prompts/contract_review.yaml`：`prefill.system` 的【原文依据】`（≤60字，不改写、不翻译）` → `（≤300字，不改写、不翻译）`。**`review` 的 7 条 prompt 零改动**
- [x] 12.4 `tests/test_contract_review_prefill.py`：新增 `test_evidence_quote_max_length_is_300`，把 schema 的 `maxLength` 钉死 —— 该值**此前没有任何自动化断言**（§9 早已记为遗留），本轮顺手补上
- [x] 12.5 设计文档 §4.5 / §5.2 说明、§12 修订记录；接口文档 §4.7 字段表、§8 第 3 条；本 change spec delta 的第 244 行 —— 全部同步为 300 字并补"上限非目标"的限定
- [x] 12.6 **真实样例复测**：三份样例实跑，确认**放宽上限不会诱导模型灌长引文**（36 条最长 106 字、均值 44，无一条逼近 300）；耗时另做受控 A/B（见下），**证明无代价**

**实测（`tmp/_verify_quote_len.py`，2026-09-17，已预热后单发，`scope=d02`）**

| 样例 | 行数 × 3 条 | `quote` 最长 | 均值 | 超旧上限 60 字 | 耗时 |
|---|---|---|---|---|---|
| `c3`（合成，有独立合同计划章节） | 3 行 = 9 条 | 49 | 43 | **0** | 7.6s |
| `c1`（真实，无计划章节） | 3 行 = 9 条 | 47 | 33 | **0** | 7.8s |
| `c2`（真实，交付时间指向附件） | 6 行 = 18 条 | 106 | 51 | **6** | 17.3s |
| **合计** | **36 条** | **106** | **44** | **6** | — |

**结论**

1. **放宽上限没有诱导模型灌长引文** —— 36 条里最长 106 字，**落在 [240, 300] 上限区间的一条都没有**，均值仅 44。模型取的是"够用的一句"，不是"能塞多少塞多少"。这是本轮最需要排除的退化方向，已排除。
2. **旧上限确实在切目标内容，且切掉的正是要支撑的那个值**。`c2` 那 6 条超 60 字的引文全部是付款计划表的整行（`第二阶段 | … | 33% | /`），而**金额比例位于行尾** —— 60 字会在比例之前就截断，等于 `payment_amount` 的原文依据**被截没了**。这条是本次放宽的直接收益，比"引用更完整"更实在。
3. **耗时：受控 A/B 证明无代价**（`tmp/_ab_quote_len.py`，同输入 monkeypatch 上限、各 3 次取中位数）：

   | 上限 | 耗时中位数 | min / max | 最长 `quote` | 顶到上限（即被截断） |
   |---|---|---|---|---|
   | 60 | 16.2s | 15.6 / 16.7 | **恰好 60** | **4–6 条** |
   | 300 | 15.4s | 15.4 / 17.1 | 98 | **0 条** |

   中位数差 **−0.8s**，落在噪声量级（单发噪声可达 ±4s）→ **放宽上限对耗时无实际影响**（`c2` 多出约 300 字符 ≈ 165 tokens ≈ +1.1s，被正常波动淹没）。同一实验还**因果性地锁死了截断**：上限 60 时最长引文恰好等于 60、且有 4–6 条顶在边界上；放到 300 后同一批引文以 98 字完整输出。§12 实测表里的 17.3s 单发值也由此确认是噪声。

**未同步的一处（有意）**：历史实施计划 `docs/superpowers/plans/2026-09-16-contract-review-mvp-prefill.md` 内嵌一份 prompt 快照，仍写 `≤60字`。该文件自 `a031153` 后**从未随口径演进更新**（第十、十一轮关键词命中 0 次），性质是**执行时的计划快照**而非活文档，故继续不动；口径以设计文档、spec delta 与接口文档为准。

## 13. 修订记录：`upload-md` 入口支持预填 + 附件口径收敛（第十三轮，2026-09-17）

**修订原因**：消费方/联调方按**文件上传**方式调用（`multipart`），而预填只在 JSON 入口提供 —— 两个入口语义不一致，会把"同一个功能要学两套调用方式"的成本推给对方，且将来补齐时对方还要再适配一次。**决定：现在补齐，两个入口语义完全一致。**

**修订后口径**

- `POST /api/v1/contract-review/upload-md` 新增**两个可选表单字段**：`mode`（默认 `review`）、`prefill_scope`（默认 `all`），与 JSON 入口**同名、同默认、同 `Literal` 校验**。
- 两个入口**共用同一处分流函数**（`router._dispatch`），保证 `mode` 语义、字段口径与响应结构逐字段一致。
- **`mode` 取值非法**（含错拼如 `prefil`）→ **422 + `code=10001`**，**不再静默落回评审**（此前 multipart 传 `mode` 会被 FastAPI 丢弃、HTTP 200 返回评审结果，是易误判的坑）。
- **不传 `mode` 时行为与改造前逐字段一致** —— 老调用方零影响。

**附件口径（用户拍板，本轮一并固化）**：「在正文里就当正文，不在就不管」。

- 预填输入 = `contract_md` **整份全文**，服务端不切分、不截断（`prefill_prompts.py:101-113`）→ **正文内嵌的附件章节**（独立 `附件一` 标题行）与正文同等对待，**会**被抽取。
- **单独上传的附件**（JSON `attachments` / multipart `attachment_files`）**不参与抽取**，传了不报错、静默忽略。
- 顺带确认一个**对预填有利**的非对称：review 用 `split_embedded_attachments` 把 `附件N` 章节**从正文切出去**当独立文档，预填**不切**、整段留在上下文里。
- ⚠️ **覆盖缺口（如实记录）**：`tmp/samples/` 的 c1 / c2 / c3 **都没有**内嵌附件章节 → **「附件在正文中」这条路径目前 0 覆盖**（属"没测过"，非"测过没问题"）。c2 的 `详见附件2《技术协议》` 属"正文引用外部附件"，即"不在就不管"那类。

**改动清单**

- [x] 13.1 `router.py`：抽出 `_dispatch(request)` 供两个入口共用；`upload-md` 新增 `mode` / `prefill_scope` 两个 `Form` 参数并透传到 `ContractReviewRequest`。**`review` 分支仍直接调用模块内 `review_contract`**（`tests/two_stage/test_prepare_api.py` 依赖该 patch 目标与调用次数）
- [x] 13.2 `tests/test_contract_review_api.py`：新增 3 条 —— `..._prefill_mode_routes_to_prefill`（走预填且**不**调用 `review_contract`）、`..._defaults_to_review_mode`（不传 mode → `mode=review` / `prefill_scope=all`）、`..._rejects_unknown_mode`（422 + `10001`）
- [x] 13.3 接口文档：头部适用范围与 §1 改为"两个入口皆支持"；新增 **§3.5 Markdown 文件入口**（表单字段表 + curl 示例 + 非法 mode 行为）；§3.4 附件口径改写为"只认正文里的"；§8 新增第 10 条；§9 新增第 16 条文件入口自检
- [x] 13.4 评审接口文档（`2026-08-03-...`）§1 加交叉引用：两个入口均支持预填、不传 `mode` 行为不变
- [x] 13.5 本 change `proposal.md`（Impact 与 Modified Capabilities）、spec delta（需求名下的入口范围 + 4 条 Scenario）、`tasks.md` §6 三条 + 本 §13
- [x] 13.6 验证：`pytest tests/ -q` 全绿、`pytest tests/two_stage/ -q` **零回归**、`openspec validate --strict` 通过

**没有新开 change 的理由**：主 spec `openspec/specs/contract-review/spec.md` 里**没有任何预填内容**（预填需求只活在在途 delta 中），新开 change 写 MODIFIED 会因找不到目标而 `validate` 失败、写 ADDED 会与在途需求重名冲突 → **只能就地修订在途 delta**（该结论在第十轮修订时已实测确认）。

**未同步的一处（有意）**：`docs/superpowers/plans/2026-09-16-contract-review-mvp-prefill.md:933` 写有"`/contract-review/upload-md` 一行不改；预填不提供 multipart 形态"，属**执行时的计划快照**，按 §12 同一惯例不动。

## 14. 修订记录：`finance_info` 并入 `d02`（第十四轮，2026-09-18）

**修订原因**：`prefill_scope=d02` 只返回 `contract_plan[].payment_amount` 的**比例原文**（实测 `"50%" / "40%" / "10%"`），**不带合同总额** → 合同系统拿到比例**算不出金额**。属分组归属疏忽。

**用户拍板**：把**整组 `finance_info` 同时归入 `d02` 与 `d03`**，按「基础信息」而非「场景专有」归属；**不新增字段、不改字段名、不改取值口径、不做任何计算**。

**修订后口径**

- `SCOPE_GROUPS`：`d02` = `contract_info` + `contract_plan` + `finance_info`（三组）；`d03` = `finance_info` + `guarantee`（不变）；`all` = 四组（不变）。
- **去重后仍是 26 个返回字段**（`finance_info` 的 2 个字段被两个 scope 共用，不重复计数）。
- `d02` 下未被请求的组只剩 `guarantee`（空数组）；`d03` 下 `contract_info` 全 `null`、`contract_plan` 为空数组。四组外层键**一个不少**。
- `finance_info` 的 schema、字段类型（`string`）与取值口径（`currency` 映射为 `CNY`、`contract_amount` 原文原样）**一字未改**。

**改动清单**

- [x] 14.1 `app/capabilities/contract_review/prefill_response_formats.py`：`SCOPE_GROUPS["d02"]` 加入 `finance_info`。schema / `json_example` / `top_level_keys` / `required_keys` 均由 `SCOPE_GROUPS` 自动派生，**无需手工同步**（已 grep 复核）
- [x] 14.2 `app/capabilities/contract_review/prefill_prompts.py`：`scope_note` 由**硬编码 `_SCOPE_NOTES`** 改为**从 `SCOPE_GROUPS` 派生的 `_scope_note(scope)`** —— 消除「分组变了、prompt 说明没跟上」的漂移源
- [x] 14.3 `tests/test_contract_review_prefill.py`：改 2 条（`test_scope_groups_match_with_design`、`test_schema_scope_only_exposes_requested_groups`），新增 4 条 —— `test_finance_info_is_shared_by_d02_and_d03`、`test_scope_note_is_derived_from_scope_groups`、`test_run_prefill_d02_keeps_contract_amount_but_blanks_guarantee`、`test_run_prefill_d02_asks_model_for_three_groups`
- [x] 14.4 接口文档 `docs/integration/2026-09-16-contract-review-prefill-api-integration.md`：§3.2 分组表与说明、§4.5 标题与归属说明、§4.6/§4.8 `d02` 示例补 `finance_info`、§7 耗时、§9 自检第 4 条、§11.4 交互建议
- [x] 14.5 设计文档 `docs/superpowers/specs/2026-09-15-contract-review-prefill-design.md`：§2 字段总数口径、§3.4 两表、§3.5 两张表与未请求组说明、§4.3 标题与归属说明、新增「第十四轮」修订记录
- [x] 14.6 本 change：spec delta（`prefill_scope` 需求正文 + 新增 1 条 Scenario「d02 同时返回合同总额与付款比例」+ 字段契约需求补去重口径）与本 §14
- [x] 14.7 验证：`pytest tests/ -q` → **830 passed / 0 failed**；prefill + API 相关 **52 passed**；`pytest tests/two_stage/ -q` 零回归；`openspec validate contract-review-mvp-prefill --strict` 通过

**实测（新口径，`tmp/samples/c1.md`，重复 3 次取中位）**

- `d02` 返回 `finance_info = { "contract_amount": "¥10492500.00", "currency": "CNY" }`，`payment_amount` 为 `"50%" / "40%" / "10%"` —— **比例与总额在同一响应里齐了**。
- 耗时 `d02` **6.9s**（加组前 5.2s）、`d03` 3.1s、`all` 10.2s。

**没有新开 change 的理由**：同 §11 / §13 —— 主 spec 里 prefill 出现 0 次，新 change 写 `MODIFIED` 无目标、写 `ADDED` 与在途需求重名，**只能就地修订在途 delta**。

**未同步的一处（有意）**：历史实施计划 `docs/superpowers/plans/2026-09-16-contract-review-mvp-prefill.md` 内嵌的分组快照仍写 `d02 = contract_info + contract_plan`，属**执行时的计划快照**，按 §12 / §13 同一惯例不动；口径以设计文档、spec delta 与本文件为准。

## 15. 修订记录：取值规则补强（第十五轮，2026-10-03）

**修订原因**：复核 `YDZB1812336A`（中国移动上海 × 东软 · 技术开发合同）预填返回，发现 **4 处缺陷 + 1 处口径缺失**。根因是合同用 `【】` 作填空标记，而**括号边界没有规则**，模型对同一份合同、同一个 `【】` 形态给出**四种互不相同的取值方式**：

| 字段 | 原文 | 返回 | 括号边界处理 |
|---|---|---|---|
| `service_content` | `1.1 甲方委托乙方开发【…】项目。` | 整句，保留 `【】` | 全文照抄 ✅ |
| `service_valid_months` | `…之日起【两】年。` | `"两"` | 只取括号内 ❌ 丢单位 |
| `finance_info.contract_amount` | `（¥：【763200】元…` | `"763200"` | 只取括号内 ❌ 丢 `¥` 与「元」 |
| `service_end_date` | `在【2018】年【11】月【30】日完成。` | `"2018年11月30日"` | 拼接内外、去 `【】` ⚠️ 来源条款错 |

**同一响应内自相矛盾（更硬的证据）**：`payment_amount` 来自「相当于合同总价款的【80】%」→ 返回 `"80%"`，**保住括号外的 `%`**；而 `contract_amount` 来自「（¥：【763200】元」→ **丢掉括号外的 `¥`/元**。同一形态、同一合同，一个保单位一个不保。

**`service_end_date` 误抓的判据**：该值取自 `2.1`「开发内容在【2018】年【11】月【30】日完成」（属**履行期限**条款，非服务条款）；真正的服务期限在 `7.1`「免费质量保证期为从系统初验合格之日起【两】年」= 事件起算 + 期限，**无绝对日期**。**铁证：`service_start_date=null` 而 `service_end_date` 有值 —— 起止不成对。**

**用户拍板（2026-10-03）**

1. **金额型字段一律不带符号**（3 个字段：`contract_plan[].payment_amount`、`finance_info.contract_amount`、`guarantee[].amount`）。
2. **「万」「亿」保留、不换算**（不去掉、不折成 ×10000 —— 折算属服务端计算，踩红线）。
3. **`%` 保留** —— `payment_amount` 多为比例，若按"去除非数字字符"实现会使 `"50%"` 退化为 `"50"`，语义灾难。
4. **中文大写金额优先取阿拉伯数字那侧**；全文只有大写时返回大写原文。
5. **`currency` 明确为 ISO 4217 三位大写码**（`CNY`/`USD`/`JPY`）；且该字段**不恒为 `CNY`**（见下"纠正"）。
6. **`service_start_date` / `service_end_date` 补取值来源规则**；消费方已确认**可接受**这两字段在多数合同上为 `null`。
7. 给 `contract_info` / `finance_info` **补 `evidence` 不在本轮范围**（需新增字段，另行立项）。

**修订后口径**

- 金额型字段**删除集**：`¥` `￥` `$` `€` `£`、币种词「元」「人民币」「RMB」、千分位 `,`、首尾空白；**除这 3 个字段外，任何字段一律不剥离**。
- **保留集**：数字、小数点及其后原样小数位、`%`、数量级「万」「亿」。**禁止任何换算**（不折「万」、不折 `%`、不转中文大写数字）。
- **填空标记**：去掉 `【】` 本身、保留其前后紧邻的单位 / 货币符号 / 量纲；**不得返回裸数字、裸量词**。
- **服务类日期**：来源限定服务 / 售后 / 质保条款；只有「事件起算 + 期限」时两字段**同为 `null`**，不得用合同内其他绝对日期顶替（**起止不得仅一侧有值**）。
- **`evidence` 第二条**：新增第三种态 —— **出处章节存在但不含所需事实**（如交付 / 验收条款只有验收流程时限）时，该条返回 `{"section": null, "quote": "无"}`，**不得**改用该章节原文片段充当 `quote`。

**🔴 顺带纠正一处此前的错误结论（重要）**

本轮曾误判 `currency` **恒为 `"CNY"`**，实为错误。三条反证：① `prefill_response_formats.py:55` 为 `_nullable_string(max_length=8)`，**无 enum / const / 默认值**（对比同文件 `guarantee.type` 是真 enum）；② `prefill_prompts.py:68` 原文是「币种：**如** `"CNY"`」（举例）；③ `prefill_prompts.py:91` 的 `"CNY"` 只是 JSON 示例值。**该字段随合同币种变化**，本次一并把口径定死为 ISO 4217。

**改动清单**

- [x] 15.1 本 change 的 spec delta：字段数据契约需求正文（金额型字段例外 + 保留集 + 填空标记 + 服务日期来源 + `currency` ISO）、`evidence` 需求正文（补第三种态）；新增 8 条 Scenario（金额剥离符号 / 保留比例小数数量级 / 仅有大写 / 填空标记自带单位 / 币种 ISO / 服务日期来源 / 出处存在但不含所需事实），并修正 2 条与新口径冲突的既有 Scenario（`日期与金额按原文原样返回`、`数值类字段一律字符串`）
- [x] 15.2 全部规则落地 —— **分两处**（`2026-10-05` 完成）：① `prompts/contract_review.yaml` 的 `prefill:` 段承载**通用规则**（金额删/留集、`【】` 填空边界、`currency` ISO、四个时间字段来源、`evidence` 三态），理由是该段**不随 scope 变化**、三个 scope 都看得到；② `app/capabilities/contract_review/prefill_prompts.py` 的 `_FIELDS` 承载**字段级说明**（在各字段旁注明自身规则），保证按 scope 组装时该字段的规则一定在场。**服务端业务代码零改动**（`prefill_service.py` 未触碰）；`mode=review` 的 prompt 段未触碰（`git diff` 的 hunk 上下文全部落在 `prefill:` section 内）
- [x] 15.3 `app/capabilities/contract_review/prefill_response_formats.py`：`currency` 的 `max_length` 由 8 收紧为 3 —— **2026-10-05 用户拍板执行，已完成**。定性：属**响应 schema 约束收紧**，不新增 / 不改名 / 不改字段集合，不触红线。已核**无任何测试依赖 `maxLength=8`**（`grep` 全仓仅 `FINANCE_INFO_SCHEMA` 一处定义，测试只断言 `currency == "CNY"`）
- [x] 15.4 `tests/test_contract_review_prefill.py`（`2026-10-05` 完成）：① `_ok_payload()` 的 `contract_amount` 由 `"¥10,492,500.00"` 改为 `"10492500.00"` 并重写 docstring（点明"金额型字段已去符号"与"服务端零加工、断言校验的是原样透传"）；② 关联断言同步（原 `:312` / `:330` 两处）；③ **新增 7 条 prompt 内容断言用例** —— 金额删/留集（含**反向断言**：prompt 里不得再出现"不要去掉符号"）、`【】` 填空边界、服务日期来源、`currency` ISO 且**不固定**、`evidence` 三态、金额规则**三个 scope 均可见**（防"挪进 `_FIELDS` 后漏组"的静默半失效）、`currency` schema `maxLength == 3`。该文件实测 **50 passed**
- [x] 15.5 接口文档 `docs/integration/2026-09-16-contract-review-prefill-api-integration.md`（**2026-10-05 完成，共改 12 处**）：头部加 2026-10-03 变更说明并更新日期、§0「未变的部分」改为"2026-09-18 那次变更未动的部分"并把「取值口径（原文原样）」标注为**已不成立**、§4.2 取值口径纲领**整段重写**（改为"默认原文原样 + 3 类例外"并给出 13 行新旧对照示例表）、§4.3 服务日期两行改写 + 表后补"易为 `null` 是修正而非失败"、§4.5 `contract_amount`/`currency`、§4.6 `amount`、§4.7 判定表**补第三态**（含"两种情形标记相同、消费方无需区分"与语义变更提示）、§8 第 2 条「`"无"`」语义、§8 第 4 条服务日期、§8 第 5 条、§8 第 9 条「同类例外」表述、§9 第 4 条自检、§10 第 3 条「不去货币符号」、§4.8 示例的 `contract_amount` 值

**附加：接口文档的**两处**"留白"说明**

- §4.8 示例中 `evidence[].quote` 里的 `¥10492500.00` **保持原样不动** —— `quote` 是**原文片段**，服从原文原样，不适用金额例外。
- [x] 15.6 新增消费方增量说明 `docs/integration/2026-10-03-contract-review-prefill-value-rules-change.md`（结论：消费方**无需任何改动**）
- [x] 15.7 新增变更范围草案 `docs/superpowers/specs/2026-10-03-contract-review-prefill-value-rules-scope.md`
- [x] 15.8 验证（`2026-10-05` 实跑，`PYTHONPATH=. ./.venv/Scripts/python.exe -m pytest`）：
  - `tests/test_contract_review_prefill.py -q` → **50 passed**（含本轮新增 7 条）。
  - `pytest tests/ --ignore=tests/two_stage -q` → **476 passed / 2 failed / 1 skipped**。2 个失败判为**既有环境漂移、与本次无关**：`test_config.py::test_loads_default_then_env_override` 与 `test_llm_factory.py::test_get_chat_model_returns_base_chat_model`，两者都断言 `llm.base_url == "http://192.168.16.10:8080/v1"`，而 `config/config-dev.yaml` 已被**本地**改为 `https://api.xiaomimimo.com/v1`（小米 MiMo API）。证据：该 config 与 `tests/test_llm_factory.py` 均处于 `M` 状态且非本次改动；两个测试都不触及 prefill。
  - `pytest tests/two_stage -q` → **527 passed / 20 failed**。失败**全部**落在 `tests/two_stage/test_m2_signature_replay.py`（untracked 文件）。**三重取证证明与本次无关**：① 根因统一 —— 缺 `%TEMP%\m2-header-checkpoint-retirement-02.json`（`FileNotFoundError`），或 `prompts/contract_review_prepare.yaml` 的现场指纹与测试常量 `_CURRENT_PROMPT_SHA256` 不符（该常量绑定的是 **prepare** prompt，**不是**本次改动的 `contract_review.yaml`）；② 该测试文件**不 import 任何 prefill 模块**，只 import `two_stage.*`；③ `find app/capabilities/contract_review/two_stage tests/two_stage -newermt "-30 minutes"` **输出为空** → 两处目录本轮零改动（红线①成立）。
  - `openspec validate contract-review-mvp-prefill --strict --no-interactive` → **`is valid` / EXIT=0**。

**⛔ 实现约束（关键）**

**15.2 的全部规则必须在 prompt 层实现，服务端 SHALL NOT 做任何字符串后处理。** 三条依据：

1. 接口文档 §10 第 4 条：「**服务端不对取值做任何二次加工** —— 拿到的字符串原样放进响应」。
2. `tests/test_contract_review_prefill.py:294` 的 `_ok_payload()` 注释为「模拟新取值口径下模型的输出：除 `milestone_seq` 外一律原文原样字符串」，其断言（`:312` / `:330`）校验的正是**原样透传**（`"¥10,492,500.00"` 进 → 同样出）。
3. 若改服务端 strip，将**打穿上述断言**并改变「服务端零加工」的既有契约。

→ 走 prompt 方案时**服务端业务代码零改动**，上述用例不受影响。

**红线核对**

| 红线 | 影响 |
|---|---|
| ① 不碰 `two_stage/**` | ✅ 不涉及 |
| ② `mode=review` 只关思考，prompt / 响应模型 / 检查逻辑 / 错误码 / 字段集合不动 | ✅ 本变更只动 prefill 侧 prompt 与 schema 约束，不触及 review 链路 |
| ③ 预填只读 `contract_md` + `prefill_scope` | ✅ 不涉及 |
| 不新增字段 / 不改名 / 不改字段集合 | ✅ 只改**取值内容**；3 个金额字段名与类型不变；`currency` 仅收紧取值形式 |

**验证（本轮已完成部分）**

- `openspec validate contract-review-mvp-prefill --strict --no-interactive` → **`is valid` / EXIT=0**（spec delta 改完后立即跑过）。
- 15.2 / 15.4 / 15.8 的代码与测试验证**待实施后补**。

**没有新开 change 的理由（2026-10-03 更正）**：主 spec 里 prefill 出现 **0 次**（`grep -c` 复核）—— 预填整体尚未合并。就地修订仍是正确做法，但**理由不是"validate 过不了"**。§11 / §13 / §14 沿用的「新 change 写 `MODIFIED` 无目标、写 `ADDED` 与在途需求重名」这一说法**已被实测证伪**，此处更正（历史各节按惯例不追改）：

- **🔬 实测：三个探针（建后即删）** —— `openspec validate --strict` **不校验需求名的存在性与重名**：
  ① `MODIFIED` 一个只存在于在途 delta 的需求 → `is valid` / EXIT=0；
  ② `ADDED` 一个与在途 delta 同名的需求 → `is valid` / EXIT=0；
  ③ `ADDED` 一个主 spec 已存在的需求名（作对照）→ `is valid` / EXIT=0。
  → **validate 只查格式，不查引用能否落地。**
- **真正的理由**：新建 change 会声明 `MODIFIED 预填字段数据契约`，而该需求**只存在于在途 change 的 delta 里、尚未进入主 spec** → 制造一条**悬空引用**，并使新 change 与在途 change 之间产生**隐含的合并顺序依赖**（在途那份必须先合并）。加之在途 delta 本身仍在反复修订（本轮已是第 15 轮），新 change 改的是**移动靶**。而预填整体尚未上线、规格仍是同一份草稿 → **继续修订该草稿**是唯一无歧义的做法。
- 🔴 **风险提示**：正因为 validate 不拦这种情况，新建 change 会显示 `is valid` —— **这是假绿灯，比报错更危险**（会让人误以为该声明合法）。若后续继续沿用"validate 会拦"的旧说法，会把错误认知传下去。
- **建议**：尽快推动 `contract-review-mvp-prefill` 走完流程归档。否则预填的后续改动将持续叠在同一个 delta 上，独立变更记录缺失，追溯只能靠本文件的修订章节。

**2026-10-05 文档一致性审核（已全部修正）**

对本轮全部相关文档（spec delta / 本文件 §15 / `proposal.md` / scope 草案 / 消费方增量说明 / 接口文档）与代码事实基线逐项比对，共发现 **17 处不一致**：

| 类别 | 处数 | 内容 |
|---|---|---|
| 🔴 硬矛盾 | 1 | `service_start_date` / `service_end_date` 的"事件起算"处理 —— 两条规格条款 + 两条 Scenario 互斥（裁决见下） |
| 规格表述缺口 | 2 | ① 字段契约总述未给"例外"引子（金额字段已非原文原样）；② 填空标记规则未说明与金额例外**串联适用、不互相抵消** |
| 规格易误读 | 1 | `service_valid_months` 用「质保期」条款当正例，易被读成"质保期 = 服务有效期"已定（scope §6 明确为另案）→ 已加澄清 |
| 接口文档与代码脱节 | 11 | §0「未变的部分」/ §4.2 纲领与示例表 / §4.3 / §4.5 / §4.6 / §4.7 判定表 / §8 第 2·4·5 条 / §9 第 4 条 / §10 第 3 条 |
| 本文件自身 | 2 | ① 15.3 的"待确认"未落定；② **15.5 清单漏了 §4.7 与 §10** 两处必改章节 |

🔴 **硬矛盾的裁决（2026-10-05）**：`spec:147`（旧）举例服务日期可以是"事件起算"表述并原样返回，且旧 Scenario `日期字段未必是可解析日期` 要求 `service_start_date` **原样返回**「自系统上线并最终验收合格之日起计」；而本轮新增的 `spec:148` 与 Scenario `服务类日期字段的来源` 要求同种情形**两字段同为 `null`**。**四条互斥。** 已按**严格版**统一，理由三条：① 与本轮用户意图（不得用非服务条款日期顶替）一致；② 与接口文档 §4.8 实测示例一致（该示例中两字段均为 `null`，原 §4.3 的"就照抄这一句"与自家示例矛盾）；③ 与本轮新增的「起止成对」判据一致。具体改法：`spec:147` 拆为两条（计划类日期允许相对表述原样返回；服务类日期更严，事件起算 / 相对表述 → `null`），旧 Scenario `日期字段未必是可解析日期` 的主体由 `service_start_date` 改为 `plan_finish_date`。**若消费方更需要"服务条款里的事件起算表述也原样回传"，改回宽松版只需回退这两处。**

**第十六轮 · 合同类型分路（2026-10-05）**

**起因**：用户在收口时追问「需要区分合同是服务类合同还是非服务类合同，这一点本次 change 有涉及到吗？」→ **核查结论：完全没有**。当时的表述是**全链路空白**：`prompt` / spec delta / 接口文档 / scope 草案**四处都没有**任何一句说明合同类型是否参与判定；且**预填请求里根本没有类型参数**（`ContractReviewRequest` 字段集 = `{contract_md, attachments, mode, prefill_scope}`）。

**用户裁决（原话）**：「先从合同名称中识别是否是服务合同，**不用限制太死**，能识别就识别为服务合同，不能识别就一律按非服务合同走」。

**落地口径**：

> ⚠️ **本节第 1 条是初版写法，已被下方「同日二次修正」取代** —— 保留下文以留痕。**最新口径：服务性质词表不含「开发」**，判定依据的示例应是 `…运维服务合同` 而非 `…技术开发合同`。

- **判定依据 = 合同名称**（正文最前面的一级标题，如 `…技术开发合同`）；**判据从宽** —— 名称内含服务性质词（服务 / 开发 / 运维 / 运营 / 咨询 / 设计 / 监理 / 外包 / 维护 / 技术支持 / 实施 / 集成 / 培训 / 检测 / 评估 / 勘察）→ **服务类**；看不出、**或读不到名称** → **非服务类**；不得因正文内容像服务而改判。
- **非服务类**：`service_start_date` / `service_end_date` 只从服务 / 售后 / 质保条款取，只认绝对日期；**两者必须成对**（同为 `null` 或同为有值）。
- **服务类**：`service_start_date` 规则同上；`service_end_date` 在服务条款取不到绝对日期时，**可以**改取**合同自身的完成 / 交付截止日** → **允许只有该字段有值**。
- **两类共同**：只写「事件起算 + 期限」或纯相对表述 → `null`，不折算、不推算。
- **不新增字段 / 不改请求契约**：不引入 `contract_type` 入参，也不把类型落进响应；类型纯由模型从正文自判。已加 `test_prefill_request_has_no_contract_type_field` 固化（断言字段集恰为那 4 个且不含 `contract_type`）。

**🔴 同日二次修正：「开发」误入服务性质词表（用户当场指出）**

初版词表收了「**开发**」→ `YDZB1812336A` 的名称 `【2018年诈骗电话共享平台建设平台TD】 技术开发合同` 被「技术**开发**」命中 → 误判**服务类** → 连带把 2.1 的「开发完成日」合法化成 `service_end_date`，**等于把 #2 这条真缺陷洗成合法取值**。

**用户原话**：「YDZB1812336A 这个合同是技术开发合同，也不是服务类啊」—— 正确。核对《民法典》：技术合同为**独立合同类型**（技术开发 / 转让 / 许可 / 咨询 / **技术服务**），**技术开发合同的标的是交付开发成果，不是持续提供服务** → 应归**非服务类**。

**已修 4 处代码/规格 + 1 处连带错误**：

| # | 位置 | 改动 |
|---|---|---|
| 1 | `prompts/contract_review.yaml` prefill `system` 段 | 词表删「开发」；新增显式反例（「技术开发合同」「技术开发（委托）合同」一律非服务类；带「技术」二字不因此归服务类；「技术**服务**合同」归服务类） |
| 2 | 同上 `user` 段「三、硬性要求」 | 同步删「开发」，加「⚠️「开发」不算，**技术开发合同按非服务类**」 |
| 3 | `prefill_prompts.py` `_FIELDS["contract_info"]` | 词表删「开发」，补全为 服务/运维/运营/咨询/设计/监理/外包/维护/技术支持/实施/集成/培训；加「⚠️「开发」不算，「技术开发合同」按非服务类」 |
| 4 | spec delta `:151` + Scenario `合同名称无法判断时按非服务类处理` 后 | 词表删「开发」+ 写反例；**新增 Scenario `技术开发合同按非服务类处理`** |
| 5 | 🔴 **连带错误**：spec delta `:151` 与 Scenario `服务类合同的服务结束时间可取自合同完成日` 的 WHEN 行**原先拿「…平台建设 技术开发合同」当服务类正例** | 换成「…运维服务合同」「…平台建设及技术**服务**合同」；该 Scenario 里的完成日示例也换成中性日期 `"2020年6月30日"`，避免再引用本合同原文 |

**✅ 结论回到：`YDZB1812336A` = 非服务类 → #2 缺陷成立**（`service_start_date=null` 而 `service_end_date` 有值 = 起止不成对；该值取自 2.1 开发完成日而非服务条款）。「允许只有 `service_end_date` 有值」**只适用于服务类合同**。

⚠️ **服务类分支目前无实测覆盖**：三份样例里只有 `c3`（`智慧园区综合管理平台建设及技术服务合同`）命中服务类，而它没有「合同完成日」可被误取 → 该分支需在真机上单独验一次。

**已配反向断言防回退**（`test_prefill_prompt_carries_contract_type_rule`）：① 必须显式写明「技术开发合同」按非服务类；② 服务性质词表里不得再出现裸露的 `服务/开发`。→ 有人再把「开发」加回词表会立刻红。

📌 **教训**：一份"从宽"的正向词表，只要混进一个**与目标语义相反的词**，就会把缺陷洗成合法 —— 这类错误**不报错、只静默改变结论**，故判据类词表必须配反向断言。

**本轮同步面（4 处文档 + 2 处测试）**：

| 面 | 改动 |
|---|---|
| spec delta | `spec:149`/`:150` 拆为「严格版条款 + 分类型嵌套条款」；Scenario `服务类日期字段的来源` → **拆成 3 条**（`非服务类合同的服务日期来源` / `服务类合同的服务结束时间可取自合同完成日` / `合同名称无法判断时按非服务类处理`）；`计划类日期字段未必是可解析日期` 的交叉引用同步 |
| prompt | `contract_review.yaml` prefill `system` 段 + `user` 段「三、硬性要求」的服务日期条 → 分类型表述 |
| `prefill_prompts.py` | `_FIELDS["contract_info"]` 两行日期规则 → 分类型表述 |
| 接口文档 | §4.3 两组行改写 + 新增 🔷 判定说明段（「你方不需要做任何事」）；§8 第 4 条；**§9 新增第 17 条**（服务日期与合同类型自检，3 份合同 ①②③） |
| 消费方增量说明 | §2.3 改题 `服务日期字段收紧取值范围（并按合同类型分路）` + 类型表；§3 的 `service_end_date` 行改为「两可」 |
| 测试 | `test_prefill_prompt_carries_service_date_source_rule` 扩注释；新增 `test_prefill_prompt_carries_contract_type_rule`（断言含 合同名称 / 服务类 / 非服务类 / 读不到合同名称 / 完成·交付截止日）、`test_prefill_request_has_no_contract_type_field` → **52 passed** |

**未同步的一处（有意）**：历史实施计划 `docs/superpowers/plans/2026-09-16-contract-review-mvp-prefill.md` 内嵌的口径快照按 §12 / §13 / §14 同一惯例不动；口径以设计文档、spec delta 与本文件为准。

**第十七轮 · 服务性质词表按"软件公司的服务类合同"收窄（2026-10-07）**

**起因**：用户就第十六轮收口回复提出两点 —— ① 追问「千分位什么时候被剥？」（质疑上一轮的判断）；② 「服务类合同的范围太大了，比如**开发、咨询、设计**等等这些都不是服务类合同，我们公司是软件公司，**按软件公司的服务类合同来缩小范围**」。

**🔴 纠错一：上一轮"千分位早已被剥"的结论是错的（已作废）**

上一轮我在审核表里写「接口文档 §4.2 原来自相矛盾：声称"符号与小数都保留"，但**千分位其实早已被剥**」—— **该判断错误**。回原文核验后的事实链：

| 时间 | 事实 | 依据 |
|---|---|---|
| 2026-09-17（第十轮） | 口径定「原文原样」，**保留**货币符号 / "元" / **千分位** | `tasks.md` §10 `:118` 明写"金额：**保留货币符号 / "元" / 千分位**"；`prefill_schemas.py` 头注"**不去千分位**" |
| 2026-09-17 实测 | `contract_amount` → `"¥10492500.00"` | `tmp/_verify_verbatim.py` 实测；`memory/2026-09-17.md:75` |
| **原文本身** | `tmp/samples/c1.md` 第一条写的是 `（¥10492500.00）` —— **本来就没有逗号** | 直接读样例原文 |
| 2026-10-03（第十五轮） | **这才第一次**把千分位 `,` 加入删除集 | `spec:142`、`proposal.md:20` |

**结论**：**千分位在 2026-10-03 之前从未被剥过**；实测返回没逗号是**照抄原文**（原文就没逗号）。我上一轮之所以判错，是因为把接口文档 §4.2 示例**输入列**里那个被美化过的 `¥10,492,500.00`（带逗号）当成了真实原文。
→ **该行真正的毛病是"示例的输入列不忠实于真实原文"**（把 `¥10492500.00` 写成 `¥10,492,500.00`），**不是**"文档口径与实现不符"。而 2026-10-03 起新口径确实要剥千分位，故该行结论现已自洽。
→ 📌 **教训（同类错误第二次）**：与"`currency` 恒 `CNY`"、"'开发'入词表"同源 —— **凡要写进结论的"原文事实"，必须当场回原文核验**；示例里的输入列不是原文，不能当原文用。核验成本 = 一次 `grep` 样例文件。

**🔴 修正二：服务性质词表 16 → 7 → 5（两轮收窄），反例词 9 → 11**

按"**软件公司的服务类合同**"（= 持续投入人力或技术提供服务，而非交付一次性成果）收窄，用户分两轮追加：

| 轮次 | 用户原话 | 正向词表 | 反例词表 |
|---|---|---|---|
| 第一轮 | 「服务类合同的范围太大了，比如开发、咨询、设计等等这些都不是服务类合同…按软件公司的服务类合同来缩小范围」 | 16 → **7**（`服务`/`运维`/`运营`/`维护`/`技术支持`/`外包`/`培训`） | 9 个（`开发`/`咨询`/`设计`/`集成`/`实施`/`监理`/`勘察`/`检测`/`评估`） |
| 第二轮 | 「**外包、培训也去掉**」 | **7 → 5**（`服务`/`运维`/`运营`/`维护`/`技术支持`） | **11 个**（上列 9 个 + `外包`/`培训`） |

**判据**：反例词本身不表示"持续投入人力或技术为对方提供服务"，其标的多为**一次性交付成果**、**劳务事项**，或属**独立的合同类型**（《民法典》技术合同族：技术开发 / 转让 / 许可 / 咨询 / 技术服务）；名称带「技术」二字也不因此归服务类。
**🔴 关键边界（用户第二轮专门追问）**：用户问「如果是**集成服务合同**，会判断为什么类型？」→ 答：**服务类**（命中「服务」二字）。**反例词没有否决权** —— 名称里只要出现「服务」二字就一律判服务类，哪怕同一名字里还带着「集成」「设计」「外包」。（删掉「集成」这个词对「集成服务合同」的判定**没有任何影响**。）
→ ✅ **2026-10-07 用户拍板：保持现状（方案 A）**。曾同时提出**方案 B**（反例词升级为否决票：名称含交付型词即判非服务类，则「集成服务合同」→ 非服务类，更贴合"软件公司服务类 = 纯服务/运维"），用户选择 **A**。**故反例词 SHALL 只作补充判据、不作否决票；后续不要改成 B。** 已知并接受的代价：名称含「服务」二字但实为项目交付型的合同仍判服务类。
**影响面**：三份样例结论**不变**（`c1`/`c2` 无标题 → 非服务类；`c3` `…建设及技术**服务**合同` → 服务类）；`YDZB1812336A`（技术开发合同）仍为**非服务类** → **#2 缺陷结论不变**。已新增 spec Scenario `含「服务」二字的复合名仍按服务类` 固化该边界。

**本轮同步面（代码 2 + 测试 1 + 文档 5 + 技能 1）**：

| 面 | 改动 |
|---|---|
| prompt | `contract_review.yaml` prefill `system` 段词表 16 → 5，11 个反例词显式点名（"都不算服务性质词，单凭它们不得判服务类"）+ "含服务二字仍服务类"的示例（含「集成服务合同」）；`user` 段「三、硬性要求」同步 |
| `prefill_prompts.py` | `_FIELDS["contract_info"]` 的 `service_end_date` 词表同步收窄 |
| spec delta | `:151` 词表 16 → 5 + 反例词显式列举 + "反例词没有否决权"；Scenario `技术开发合同按非服务类处理` → 改名 **`交付型合同按非服务类处理`** 并扩展至 咨询 / 设计 / 集成 / 实施；**新增 Scenario `含「服务」二字的复合名仍按服务类`** |
| 接口文档 | §4.3 的 🔷 词表与示例收窄 + "反例词没有否决权"；**§9 第 17 条自检 6 项**（③ 扩入 外包/培训 → 应为 `null`、⑥ 改为"**集成服务合同**等含服务二字 → 服务类"，标注为最易判反处） |
| 消费方增量说明 | §2.3 类型表收窄（5 词 / 11 反例） + 标注"2026-10-07 两轮收窄" + "含服务二字仍服务类" |
| scope 草案 | 头部加第十七轮行；R3 首段词表收窄 + 新增「第十七轮两轮收窄」留痕段（含 16→7→5、判据、**集成服务合同的边界问答**、影响面） |
| 测试 | `test_prefill_prompt_carries_contract_type_rule` 重写断言：正向词表必须为那 5 个、11 个反例词必须显式点名且出现"都不算"、**`集成服务合同` 必须写明为服务类**、旧词表形态不得复活（5 条反向断言） |
| 复核技能 `ltc-prefill-qa` | 词表收窄至 5 词 + 反例词扩到 11 个 + **"先看名字有没有「服务」二字"作为第一判据** + "集成服务合同 = 服务类，最容易判反" |

## 18. 修订记录：`payment_terms` 口径定案为「完整的付款触发条件句」（第十八轮，2026-10-12）

**起因**：复核东软《技术服务合同》（芜湖市妇幼保健院 0904GE彩超）d02 返回，报告见 `tmp/prefill-runs/QA-东软技术服务合同-2026-10-10.md`。该合同第四条付款条款结构为：

| 行 | 原文 | 归属 |
|---|---|---|
| 47 | `1.技术服务费总额为￥15000.00（大写人民币壹万伍仟元整）。` | 金额 → `contract_amount` |
| 51 | `合同生效后7（七）个工作日内，一次性支付全部费用…` | 付款触发条件句 |
| 53 | `付款方式：甲方自带汇票/电汇/支票；` | 支付手段 → `payment_method` |
| 55 | `乙方收到甲方相应付款后开具等额的增值税发票` | **后置型**开票义务 |
| 57 | `乙方开户银行和名称、账号为：` | 银行账号 |

我方初步把疑点框成「`payment_terms` 是否应包含发票条款」，即「付款条件句 vs 钱流转全部约定」的二选一。

**🔴 用户纠偏（2026-10-12，第 6 次同类纠错）**：该框法是**伪二分**。「甲方收到乙方开具的增值税专用发票后 30 日内付款」这一整句**本身就是一个付款触发条件**，其中的「收到发票」与「终验合格」「交付验收」**语法同构**，都是**起算锚点**（回答"什么阶段付款"），**不是**付款之外的另一类约定。→ **不存在"含不含发票"这个维度。**

**定案口径（用户裁定，无需业务方确认）**

> **`payment_terms` = 完整的付款触发条件句，其起算锚点 SHALL 一并取到。**

- 付款触发条件结构 = **【起算锚点】+【期限】+【付款动作】**。
- 起算锚点类型 = **时间**（合同生效后）/ **交付**（交付验收后）/ **验收**（终验合格后）/ **发票**（收到发票后）—— 四类**同等对待**。
- 判定含发票文字是否属触发条件**只看前置 / 后置**：前置型（「收到发票后…付款」）→ 锚点 → **取**；后置型（「收到付款后开票」）→ 付款之后的义务 → **不取**。
- 非触发条件内容一律不进本字段：后置开票义务、银行账号 / 开户行、支付手段词（后者由 `payment_method` 承接）。
- → **本合同第 55 行为后置型，当前 `payment_terms` 未取它 = 行为正确**（本次复核不构成缺陷）。

**改动清单**

- [x] 18.1 `prompts/contract_review.yaml` 的 `prefill.user` 段 `payment_method` / `payment_terms` 条重写：口径由"分期与条件条款的整段原文"改为"完整的付款触发条件句"，补锚点四类、前置/后置判据、非触发条件排除项。**`review` 的 7 条 prompt 零改动**（hunk 全落在 `prefill:` 段）
- [x] 18.2 `app/capabilities/contract_review/prefill_prompts.py` 的 `_FIELDS["contract_info"]` 同步：`payment_terms` 行按新口径重写（通用说明 + 字段级说明两处落点按既有惯例同步）
- [x] 18.3 本 change spec delta `specs/contract-review/spec.md`：① `payment_terms` 主规则改写为"完整的付款触发条件句"；② 新增专项条款「付款触发条件句的口径」（锚点结构 + 四类锚点同等 + 前置/后置判据 + 排除项）；③ Scenario `付款方式与付款条件的边界` 的 THEN 行同步；④ **新增 2 条 Scenario** —— `付款触发条件的锚点必须一并取到`（前置型发票锚点）、`后置型开票义务不进付款条件`（本合同形态）
- [x] 18.4 `tests/test_contract_review_prefill.py`：`test_prefill_prompt_carries_payment_terms_trigger_clause`（新增）—— 断言 prompt 必须写明「完整的付款触发条件句」「锚点」四类（时间/交付/验收/发票）、前置 vs 后置判据、以及排除项；并保留**反向断言**：旧的「分期与条件条款的整段原文」表述不得复活
- [x] 18.5 验证：`pytest tests/test_contract_review_prefill.py -q`、`openspec validate contract-review-mvp-prefill --strict`

**改动性质**：**纯 prompt 规则澄清 + spec 口径固化**。`payment_terms` 的 schema（`_nullable_string()`，无长度/枚举约束）、字段名、字段集合、响应结构**均零改动**；服务端业务代码**零改动**（规则只能在 prompt 层实现，服务端 SHALL NOT 做字符串后处理）。**不新增 change** —— 沿用 §11 / §13 / §14 结论：主 spec 里 prefill 出现 0 次，只能就地修订在途 delta。

⚠️ **连带待办**：口径文档中 `payment_terms` 的"整段原文"旧描述需同步修订（接口文档 `docs/integration/2026-09-16-…` §4.x 与设计文档 `docs/superpowers/specs/2026-09-15-…`），本轮暂未动。

📌 **教训（第 6 次同类错误）**：给字段划"含 / 不含"边界前，先把**句子的语法结构**拆开（本体 + 锚点/修饰），确认那个"可选项"是否真的是本体的一部分。本例中"发票"根本不是可选项，而是**锚点**。同类错误已 6 次（`currency` 恒 CNY、「开发」入词表、千分位"早被剥"、"含 guarantee 键⇒scope=all"、内网推送"凭据缺失"），**共性是凭直觉造分类而未先核验结构**。

## 19. 修订记录：服务日期禁令的作用域（第十九轮，2026-10-12）

**起因**：复核东软《技术服务合同》（芜湖市妇幼保健院 0904GE彩超）d02，`service_end_date` 返回 `null`。合同事实：

| 位置 | 原文 |
|---|---|
| 第 15 行 | `**签订时间：** 2026 年9月4日` |
| 第 33 行 | `# 第二条乙方应按以下要求完成技术服务工作：`（= 服务条款） |
| 第 37 行 | `2.技术服务期限： 2026年9月4日 ；` |

→ 该日期**既是服务条款内的绝对日期、又与签订日同一天**。

**🔴 本轮纠正一处此前的误框（重要）**

2026-10-10 的复核报告把它写成「**两条规则冲突，需业务方拍板**」（`tmp/prefill-runs/QA-东软技术服务合同-2026-10-10.md` §五）。**该框架不准确**，本轮更正：

- 规则原文（`contract_review.yaml` §服务类）中，「**不得用合同签订日等其他日期顶替**」这句**只挂在 `service_start_date` 上**，**对 `service_end_date` 没有任何限制**；
- 因此**不存在"两条规则打架"** —— 真相是**模型把 start 的限制误用到了 end**，属**漏抽**；
- 判据澄清：`service_end_date` 只要**取值来源在服务 / 售后 / 质保条款内**即应返回，**与它是否等于签订日无关**（「期限」语义即指截止时点）。

**用户定案（2026-10-12）**：合同是"一天完成的远程单次服务"，「技术服务期限」即服务结束时间 → **`service_end_date` 应取该日期**。并确认 **Q1 不需要业务方确认**（属 prompt 澄清，非业务口径分歧）。

**修订后口径**

> 「不得用合同签订日顶替」**SHALL 仅作用于 `service_start_date`**，**SHALL NOT 作用于 `service_end_date`**；后者只要在服务 / 售后 / 质保条款内取到绝对日期，**即使与签订日相同也应返回**。系统 SHALL 依**来源**判断，SHALL NOT 因"恰等于签订日"而丢弃。

**改动清单**

- [x] 19.1 `prompts/contract_review.yaml` 的 `prefill:` 段「服务类」条：追加作用域澄清（禁令只约束 start、end 即使同日也应返回、判据看来源）。**`review` 的 7 条 prompt 零改动**
- [x] 19.2 `app/capabilities/contract_review/prefill_prompts.py` 的 `_FIELDS["contract_info"]` 的 `service_end_date` 行同步同一澄清
- [x] 19.3 本 change spec delta：服务日期需求下**新增专项条款「「不得用签订日顶替」的作用域」**；**新增 Scenario `服务条款内的绝对日期与签订日相同时仍取作服务结束时间`**
- [x] 19.4 `tests/test_contract_review_prefill.py`：新增 `test_prefill_prompt_scopes_signing_date_prohibition_to_start_only`（断言"只约束 service_start_date"、本合同真实日期、"来源是否在服务条款内"）
- [x] 19.5 `docs/integration/…prefill-api-integration.md` §4.3 的 🔷 判定说明块补作用域澄清
- [x] 19.6 验证：`pytest tests/test_contract_review_prefill.py -q` → **54 passed**；`openspec validate contract-review-mvp-prefill --strict` → **is valid**；yaml diff 两 hunk 均落在 `prefill:` 段
- [x] 19.7 **东软合同 d02 实跑（8 次）** → 🔴 **修复有效但未达稳定**：

  | 字段 | 改前 | 改后（8 次） | 判定 |
  |---|---|---|---|
  | `service_end_date` | `null`（3/3） | `"2026年9月4日"` **6/8** | ⚠️ 从 0% 提升到 75%，但**未稳定** |
  | `service_start_date` | `null`（3/3） | `null` **5/8**（**3 次被误填为该日期**） | 🔴 **出现回归** |

  → **结论：作用域澄清改善了 target 字段，但暴露规则另一处不足** —— 模型对"同一日期该进 start 还是 end"仍不稳定（见 §19.8）。
- [x] 19.8 ✅ **已落（2026-10-12 同轮补）**：规则对「服务 / 售后 / 质保条款内以**单一绝对日期**给出『服务期限』」这一形态**缺少显式处置** —— 该日期**同时满足** `service_start_date` 的来源条件（在服务条款内）、又**触发**其禁止条件（== 签订日）→ 模型每次解析不同。**补规则：该类"单一日期 / 『期限』表述"只作 `service_end_date`，`service_start_date` 保持 `null`（「期限」语义即截止时点；单点不界定起始）。** 落点见 19.9–19.12。
- [x] 19.9 落 prompt：`prompts/contract_review.yaml`「服务类」条 + `prefill_prompts.py` 的 `service_start_date` / `service_end_date` 两行各补该规则（start 行给"本字段保持 null"直述、end 行给"只作本字段"直述，**两侧对称钉住**，防模型只读到单侧 spec 就填 start）
- [x] 19.10 spec delta：§19 专项条款下**新增「单一日期形态的处置」**；Scenario `服务条款内的绝对日期与签订日相同时仍取作服务结束时间` 加一条 AND（SHALL NOT 对称填充 `service_start_date`）
- [x] 19.11 测试：`test_prefill_prompt_scopes_signing_date_prohibition_to_start_only` 追加 4 条断言（正向 `单一绝对日期` / `只作service_end_date` / `service_start_date保持null`；反向 `对称`）
- [x] 19.12 ✅ **验证通过（目标达成）**：`pytest tests/test_contract_review_prefill.py -q` → **54 passed**；`openspec validate contract-review-mvp-prefill --strict` → **is valid**；yaml diff 仅落在 `prefill:` 段（非 prefill 各段逐行相同）。**东软 d02 复跑 ×8 → `service_end_date` = `"2026年9月4日"` **8/8**、`service_start_date` = `null` **8/8**（改前：end 6/8、start 3/8 误填）→ 稳定达标**。回归：c4（**区间型** 2026-04-01~2027-03-31 → 两字段均填，符合预期，新规则不误伤区间）/ c1（政府合同 → 两者仍 `null`，无退化）。

**改动性质**：纯 **prompt 规则澄清 + spec 口径固化**。字段名 / 字段集合 / schema / 响应结构**零改动**；服务端业务代码**零改动**（规则只能在 prompt 层实现）。**不新增 change**（沿用 §11 / §13 / §14 / §18 结论）。

📌 **本条与 §18 的对照**：§18 是"取消一个伪二分"（发票不是可选维度）；本条是"**厘清一条既有约束的作用域**"（禁令只管 start）。两条同属"**边界/作用域**"类问题 —— 与其新增规则，不如先把既有规则的适用边界读准。**教训：给"是否取某值"下结论前，先确认那条约束的 SHALL 主体是哪个字段。**

📌 **§19.8 追加教训（2026-10-12）**：**当同一个原文实体同时满足 A 字段的「取」条件、又触发 B 字段的「禁」条件时（此例：一个绝对日期既在服务条款内=start 可取的来源、又 == 签订日=start 的禁止项），只声明两条独立规则仍会随机 —— 必须在 prompt 里为这一「单一形态」显式指定唯一归属**（此处：单一日期只作 end、start 恒 null）。否则模型每次在"按来源可取"与"按禁令不可取"之间重新博弈，表现为同一合同跨次抖动。**这解释了"修复有效但不稳定"的机制**：不是规则写错，而是**该形态未被覆盖**。

---

## 20. 修订记录：九项口径定案 + 两项技术缺陷修复（第二十轮，2026-10-12）

**起因**：东软《技术服务合同》+「26年运维合同」的 d02 / d03 复核共暴露 9 项问题；业务方（吴钢 / 王晓丽）与用户于 2026-10-12 逐条定案。

**定案清单**：

| 项 | 定案 | 主要落点 |
| --- | --- | --- |
| **A1** | 金额 / 比例数值**逐字照抄本合同原文**，严禁套用示例值 / 行业惯例 | yaml 金额段 + `_FIELDS`（`payment_amount`、`guarantee.amount`）+ `_EXAMPLES`（示例值 `5%`→`8%`） |
| **A2** | `payment_terms` 取句**保留完整主语**、不得截断 | yaml + `_FIELDS` |
| **Q2** | `evidence[].section` **逐字照抄**原文标题（含空格与标点，不规范化） | yaml【章节位置】+ `_FIELDS` evidence + `_EXAMPLES`（示例改为照抄形态：无空格 + 全角冒号） |
| **Q4①** | `service_valid_months` ~~排除质保期 / 保修期 / 保密期 / **有效期**~~ → **2026-10-13 补正为「按语义取」**：「合同（的）有效期 / 本合同有效期为 N 年」**计入**（服务类合同尤其）；仅保留 质保期 / 保修期 / 缺陷责任期 / 保密期 排除。详见 **§23** | yaml + `_FIELDS` |
| **Q4②** | `inspection_count` 接受**频次表述**且**整句保留** | yaml + `_FIELDS` |
| **Q6** | 约束付款的**并列条款**并入 `payment_terms` | yaml + `_FIELDS` |
| **Q7** | 服务期为**起止区间** → `service_valid_months` = **null**（不推算） | yaml + `_FIELDS` |
| **Q8** | `guarantee.type` 的 **schema 枚举新增「预付款保函」**（金额等于预付款额者）；⚠️ **2026-10-14 收敛**：该判据**仅作负向参考**、不输出（见 **§26**） | `prefill_response_formats.GUARANTEE_SCHEMA` 枚举 + yaml / `_FIELDS` 判别规则 |
| **Q9** | `payment_method` **原文原样**（含主语 / 修饰词） | yaml + `_FIELDS` |
| **Q10** | `payment_terms` **多阶段全部拼接**（按原文顺序） | yaml + `_FIELDS` |
| ~~Q3~~ | 里程碑默认口径（`deliver` vs `begin`）—— **待业务方确认，本轮不动** | 无改动 |

**改动清单**：

- [x] 20.1 `prompts/contract_review.yaml` 的 `prefill:` 段 —— Q2 章节位置、A1 金额数值、Q4①/Q7 服务期限、Q4② 巡检、Q6/Q9/Q10/A2 付款字段
- [x] 20.2 `prefill_prompts.py` 的 `_FIELDS` —— 上述各项的**字段级**规则（`inspection_count` / `service_valid_months` / `payment_terms` / `payment_method` / `payment_amount` / `guarantee.type` / `guarantee.amount` / evidence 的 section 说明）
- [x] 20.3 `prefill_response_formats.py` —— `GUARANTEE_SCHEMA.type` 枚举**放宽**，新增 `"预付款保函"`（本轮**唯一非 prompt 改动**；仍为 `string|null`，**不新增字段 / 不改名 / 不改字段集合**）。⚠️ **2026-10-14 订正**：此"放宽"指 **schema 声明**；服务**只输出** `履约保函` / `履约保证金` 两类，其余各类仅作**负向参考**（见 §26）
- [x] 20.4 `_EXAMPLES` —— contract_plan 的 `section` 示例改为**照抄形态**（`"第四条付款方式及条件："`，去掉诱导规范化的旧示例）；guarantee 的 amount 示例值由 `"5%"` 改为 `"8%"`（避免模型照抄示例值 —— **A1 的直接诱因**）
- [x] 20.5 本 change spec delta —— 「预填字段数据契约」下追加第二十轮条款；「履约保证金多笔抽取」的 `type` 放宽并加判别；「预填原文依据标注章节位置」追加 section 逐字规则；新增 **8 条 Scenario**
- [x] 20.6 `tests/test_contract_review_prefill.py` —— 新增 `test_prefill_prompt_carries_twentieth_round_rules`（13 条断言，含反向断言"旧示例不得复活""示例值 5% 不得复活"）+ `test_guarantee_type_enum_includes_prepayment_bond`
- [x] 20.7 `docs/integration/…prefill-api-integration.md` 与设计文档同步（字段口径 + enum 放宽的下游提示）
- [x] 20.8 验证（见下）

**验证**：
- `pytest tests/test_contract_review_prefill.py -q` → **56 passed**（原 54 + 新 2）
- `openspec validate contract-review-mvp-prefill --strict` → **is valid**
- yaml diff 仅落在 `prefill:` 段（非 prefill 各段逐行相同）
- 实跑：东软 d02、26年运维 d02 / d03、c1、c4（结果见当日复习报告）

**改动性质**：**prompt 规则 + 一处取值集合放宽**。字段名 / 字段集合 / 响应结构 / 请求参数**零新增零改名**；服务端业务代码**零改动**（规则只在 prompt 层实现；`GUARANTEE_SCHEMA` 仅放宽 enum 取值）。**不新增 change**。

⚠️ **对外影响提示**：`guarantee[].type` 的 **schema 枚举**新增可取 `"预付款保函"`。⚠️ **2026-10-14 订正**：上文"新增可取"应读作 **schema 声明放宽** —— 服务**实际只输出** `履约保函` / `履约保证金` 两类；`预付款保函` 及投标 / 质量·质保 / 支付各类**仅作负向参考、不会出现在响应中**（见 **§26**）。下游若对该字段做严格枚举解析，宜认知**全部** 7 值（声明如此），但**不应期待**出现其余 5 类。

📌 **第二十轮教训**：**"示例值污染"是一类独立的失效模式** —— A1（26年运维 `50%` 被答成 `5%`）的诱因不是规则缺失，而是 prompt 示例里恰好写了 `"5%"`，模型直接照抄。**凡示例中的具体数值 / 文本，都必须选成"不可能与真实答案撞车"的值，并在规则里写明"仅格式示意、不得照抄"。** 这与 §19.8 的"形态未覆盖"不同：§19.8 是**规则缺口**，A1 是**示例污染**。


---

## §21 第三轮复核修订（2026-10-13）

**起因**：第三轮样例测试（东软 / 26年运维 / 吉林银行 / 中汇 四合同）复核；业务方答复两项口径，并暴露缺陷。

**本轮定案**：

| 编号 | 定案 | 来源 |
| --- | --- | --- |
| **Q3 / B7** | 里程碑命名：付款条件**无成果物**约定 → 视为**预付款** → 取 `启动(begin)`；**有成果物** → 按成果物取 `交付(deliver)` 或 `验收`；`contract_plan` **只从付款条件拆**，不得自造无付款金额的收尾/验收项 | 业务方 2026-10-13 |
| **B-1** | 保函 `type` 按「保函种类表」（开立方→受益人 / 担保时间段 / 核心保障 / 常见金额）判别；🔴 **不得默认归「履约保函」** | 业务方 2026-10-13 |
| **A3** | `guarantee` **不得由非担保条款生成** —— 违约责任 / 违约赔偿 / 违约金不构成担保；无独立担保条款时 SHALL 为 `[]` | 技术缺陷（吉林银行幻觉） |

**改动清单**：

- [x] 21.1 `prompts/contract_review.yaml` 的 `prefill:` 段 —— 里程碑命名口径 + 「不得自行追加无付款金额的收尾/验收里程碑」
- [x] 21.2 `prefill_prompts.py` —— `_FIELDS["contract_plan"]` 里程碑命名口径；`_FIELDS["guarantee"]` 的 `type` 判别按保函种类表重写 + **A3 负向约束**（违约金不是担保）
- [x] 21.3 本 change spec delta —— 「预填字段数据契约」加第三轮定案块；「履约保证金多笔抽取」的保函性质判别按表强化 + A3；新增 **4 条 Scenario**（无成果物取启动 / 里程碑数=付款阶段数 / 违约金不产生记录 / 付款条款保函判为预付款保函·已有）
- [x] 21.4 `tests/test_contract_review_prefill.py` —— 新增 `test_prefill_prompt_carries_third_round_rules`
- [x] 21.5 `QA-26年运维合同-2026-10-12.md` 订正 —— 其中 `type="履约保函"` 系 Q8 定案**之前**的过期结论，已加订正块

**验证**：

- `pytest tests/test_contract_review_prefill.py -q` → **57 passed**（原 56 + 新 1）
- `pytest tests/ --ignore=tests/two_stage -q` → **613 passed / 1 skipped**（`test_config.py` 一次瞬时失败 —— 因 `config/config-dev.yaml` 被外部同刻修改；单跑 **6 passed**，**非本轮引入**）
- `openspec validate contract-review-mvp-prefill --strict` → **is valid**
- yaml diff **仅落在 `prefill:` 段**（非 prefill 各段逐行相同）✅ 红线②

**改动性质**：纯 prompt 规则改动（+ spec / tasks / 测试 / QA 订正）。字段名 / 字段集合 / 响应结构 / 请求参数**零新增零改名**；服务端业务代码**零改动**。**不新增 change**。

**未落地（待用户定）**：

- **A5**（`payment_method` 丢介词「通过」）—— 轻微，可并入下次微调
- **W1**（服务期限为**绝对区间**时 `service_start_date`/`service_end_date` 双 null，疑 Q7 规则串扰）—— **需模型可达后实跑确认**再改
- ~~**Q11**（「本合同有效期为 N 年」是否算 `service_valid_months` 来源）—— 待业务方~~ → ✅ **2026-10-13 用户定案：算**（**按语义取**，不再抠字面；见 **§23**）
- ✅ **已实跑（2026-10-13 10:5x，模型服务恢复）**：A3（吉林银行 d03 `guarantee = []`，幻觉未复现）、Q3/里程碑命名（东软 1 条 `begin`、吉林银行 3 条）、A4（吉林银行恰好 3 条，无自造第 4 条）均**验证通过**。⚠️ 仍留 **W1**（吉林银行 `start` **2/3**）与 **中汇 `contract_plan` 抖动**（均**非本轮引入**）→ `tmp/prefill-runs/实跑复核-2026-10-13.md`

---

## §22 第三轮补充：`guarantee.type` 取值集合扩至「保函种类表」全量（2026-10-13）

**起因**：§21 落地后 `guarantee.type` 仍只有 3 值（`履约保函` / `履约保证金` / `预付款保函`），业务方「保函种类表」其余类型**不可作为取值**（合同出现时只能返 `null`）—— 即"判别规则已覆盖、但取值取不出来"。用户 2026-10-13 指示**扩到表内全部类型**。

**业务方口径（用户 2026-10-13 答复）**：

| 项 | 定案 |
| --- | --- |
| 表内「质量·质保保函」 | 实为 **`质量保函` / `质保保函` 两种类型**（**说明相同**），拆为两个取值 |
| `履约保证金` | 表内**无此项**，按**合同实务常见概念**保留（不删） |
| d03 实际命中 | 仅 `履约保函` / `履约保证金` **两种**；`预付款保函` 与 投标 / 质量 / 质保 / 支付 **地位相同**，均为**兼容覆盖** |

**最终取值集合（7 值 + `null`）**：`履约保函` / `履约保证金` / `预付款保函` / `投标保函` / `质量保函` / `质保保函` / `支付保函`，或 `null`。

**改动清单**：

- [x] 22.1 `prefill_response_formats.py` —— `GUARANTEE_SCHEMA.type` 枚举由 3 值扩为 7 值（注释同步）
- [x] 22.2 `prefill_prompts.py` —— `_FIELDS["guarantee"]` 的 `type`：候选值列全 + 新增 投标 / 质量·质保 / 支付 三类判据（按**担保标的**）+ `履约保证金` **实务定位**说明；删除旧「其余种类**不在本字段可选值内** / 取值集合是否扩充**待业务方确认**」表述
- [x] 22.3 本 change spec delta —— 「履约保证金多笔抽取」的 `type` 取值与取值集合段改为 7 值 + 新增三类判别 + 新增 Scenario「保函种类表内其余类型可被归类」
- [x] 22.4 `tests/test_contract_review_prefill.py` —— `test_guarantee_type_enum_includes_prepayment_bond` 断言改 7 值；新增 `test_prefill_prompt_carries_guarantee_type_catalog`（正向 4 类 + 反向断言「旧表述不得复活」）
- [x] 22.5 `docs/integration/…prefill-api-integration.md` 与设计文档同步（enum 全量 + 下游提示）
- [x] 22.6 验证（见下）

**验证**：

- `pytest tests/test_contract_review_prefill.py -q` → **58 passed**（§21 的 57 + 新 1）
- `openspec validate contract-review-mvp-prefill --strict` → **is valid**
- 本轮**未改 `prompts/contract_review.yaml`**（该文件不含 type 枚举）

**改动性质**：**一处取值集合放宽**（扩 enum）+ 对应 prompt 判别。字段名 / 字段集合 / 响应结构 / 请求参数**零新增零改名**；服务端业务代码**零改动**（仅 `GUARANTEE_SCHEMA` 放宽 enum 取值）。**不新增 change**（就地修订在途 delta）。

⚠️ **对外影响提示**：`guarantee[].type` 新增可取 `投标保函` / `质量保函` / `质保保函` / `支付保函`（叠加 §20 的 `预付款保函`）。下游若对 `type` 做**严格枚举解析**，需同步兼容**全部**取值，否则遇到新值可能反序列化失败。

📌 **本轮教训**：**「取值集合是业务概念的表征，不是技术便利」** —— §21 已把业务方表的 3 列判据写进 prompt，却仍锁死 3 值枚举，于是"规则覆盖了、值取不出来"（合同写 质量保函 时只能返 `null`）。**凡业务方给出了分类全集，取值集合 SHALL 与全集对齐**；若某类不在全集内（如 `履约保证金`），须显式记录"按实务保留"及其理由。

> 🔴 **2026-10-14 订正（重要 —— 本节表述在"取用语义"上有歧义，已收敛）**：本节标题「取值集合扩至全量」、以及 L695「d03 实际命中仅两种；其余各类**均为兼容覆盖**」，**容易被读成「其余各类是可选输出值」—— 这是误读**。
> 用户 2026-10-14 明确：「兼容覆盖」= **负向参考**（自 2026-10-13 起就是这个意思，**不是口径变更**）：除履约 2 值外的其余 5 值，是**用来反向排除的判据库** —— 识别到是这 5 个之一，就 **100% 确定「不是履约类」→ 该条不输出**；若落在这 7 类之外、或语义判不清，**同样不输出**（宁可空、不要错位）。保留这 5 条说明的用意，是**把「不是履约类」固化成可复现判据**，避免语义不清时产生抖动。
> ⇒ **结论**：§22 的「enum 扩为 7 值」**作为 schema 声明仍然保留**（`GUARANTEE_SCHEMA` 不动），但 **prompt 层的取值约束收敛为「只输出履约两类」**。完整定案见 **§26**。

---

## §23 第三轮再补正：`service_valid_months` 由「字面」改为「语义」+ d03 命中面澄清（2026-10-13）

**起因**：用户两条澄清 ——

1. **d03 命中面澄清**：d03 **只命中 `履约保函` / `履约保证金` 两种**；`预付款保函` **与其余各类地位相同**，均为**兼容覆盖**（§22 曾写成"主要命中含预付款保函"，**已订正**）。⚠️ **2026-10-14 补注**：此处「兼容覆盖」= **负向参考**（命中即排除、**不输出**）；`预付款保函` 等**不是候选输出值** —— 完整定案见 **§26**。
2. **Q4① 过死（Q11 定案）**：Q4① 原规定 `service_valid_months` 只取「服务期 / 服务期限」**字面**，且把「**有效期**」列入黑名单 —— 导致「**本合同有效期为两年**」（服务类合同，语义明显即服务期限）被排除。用户定案：**以语义为主、不能写太死**；"明显的"可写死，但「合同有效期为 N 年」模型很容易识别为服务期限 ⇒ **改**。

**本轮定案**：

| 编号 | 定案 | 来源 |
| --- | --- | --- |
| **Q11**（原**唯一**待确认项，现已定案） | 「本合同有效期为 N 年」**算** `service_valid_months` 来源 —— **按语义取**；`Q4①` 由「字面」**改为「语义」** | 用户 2026-10-13 |
| **Q4①′** | 仍**写死排除**的仅：**质保期 / 保修期 / 缺陷责任期 / 保密期**（属售后质量责任期 / 保密义务期，与"服务持续多久"无关） | 同上 |
| **Q4①″** | 同时出现「服务期」与「合同有效期」时，**以「服务期 / 服务期限」为准** | 同上（本方案新增，防随机 —— §19.8 教训） |
| **新增护栏** | 字段名 `months` **仅为命名**，返回**原文写法**、**绝不折算为月数**（"两年" ≠ "24"） | 用户指出字段名可能诱导折算 |

**改动清单**：

- [x] 23.1 `prompts/contract_review.yaml` `prefill:` 段 —— `service_valid_months` 段由「只取字面 + 有效期黑名单」改写为「**按语义取**」三分支（算 / 不算 / 区间→null）+ months 反折算护栏
- [x] 23.2 `prefill_prompts.py` `_FIELDS["contract_info"]` 同步；并订正 `_FIELDS["guarantee"]` 里「d03 实际主要命中…」的表述
- [x] 23.3 本 change spec delta —— 「预填字段数据契约」的 Q4① 条款改写；新增 Scenario「服务类合同的『合同有效期』计入服务有效期限」；「履约保证金多笔抽取」的 d03 命中表述订正
- [x] 23.4 `prefill_response_formats.py` 注释订正（d03 命中**仅两种**）
- [x] 23.5 `tests/test_contract_review_prefill.py` —— `test_prefill_prompt_carries_twentieth_round_rules` 的 Q4① 断言改为「按语义取 / 本合同有效期为两年 / 缺陷责任期 / 绝不折算成月数」（原断言 `"都不属于"` 已随措辞改写而失效 → 一并更新）
- [x] 23.6 `docs/integration/…prefill-api-integration.md`（10-12 备注 + §4.5 字段行）与设计文档 §4.1 同步
- [x] 23.7 护栏措辞改**双向**（用户担心"原文本身是月、会不会被改成非月"）：显式写明「原文写"13.5个月"就**照抄**"13.5个月"，不得改写成"1年"或其它形式」+「**两个方向都不许换算**」；同步 yaml / `_FIELDS` / spec / 接口文档 §4.5 / 设计文档 §4.1，测试加断言 `两个方向都不许换算`、`13.5个月`
- [x] 23.8 验证（见下）

**验证**：

- `pytest tests/test_contract_review_prefill.py -q` → **58 passed**
- `openspec validate contract-review-mvp-prefill --strict` → **is valid**
- `tmp/check_yaml_sections.py` → 非 prefill 各段逐行相同（本轮改的是 `prefill:` 段）✅ 红线②
- ✅ **实跑（2026-10-13 10:5x，模型服务恢复）**：中汇 d02 `service_valid_months = '两年'` **3/3**；东软 / 吉林银行（反例）均 `null` **未误取**；吉林银行 d03 `guarantee = []`（A3 幻觉未复现）；26年运维 d03 `('预付款保函','50%')`。明细见 `tmp/prefill-runs/实跑复核-2026-10-13.md`
  - ⚠️ **2026-10-14 订正**：其中「26年运维 d03 `('预付款保函','50%')`」是**旧口径下的越界输出** —— 合同该处「合同总金额的50%保函」属**预付款保函**，按 **§26** 定案（只输出履约两类）该合同 d03 **应为 `[]`**。当日本项曾被标 ✅（`2026-10-13.md` L196），**该标记亦错**。

**改动性质**：**prompt 规则改动 + 一处 spec 口径变更**（Q4① 由字面改语义）。字段名 / 字段集合 / 响应结构 / 请求参数**零新增零改名**；服务端业务代码**零改动**。**不新增 change**（就地修订在途 delta）。

⚠️ **需知会**：Q4① 原为 **2026-10-12 业务方（吴钢 / 王晓丽）定案**，本轮**修订其「有效期」部分**（吴钢如参与原定案，建议同步知会）。

**实跑结论（2026-10-13 10:5x，模型服务已恢复）**：中汇 d02 `service_valid_months = '两年'` **3/3**（Q11 语义化达成）、东软 / 吉林银行（**反例**）均 `null`（未误取）。⚠️ 但顺带证实 **W1 仍未收敛**（吉林银行 `start` **2/3** 有值）与 🆕 **中汇 `contract_plan` 抖动**（3 次 3 形态），**二者均非本轮引入** → 详见 `tmp/prefill-runs/实跑复核-2026-10-13.md`。

📌 **本轮教训（两条）**：
1. **「写死」与「智能」的边界**：把字段来源写成**字面白名单**，看似精确，实则把**语义等价**的表述（合同有效期 = 服务期限）一并挡在门外 → 字段大面积空。**来源判定宜用语义判据 + 少量"明显不同"的写死排除**；用户原话："限制这么死就不是智能了，那不就成了纯编码了吗"。
2. **字段名会诱导输出**：`service_valid_months` 里的 `months` 有把模型推向"折算月数"的风险（Q7 案例中模型确曾把 1 年区间答成 `"12个月"`）。**凡字段名与目标类型不一致（名含 month 但要求原文写法），都要在 prompt 显式声明"名仅为命名、返回原文"**。


---

## §24 第二十四轮 —— 「措辞触发」改「形态判据」（W1）+ 示例必须与规则同向（A5）

**触发**：用户 2026-10-13 判定两件事 —— ① 规则 A（服务期限「单一绝对日期 / **「期限」表述**」→ 只作 `service_end_date`、`service_start_date` 保持 `null`）**触发条件过死**：*「用『期限』这个词去猜语义，把『技术服务**期限**：**自 X 到 Y**』（明明是区间）也吞了」*；② `payment_method` 旧示例②**示范截取**，与同段规则「不得删主语或修饰词」**不同向** → 模型跟示例走，用户定调：**「示例导致的模型无脑使用，这个必须杜绝，示例只是举例子，不能偷懒直接用」**。

### 定案（用户 2026-10-13）

| 项 | 口径 |
| --- | --- |
| **W1 判据** | `service_start_date` / `service_end_date` 的触发条件由**措辞**（标题里有没有「期限」二字）改为**形态**（服务条款内**绝对日期的个数**） |
| **W1 分流** | **1 个绝对日期** → 只作 `service_end_date`，`service_start_date` 保持 `null`（结论不变）；**2 个、构成区间** → **起点 → `service_start_date`、终点 → `service_end_date`，两端都必须取**（新增） |
| **互斥性** | 两分支按**日期个数**严格互斥 ⇒ 区间规则**不影响**单一日期分支 |
| **Q7 边界** | `service_valid_months` 的「起止区间 → `null`」**只作用于本字段**，**不得外溢**到日期字段（原为 W1 的放大器） |
| **A5 示例** | 删除「示范截取」的旧示例②；新增「整段照抄 + 保留介词」示例（`"通过银行转账的方式"`） |

### 改动清单

- [x] 24.1 `app/capabilities/contract_review/prefill_prompts.py`
  - `service_start_date` 段（原 L71-72）：改「先数绝对日期个数、再分流」+ 新增区间分支 + 明写「判据是**个数**，不是标题里的『期限』字样」
  - `service_end_date` 段（原 L81）：同步 —— ⚠️ 同一规则**此前在文件里重复写了两遍**，本轮两处同改
  - `service_valid_months` 段（Q7②）：加「本条只管本字段，**不得外溢到时间字段**」
  - `payment_method` 段：**删**旧示例②（`"甲方以转账方式转入指定账户"→"转账方式"`）、改「**整段表述一并照抄、不得截断**」+ 新增介词框架示例
- [x] 24.2 `prompts/contract_review.yaml` 的 `prefill:` 段 —— 三处同步（时间字段段 / `service_valid_months` 段 / `payment_method` 段）；prefill 段 **166 → 179 行**
- [x] 24.3 `openspec/…/spec.md` 就地修订 —— 改「服务条款内的绝对日期与签订日相同时…」Scenario 的判据措辞；**新增** Scenario「服务期限以绝对区间给出时两端各归其位」+「付款方式按原文整段照抄、不得截断」；`payment_method` 边界 Scenario 的「SHALL 只包含支付手段词」改为「**完整表述片段（逐字不截断）**」
- [x] 24.4 `tests/test_contract_review_prefill.py` —— A5 断言更新（删 `转账方式` 正向断言；改 `通过银行转账的方式` / `必须保留介词`；加**反向** `甲方以转账方式转入指定账户 not in flat`）；§19.8 测试补 W1 **正反向**断言（正向 `先数` / `日期个数` / `构成区间` / `两端各归其位` / `终点归service_end_date` / `两端都必须取` / `不得因为标题带` / `不得外溢到时间字段`；反向 `「期限」表述 not in flat`）
- [x] 24.5 验证（见下）

**验证**：

- `pytest tests/test_contract_review_prefill.py -q` → **58 passed**
- `pytest tests/ --ignore=tests/two_stage -q` → **615 passed, 1 skipped**
- `tmp/check_yaml_sections.py` → 非 prefill 各段**逐行相同** ✅ 红线②
- `yaml.safe_load` → OK，顶层 8 键不变
- `git diff -U0 prompts/contract_review.yaml | grep '^@@'` → 三个 hunk **全部落在 prefill 段**（242 / 265 / 334）✅
- ⏳ **待实跑**：吉林银行 d02（原文 L37「技术服务期限：自2026年09月09日到2027年9月08日」）应按**区间两端**取值；东软 d02（单一日期形态）应保持 `start=null`、`end="2026年9月4日"`

**改动性质**：**prompt 规则改动 + spec 口径变更**（时间字段判据由措辞改形态；`payment_method` 示例治理）。字段名 / 字段集合 / 响应结构 / 请求参数**零新增零改名**；服务端业务代码**零改动**。**不新增 change**（就地修订在途 delta）。

⚠️ **订正**：§23 末尾「⚠️ 需知会：Q4① 原为业务方（吴钢 / 王晓丽）定案…」一条**作废** —— 用户 2026-10-13 明确「**第 4 点不用知会，跟吴钢无关**」。

**本轮教训（三条）**：

1. 🔴 **判据要落在「形态」而非「措辞」**：用标题里的某个**词**（「期限」）去触发规则，必然把**语义等价但措辞不同**的形态（区间）误吞 → 抖动。凡判据可用**客观形态**表达（**日期个数 / 时序先后 / 结构**），**绝不写在措辞上**。
2. 🔴 **示例 ≠ 规则，且示例会「污染」规则**：prompt 里「规则说 A、示例示范 B」时，模型**永远跟示例走**（本例：规则说「不得删主语」、示例②示范「截取」→ 吉林银行「通过银行转账的方式」被截成「银行转账」）。**凡「规则句 + 示例句」并存的字段，示例必须与规则同向**；用户定调「示例只是举例子，不能偷懒直接用」。
3. 📌 **同一规则不要写两遍**：本轮规则 A 在 `prefill_prompts.py` **重复出现两次**（start 段 + end 段），改动须**三处（含 yaml）同改**，漏一处即自相矛盾。

**衍生待办（本轮排查发现，尚未处理）**：

- `yaml` L222-223「名称看不出 → 一律非服务类；**不要因为正文内容看起来像服务就改判**」—— 标题缺失时**禁止**用正文校正，风险高
- `milestone_name` 13 名清单**无「按月 / 据实结算」档** → 中汇 `contract_plan` 随机（**待业务确认**）
  - 🔴 **2026-10-14 标注：已随中汇类（服务外包类）挂起，不再需要业务确认** —— 见 §24 追加（2）③（L871/L879）。本条源自中汇，**不在本次版本范围**。
- 发票锚点判据写成**示例形态**（前置 / 后置句）而非**时序判据** → A2′ flaky
- `service_valid_months` 写死排除清单**未穷尽**（「**驻场期**」实为服务期，有误伤风险）
- **示例去值化**（`_EXAMPLES` 中 `"30%"` / `"履约保证金"` / `763200` / `"电汇"` 等可复用业务值 → 换占位）—— 面最大，**须先小样本实跑验证**

---

## §24 追加（2026-10-13 同日，用户追问引发）—— 废止「两字段必须成对」+ 单点日期按**语义方向**归位

**触发（用户原话）**：① *「这里 1 个绝对日期的做法，如果是 1 个绝对日期恰好是**开始日期**，是不是就会报错？」* ② *「**为什么『两字段必须同为 null 或同为有值』呢？哪个能取到值就给哪个值**，而不能定死必须同有值或同无值，这里为什么要定死呢？…这并不需要约束同有值同无值。」*

### 定案（用户 2026-10-13）

| 项 | 口径 |
| --- | --- |
| **单点方向** | 1 个绝对日期时**读语义指向**：指向**开始** → `service_start_date`；指向**截止** → `service_end_date`；**指向不明** → **两字段都 `null`**（用户拍板「**宁可空、不要错位**」—— 错位是**静默**错误，危害大于空值） |
| **废止「成对」** | 「非服务类两字段必须同为 `null` 或同为有值」**废止** → 改**各自独立取值**（能取到就取、取不到就 `null`） |

### 为什么原来会有「成对」—— 回查结论（关键）

- 出处 = `docs/superpowers/specs/2026-10-03-contract-review-prefill-value-rules-scope.md`（第十轮，`YDZB1812336A` 案例）：模型把 `service_end_date` 填成**履行期限条款**里的「开发内容在【2018】年【11】月【30】日完成」→ **跨条款误抓**。
- 当时用「**起止不成对**」作为**发现该 bug 的启发式判据**（同一服务条款不会只给结束不给开始）。
- 🔴 **病灶**：这个**诊断启发式**被**固化成了输出约束**「两者必须成对」—— **用错了工具**。真正治本的是**来源约束**（「只从服务 / 售后 / 质保条款取、不得用开发完成日等顶替」），而它**同时存在且已经足够**。
- **危害**：① 原文真的只给一端时（如「质保期至 2027年3月1日」）→ **能取到的也被迫丢掉**；② 与单点日期规则**直接冲突**（单点必然只让一端有值）。用户判断正确。

### 改动清单（本轮追加）

- [x] 24.6 `prefill_prompts.py` —— ① 单点分支加**方向判据**（`service_start_date` 段 + `service_end_date` 段**两处同改**）；② `service_end_date` 段开头**删**「两者必须同为 null 或同为有值」→ 改「🔴 **两个时间字段各自独立取值**」
- [x] 24.7 `prompts/contract_review.yaml` —— 三处同改（非服务类段 / 单点方向段 / user 段「非服务类」括注）
- [x] 24.8 `spec.md` —— L152 改「各自独立取值」并注明原约束**已废止**；「单一日期形态的处置」改写为「**日期个数分流**」（区间 + 方向三分支）；**新增** Scenario「**单一绝对日期的归位按语义方向**」；「非服务类合同的服务日期来源」Scenario 的成对断言改写
- [x] 24.9 `tests/test_contract_review_prefill.py` —— `test_prefill_prompt_carries_service_date_source_rule` docstring 订正（说明「成对」本是启发式、已废止）+ 断言 `各自独立取值` / `同时有值` / `同时为空` + **反向** `同为null not in flat`、`必须成对 not in flat`；§19.8 测试补 `指向开始` / `指向截止` / `指向不明` / `宁可空` / `不要错位` / `方向看`
- [x] 24.10 文档同步 —— `docs/integration/…prefill-api-integration.md`（非服务类行 + 「单一日期形态」行改写为「日期个数分流」）；`docs/合同评审能力-PRD.md` L324；`docs/superpowers/specs/2026-10-03-…scope.md` 表格行 + 文末**加订正块**（历史文档不删原文，追加订正）

**验证**：

- `pytest tests/test_contract_review_prefill.py -q` → **58 passed**
- `openspec validate contract-review-mvp-prefill --strict` → **is valid**
- `tmp/check_yaml_sections.py` → 非 prefill 各段**逐行相同** ✅
- ✅ 实跑已完成，结果见 **§24 追加(2) 的「验证」**（吉林银行/东软/26年运维 d02 ×3 全部符合预期）

**本轮教训（第四条）**：

4. 🔴 **不要把「诊断启发式」写成「输出约束」**：「起止不成对」是**发现误抓的信号**，不是**对输出形态的要求**。前者用于**排查**（看到不成对 ⇒ 去查来源），后者会**逼着系统丢数据**（原文只给一端时）。**写规则前先问：这句是在描述"正确输出长什么样"，还是在描述"什么样的输出可疑"？** 后者不该进取值规则。

## §24 追加（2）（2026-10-13 同日，用户四答落定）—— A5 改「去介词」+ 废止「叠加示例」+ 中汇挂起

**触发（用户原话）**：
> ① *「保留『银行转账』就可以，不需要保留介词，甚至不需要『的方式』这种…**之前为啥会有保留介词的断言？**」*
> ② *「我认为**不应该通过叠加示例的方式，因为穷举不完**。之所以出现 #2 的问题，不就是因为给示例之后，限制了模型。」*
> ③ *「中汇属于是**服务外包类**的合同，这种合同先不用管了。**当期阶段不用考虑这种类型的合同**。」*

### 定案

| # | 项 | 口径 |
| --- | --- | --- |
| **①** | `payment_method` | **只取支付手段本体、去掉包着它的框架词** —— **介词**（通过/以/用/经由）、**支付动词**（转入/支付/汇入/划付）、**「的方式 / 方式」**一律**去掉**（「通过银行转账的方式」→ `"银行转账"`）。⚠️ **唯一例外**：原文「付款方式：**甲方自带汇票/电汇/支票**」→ `"甲方自带汇票/电汇/支票"`（该表述**无框架词可去**、是**唯一**完整表述，去掉会丢"由谁以何形式提供"的信息） |
| **②** | 覆盖问题 | **不靠叠加示例**（穷举不完）→ 改为**把规则写足** + 明写「**上例仅为举例、不是穷举**」（区间前有无引导词 / 是否独立小节 / 是否嵌长句 **均不影响判定**），判据落**形态（日期个数）** |
| **③** | 中汇（技术人力外包服务合同） | 属**服务外包类**，**当期阶段不考虑该类型** → `contract_plan` 抖动**挂起**，不再需要业务确认 |

### 「之前为啥会有保留介词的断言？」—— 回查结论（关键，用户追问）

- 直接源头 = **第二十轮定案**（`2026-10-12.md`）那句：「**`payment_method` = 原文原样（含主语/修饰词，不提炼不编造）**」—— 该句被**过度推广**成「整段照抄、含介词」，再叠加 `evidence.section`「**逐字照抄**」的口径惯性（同一文件、同一轮定案）。
- 🔴 **但同一份定案里的 c1 例子恰是「以转账方式 → `转账方式`」（=去了介词「以」）** —— **两者本就自相矛盾**。
- 🔴 我在上一轮改 A5 时**只读了规则句、没有回查 c1 那个例子**，于是把「**必须保留介词**」写进了 prompt ⇒ **这是我的疏漏**，也是本次 A5 从「保留介词」翻转为「去掉介词」的根因。
- 教训并入 §24 首节教训③（示例必须与规则**同向**）：**规则内自相矛盾时，模型永远跟示例走** —— c1 例子已经给了「去介词」的行为示范。

### 改动清单（本轮追加 2）

- [x] 24.11 `prefill_prompts.py` —— `payment_method` 段改写「取手段本体、去框架词」+ 唯一例外；`service_start_date` 段与 `service_end_date` 段**两处**均补「**非穷举**」声明
- [x] 24.12 `prompts/contract_review.yaml`（prefill 段，166→196 行）—— `payment_method` 段改写；时间字段段补「非穷举」；`payment_method`↔`payment_terms` 边界句改「取支付手段本体」（去其介词/动词/「的方式」）
- [x] 24.13 `spec.md` —— `payment_method` 规范句（L161）+ Q9 条（L169）改写为「手段本体」；Scenario「付款方式与付款条件的边界」改写、原「付款方式按原文整段照抄、不得截断」Scenario **改名为**「付款方式只取手段本体、去掉框架词」并重写断言；原「payment_method 保留原文主语与修饰词」Scenario 改为「**唯一例外**」并声明**不得推广**；`日期个数分流` 条补「非穷举」声明
- [x] 24.14 `tests/test_contract_review_prefill.py` —— A5 断言翻转（正向 `取原文里` / `去掉包着它的框架词` / `一律去掉` / `唯一例外`；**反向**删 `必须保留介词`、`整段表述一并照抄`）；W1 测试新增「非穷举」断言（`上例仅为举例` / `不是穷举` / `不影响判定`）
- [x] 24.15 文档同步 —— `docs/integration/…prefill-api-integration.md` L257、`docs/superpowers/specs/2026-09-15-…design.md` L159 改为「去介词、取手段本体」口径

**验证**：

- `pytest tests/test_contract_review_prefill.py -q` → **58 passed**
- `pytest tests/ --ignore=tests/two_stage -q` → **615 passed, 1 skipped**
- `openspec validate contract-review-mvp-prefill --strict` → **is valid**
- `tmp/check_yaml_sections.py` → 非 prefill 各段**逐行相同** ✅；`git diff -U0 yaml` 7 hunk **全落 `prefill:` 段**
- **实跑（vLLM HTTP 200，`tmp/run_qa_round4.py`）**：
  - 吉林银行 d02 ×3 → `payment_method='银行转账'` **3/3**（去介词生效 ✅）；`start='2026年09月09日'`+`end='2027年9月08日'` **3/3** ✅
  - 东软 d02 ×3 → `payment_method='甲方自带汇票/电汇/支票'` **3/3**（例外保留 ✅）；`start=None`+`end='2026年9月4日'` **3/3** ✅
  - 26年运维 d02 ×3 → `payment_method=None` **3/3** ✅；`start='2026年1月1日'`+`end='2026年12月31日'` **3/3** ← **裸区间漏取（曾 4/6）已解决** ✅（「非穷举」声明见效，印证用户「示例被当穷举」的判断）
  - ⚠️ **残留 flaky**：吉林银行 `service_valid_months` run3 = `'一年'`（**1/3**，服务期以**区间**给出时**应为 `null`**）→ Q7 规则在**区间形态**下仍有抖动，**待后续观察 / 强化**（未列入本轮改动）

### #4（待解释）—— 4 条衍生待办（源自第二轮复核，与 #1–3 无关，暂未动）

① yaml L222-223「名称看不出 → 一律非服务类；不要因为正文内容看起来像服务就改判」（标题缺失时禁止正文校正）；
② 发票锚点判据写成**示例形态**而非**时序判据**（治 A2′ flaky）；
③ `service_valid_months` 写死排除清单未穷尽（「**驻场期**」实为服务期，**误伤**风险）；
④ **示例去值化**（`_EXAMPLES` 里 `"30%"` / `"履约保证金"` / `763200` / `"电汇"` 等**可复用业务值** → 换占位）。⚠️ 其中 ④ 与用户 #2「不应靠示例」的立场**需重新对齐**。

## §25 第二十四轮·补 —— 服务性质词表补入 `维保`（5 → 6 词）

**触发（用户提供实证）**：`淮安市第一人民医院分院PACS系统维保采购项目合同-2026.md`。用户判定"这好像就是一个服务合同"，让我判断。

**核验结论**：**是服务合同**，但**按原规则会被判「非服务类」**。
- 服务合同依据：第二条「**服务期**1年，自2026年8月1日起至2027年7月31日止」；第三条 1.2/2.1「提供**技术支持与维护升级**」；第四条「**服务内容及要求**」；附件1「PACS**维保服务**内容及需求」。
- 🔴 **误判根因**：判据只看**合同名称**，名称用「**维保**」；而 `维保` ≠ `维护`，**不在 5 词表里** → 命中不到 → 非服务类。这是**词表漏词**，**不是**"标题读不到"。

**定案（用户「先做A」）**：`维保`（= 维护 + 保养）完全符合"持续投入人力或技术为对方提供服务" → **补入正向词表，5 → 6 词**：
`服务` / `运维` / `运营` / `维护` / `技术支持` / **`维保`**

### 讨论中厘清的两条原则（一并固化）

1. 🔴 **为什么不改用"正文语义判断"**（用户追问：「既然你能判断是服务合同、有证据，为什么要用词表？」）：
   词表的价值**不是"代替判断"，而是把判断固化成一个可复现的判据**。改成语义判断的代价 —— ① **不可复现**（抖动；W1 / A5 / 后置发票句均已实测 flaky）② **不可测**（无断言可锁边）③ **不可审计**（答不出客观依据）④ **不可迁移**（换模型结论变）。
   ⇒ **扩覆盖应"扩大可复现判据的取用范围"，而非放弃可复现判据。**

2. 🔴 **标题兜底的必要性与风险**（用户追问：「用标题行匹配会不会把带『服务内容』章节的开发合同误判？」）：
   风险**成立**（开发 / 集成 / 实施合同普遍带「技术支持」「售后」章节）。但**"名称读不到才启用标题兜底"这道闸门已排除它** —— 开发/集成合同**名称读得到**（含 `开发`/`集成`）→ 走名称判定 → 非服务类 → **不进入标题匹配**。
   ⇒ **本案例是"词表漏词"，补词表即可解决，不需要引入标题匹配**。标题兜底**无实证、且正是误判源 → 暂不做**（YAGNI）；若将来有真实"名称读不到"案例再做，判据限定"仅此闸门 + 反例词冲突则退回非服务类"。

### 改动清单

- [x] 25.1 `prefill_prompts.py` —— 词表 `服务/运维/运营/维护/技术支持` → `…/技术支持/维保`，并写明「维保 = 维护 + 保养，属服务性质词（2026-10-13 补）」
- [x] 25.2 `prompts/contract_review.yaml` —— system 段词表 + user 段词表**两处**同步补 `维保`
- [x] 25.3 `spec.md` —— L151 规范句补 `维保`（附语义说明）；**新增 Scenario**「「维保」类合同按服务类处理」；L350 由"只有名称含「服务」二字"改为"名称含服务性质词（含 维保）"
- [x] 25.4 `tests/test_contract_review_prefill.py` —— `test_prefill_prompt_carries_contract_type_rule`：正向断言改 `服务/运维/运营/维护/技术支持/维保`；新增 `维护+保养` 语义断言；**反例新增反向断言 ⑤**（`维保` 不得被塞进反例词列）
- [x] 25.5 文档同步 —— `docs/integration/2026-09-16-…prefill-api-integration.md` L281、`docs/integration/2026-10-03-…value-rules-change.md` L63、`docs/superpowers/specs/2026-10-03-…value-rules-scope.md` L67 + 文末**加「第三轮」订正块**

**验证**（见下方实跑节）：
- `pytest tests/test_contract_review_prefill.py -q` → **58 passed**
- `pytest tests/ --ignore=tests/two_stage -q` → **615 passed, 1 skipped**
- `openspec validate contract-review-mvp-prefill --strict` → **is valid**
- `tmp/check_yaml_sections.py` → 非 prefill 各段**逐行相同** ✅
- 实跑 `tmp/run_qa_round6.py`（淮安 d02 ×3）+ `tmp/run_qa_round4.py`（吉林银行 / 东软 / 26年运维 d02 ×3）→ 结果见本文件末尾补充

⚠️ **已知残余风险（接受）**：词表仍是**近似**，必然还漏词（`售后` / `驻场` / `巡检` / `保养` / `代维` / `托管` 等尚未纳入）→ 遇实证再逐个评估补入。

---

## §26 第四轮正名：`guarantee.type` 「枚举 ≠ 可选输出值」—— 其余 5 类收敛为「负向参考」（2026-10-14）

**起因（用户逐字定案）**：

> 「除了履约相关的 2 个值，其他 5 个值是用来**反向参考**的，也就是通过其他 5 个值的定义，识别到是其他 5 个值的一个，那就 100% 可以确定不是履约需要的 2 个值。如果不在这 7 个值中，那也不能认为是履约的 2 个值，只是因为我现在有其他 5 个值的明确说明，所以才用于排除，避免语义不清时产生抖动。」

**背景**：§20 / §21 / §22 / §23 四轮里，`guarantee.type` 的 schema 枚举从 3 值扩到 7 值，prompt 里的判据也从「三列判别」写到「保函种类表全量」。「兼容覆盖」一词（§22 L695 / §23 L726）语义**从未被明确定义过**，于是产生两种读法：
- ❌ **误读 A**（我 2026-10-14 曾持此读法）：其余 5 类是**合法的可选输出值**，模型可据语义输出 `预付款保函` 等；
- ✅ **正解 B**（用户本意，自 2026-10-13 起即如此）：其余 5 类**不是候选值**，而是**负向参考判据库**。

**定案**：

| 编号 | 定案 |
| --- | --- |
| **D26.1** | d03 的 `guarantee[].type` **只输出** `履约保函` / `履约保证金` **两类** |
| **D26.2** | schema 枚举**保持 7 值不变**（`GUARANTEE_SCHEMA` 不动）—— 枚举是**声明**，不是**取值约束**；取值约束在 **prompt 层**实现 |
| **D26.3** | 其余 5 类（`预付款保函` / `投标保函` / `质量保函` / `质保保函` / `支付保函`）**仅作负向参考** —— 命中其一定义即 100% 确定「不是履约类」→ **该条不输出** |
| **D26.4** | **兜底**：落在 7 类之外、或语义不清 → **同样不输出**（「宁可空、不要错位」） |
| **D26.5** | 保留 5 条说明的**用意** = 把「不是履约类」固化成**可复现判据**，避免语义不清时产生抖动（即「判据可复现原则」，与 §25 词表同源） |
| **D26.6** | **26年运维 d03 的正确输出是 `[]`**（该合同「合同总金额的50%保函」= 预付款保函）；旧实跑 `('预付款保函','50%')` 属越界（§23 L754 已订正） |
| **D26.7** | 🔴 **准入闸门**（2026-10-14 **实跑后**追定）：**只有存在「为担保『按约完成 / 按期保质交付』而设的独立担保条款」时**才输出；保函 / 保证金**写在付款 / 质保售后 / 招标投标条款里的，一律不过闸门 → 不输出**（**形态判据**：看所在章节，不看保函名字 → 可复现） |
| **D26.8** | `guarantee` 的**默认输出 SHALL 为 `[]`**；**禁止「强行归类」** —— 不得因为「只允许两类」就把非履约类保函**改标成** `履约保函` / `履约保证金` |

**改动清单**：

- [x] 26.1 `prefill_prompts.py` —— `_FIELDS["guarantee"]` 的 `type` 段重写为**四层结构**：⓪ 准入闸门（形态判据）① 正向（只允许履约两类）② 负向参考（其余 4 组判据，命中即排除）③ 兜底（判不清 → 不输出）+ 输出前自检；`amount` 段去掉自引用示例
- [x] 26.2 `prefill_response_formats.py` —— `GUARANTEE_SCHEMA.type` 注释加「**枚举 ≠ 可选输出值**」说明（enum 值不变）
- [x] 26.3 本 change spec delta —— 「履约保证金多笔抽取」Requirement 首句 + **准入闸门段** + 判别块（分正向 / 负向）+ 形态判据 + 取值集合段 + 禁止强行归类段 + `type` 断言 Scenario + 两个 Scenario（「付款条款中的预付款保函**不产生记录**」「保函种类表内其余类型**不产生记录**」）
- [x] 26.4 `tests/test_contract_review_prefill.py` —— 更新 4 处 docstring / 断言（Q8 描述、第三轮 B-1 断言措辞、catalog docstring）；**新增** `test_prefill_prompt_carries_guarantee_negative_reference_rule`（含闸门 / 反强行归类 / 形态判据断言）
- [x] 26.5 `docs/integration/2026-09-16-…prefill-api-integration.md` —— L16 / L21 / §4.6 `type` 行 / §4.7 末 / §8 第 8 条（新增「有担保但均非履约类 → 也为 `[]`」这层歧义）
- [x] 26.6 `docs/superpowers/specs/2026-09-15-…prefill-design.md` —— §4.4 `type` 行 + §4.5「不在原样范围」行
- [x] 26.7 `tasks.md` —— 本 §26 + §20 / §22 / §23 加订正指向
- [x] 26.8 `prompts/contract_review.yaml` —— 🔴 **不改 type 规则**（type 属**字段级**规则，落在 `_FIELDS`，经 `{field_spec}` 注入，**不重复**）；仅修 L200-201 金额示例（去掉现已成为**负向形态**的 `"50%保函"`）
- [x] 26.9 ⭐ **`_EXAMPLES["guarantee"]` 去值化**（实跑暴露）—— 原示例含 `"type": "履约保证金"`（**真会输出的值**）→ 直接诱发「示例值污染」；已改为 `"type": null`（与 `contract_info` 示例同风格），evidence 一并去值
- [x] 26.10 验证（见下）

**验证（2026-10-14）**：

- `pytest tests/test_contract_review_prefill.py -q` → **59 passed**
- `pytest tests/ --ignore=tests/two_stage -q` → **616 passed, 1 skipped**（红线①：`tests/two_stage/**` 未动）
- `openspec validate contract-review-mvp-prefill --strict` → **is valid**
- `tmp/check_yaml_sections.py` → 非 prefill 各段**逐行相同** ✅（红线②）
- 🔴 **实跑（vLLM 直连，26年运维 d03 / c1 d03 / 吉林银行 d03）**：
  | 合同 | 期望 | 结果 |
  |---|---|---|
  | 26年运维 d03（付款条款内 50% 保函 = 预付款保函） | `[]` | **11/11 `[]`** ✅（含 5 次冷启动绕前缀缓存） |
  | c1 d03（第七条 独立「履约保证金」5%） | `履约保证金` / `5%` | **5/5 正确** ✅ |
  | 吉林银行 d03（全文无担保条款） | `[]` | **3/3 `[]`** ✅ |
- 📌 **改动过程中的实跑发现（重要）**：初版「只允许两类」的写法**反而更糟** —— 模型被"必须选一个允许值"的压力驱动，把预付款保函**改标成** `履约保函` / `履约保证金`（**26年运维 4/6 错**），产出**看起来合法、实则错**的值 —— 比原来的 `预付款保函`（明显越界）**更难发现**。依次补入 ①「`[]` 是常见且正确的输出」②「严禁强行归类」③「形态判据」④「准入闸门」后才收敛（**11/11**）。⇒ **「负向定义」不足以约束模型，"默认空 + 形态准入闸门"才有效。**

**改动性质**：**prompt 层取值约束收紧**（enum 不动）→ **对外接口契约零变化**；服务端业务代码**零改动**。**不新增 change**（就地修订在途 delta）。

⚠️ **对外影响提示**：**无新增取值**（反而更收紧）—— 唯一实际效果是 `guarantee` **更容易为空数组**（如有担保但均非履约类时）。下游**无需**做兼容改动。

📌 **本轮教训**：
1. **「枚举」与「可选输出值」是两件事** —— schema 可以声明一个比实际输出更大的取值空间（用于判别 / 兼容 / 未来扩展），**取值约束必须另有落点**（这里是 prompt 层）。凡用「兼容覆盖」这类未定义词，**必须当场给定义**，否则读者（包括我）会按"候选值"理解。
2. **保留判据 ≠ 承认取值** —— 保留其余 5 类定义，目的是**把"不是履约类"固化成可复现的排除判据**（同 §25「词表把判断固化为可复现判据」），**不是**把它们当候选。
3. 🔴 **「负向定义」不足以约束模型** —— 只写「其余各类一律不输出」**没用**：模型受「必须在允许值里选一个」的压力，会把非履约类**改标**成履约类（实跑 26年运维 **4/6 错**）。**有效组合 = ① 明示"默认 `[]`、允许为空"（卸掉输出压力）+ ② 形态准入闸门（看条款所在章节，可复现）+ ③ 禁止强行归类**。⇒ 与 §25 一致：**判据要落在「形态」而非「措辞」**。
4. 🔴 **示例值污染在 enum 字段上同样致命** —— `_EXAMPLES["guarantee"]` 写着 `"type": "履约保证金"`（**真会输出**的值），本身就是一股把答案拉向 `履约保证金` 的力。**凡示例字段的取值域与输出取值域重叠，示例就必须用 `null` 占位**（本次已改）。

---

## §27 第四轮补录：全量 prefill 审查的其余发现（2026-10-14）

**背景**：用户追问「**你只检查了保函相关的文档？所有 prefill 相关的问题是否也进行了审查和同步？**」—— 此前 §26 只覆盖 `guarantee.type` 一条线。遂对**全部 prefill 落点**（yaml / `_FIELDS` / `_EXAMPLES` / spec delta / 对外文档 / design / PRD / tests）做全量排查，发现**四类此前未纳入视野的失效源**（其中第 1 类是**比示例污染更隐蔽**的失效源）。

**定案**：

| 编号 | 定案 |
| --- | --- |
| **D27.1** | 🔴 **字段级规则空白 = 无规则**。此前 `service_content` / `service_sla` / `onsite_service_count` / `milestone_text` 四个字段在 prompt 里**只有「原文」二字**，无任何口径 → 输出全靠自由发挥。**SHALL 为每个字段写明字段级规则** |
| **D27.2** | `service_content` = **整段原文**（去掉 `【】` 等填空标记、不概括、不只写关键词）；`service_sla` = **SLA 相关约定原文**（写法不概括）；`onsite_service_count` = 🔴 **只取"次数"**（时长/时段/驻场方式 → `null`）；`milestone_text` = **完整照抄该阶段原文描述**（概括成「预付款」即为违规） |
| **D27.3** | 🔴 **示例去值化 SHALL 成体系做**，覆盖**三处**：① `_EXAMPLES`（全部业务值槽位 → `null`）② `_FIELDS` 内的合同原文摘录示例 ③ yaml 里的示例值。**不得只改被点名的那一处** |
| **D27.4** | `_EXAMPLES` 只保留两样东西：① `milestone_seq: 1`（结构必需）② evidence 的**结构形态**（3 条 / 按出处 / `{"section": null, "quote": "无"}` 哨兵）。其余全部 `null` / 占位符 |
| **D27.5** | 发现并修正一处**规则自相矛盾**：`_EXAMPLES["contract_plan"]` 的 `milestone_text: "合同签订及预付款"` 与 spec「SHALL 为该阶段的**原文描述**」**不同向**（示例是概括短语、规则要求完整原文）→ 示例改 `null`，spec 现有 Scenario 为新形态 |
| **D27.6** | **填空标记范围补齐**：yaml 原只写 `【】`，实际合同用的是**下划线**（`技术服务地点：甲方指定\____\_`、`接口方案\____\_`）→ SHALL 覆盖 `【】` / `_` / `___` |
| **D27.7** | ⚠️ **已知不一致（记待办、本轮未动）**：`evidence.quote` 可空性 —— `prefill_response_formats.py` 为 `_nullable_string`（模型侧可 `null`），`prefill_schemas.py` 为 `quote: str = ""`（非空）。**两侧不一致**，需后续统一。**本轮不擅自改动**（属契约面，需用户拍板） |
| **D27.7-a** | 🔴 **D27.7 的后果已实证（2026-10-14 证伪实验）**：`PrefillEvidence(quote=None)` → **ValidationError**；`_build_payload`（`prefill_service.py:38`）**无 try**，异常冒泡到 `run_prefill` 的 `except Exception`（L54-56）→ **整次预填降级 `prefill_status=failed` + 全字段空**（HTTP 仍 200）。即：**模型输出一个 schema 明确允许的 `null`，会打掉整次预填**。另：`quote` 的 `maxLength=300` **只在 JSON schema + prompt 层**，Pydantic 侧不设防（400 字照过）。|
| **D27.8** | ✅ **③ 长度上限 —— 用户拍板「不动」（2026-10-14）**：`payment_terms` / `service_content` / `service_sla` / `milestone_text` **均不加长度上限**。理由：口径要求这些字段取**整段 / 完整句原文**，设上限与"不得概括 / 不得截断"直接冲突。实测最长 = 26年运维 `service_content` **462 字**（已超 `quote` 的 300），此不对称**接受现状**，不改 schema。|
| **D27.9** | ✅ **④「硬错误图谱」—— 随中汇类挂起、撤出本次版本次待拍板（2026-10-14 修订）**。🔴 **用户 2026-10-14 重申**：中汇属**服务外包类**，「**那一类合同暂不处理，不在我们本次版本考虑范围**」（**该决定 2026-10-13 即已作出，见 §24 追加(2) ③ L871/L879**）。而该清单的 **4 条实证全部来自中汇**（① `contract_amount` 留千分位 `"34,008,000.00"`；② `milestone_name` 误判；③ `payment_amount` 返回非数字 `"实际结算金额"` 且不在其自报 evidence 内；④ `milestone_text` 缩写 `"按月结算"`——「按月结算」正是中汇特征）⇒ **整体随之挂起**。🔴 **记录一处流程失误**：我 2026-10-14 从**已挂起合同**的对比里提炼出「硬错误图谱」，还一度升格为**待拍板事项**并专门"纠正"其定性 —— **等于把已挂起的合同重新拉回范围，且未回查仓库里已有的挂起决定**。|

**改动清单**：

- [x] 27.1 `prefill_prompts.py::_FIELDS["contract_info"]` —— `service_content` / `service_sla` / `onsite_service_count` / `milestone_text` **补字段级规则**（D27.1 / D27.2）
- [x] 27.2 `prefill_prompts.py::_FIELDS` —— `inspection_count` 示例去值化（去掉 26年运维 L93 原文片段）；`contract_amount` 示例 `柒拾陆万叁仟贰佰元整/763200` → `壹万贰仟叁佰肆拾伍元整/12345`；`payment_method` 补反照抄护栏（「上面那些词只是形式示例、不是答案、不得照抄；原文写的是别的支付手段就返回那个」）
- [x] 27.3 ⭐ `prefill_prompts.py::_EXAMPLES` —— **全面去值化**（D27.3 / D27.4 / D27.5）：`启动/begin`、`合同签订及预付款`、`30%`、`2026年1月20日`、`第四条付款方式及条件`、`第五条合同计划`、`第三条合同金额`、`3,860,000.00`、`CNY`、`履约保证金`、`第八条履约保证金`、`按合同金额的8%收取` **全部清退**；保留 `milestone_seq: 1` + evidence 结构形态（含 `{"section": null, "quote": "无"}` 哨兵）
- [x] 27.4 `prompts/contract_review.yaml` —— ① 金额示例 `"50%保函"` → 「履约保证金为合同金额的 12.5%→12.5%」（去负向形态，同 26.8）；② **填空标记补下划线**（D27.6）+ 示例 `技术服务地点：甲方指定\____\_` + `763200`→`12345`；③ `inspection_count` 示例去值化；④ `payment_method` 补反照抄护栏
- [x] 27.5 本 change spec delta —— 新增「**字段级口径补齐（2026-10-14 第四轮 —— 4 个此前只有「原文」二字、无字段级规则的字段）**」段 + **4 个 Scenario**：「现场服务只有时长时不取值」「现场服务以频次给出时取原文」「服务内容以整段原文返回」「里程碑描述必须照抄完整原文」
- [x] 27.6 `docs/integration/2026-09-16-…md` —— 4 个字段行补足口径（`service_content` / `service_sla` / `onsite_service_count` / `milestone_text`）
- [x] 27.7 `docs/superpowers/specs/2026-09-15-…design.md` —— §4.1 表 4 行补足口径 + §4.2 `milestone_text` 行 + L211 示例 `"合同签订及预付款"` → `"合同签订后7个工作日内支付合同总额的30%"`（与 D27.5 同源）
- [x] 27.8 `docs/合同评审能力-PRD.md` L315 —— 补「`type` **实际只输出** `履约保函` / `履约保证金` **两种** … 5 值**仅作负向参考**」
- [x] 27.9 `tests/test_contract_review_prefill.py` —— **新增** `test_prefill_prompt_carries_round4_field_rules_and_devalued_examples`（4 字段规则断言 + `_EXAMPLES` 去值断言：`合同签订及预付款` / `3,860,000` / `2026年1月20日` / `"CNY"` / `第四条付款方式及条件` / `第八条履约保证金` 均**不得残留**；骨架 `"milestone_seq": 1` / `"quote": "无"` / `"milestone_text": null` **仍在**）；修 2 处断言（`每周1次系统运行情况检查` → `每周1次`；`"5*8小时现场驻场"` 改用未剥 `*` 的 `text` 断言）
- [x] 27.10 验证（见下）

**验证（2026-10-14）**：

- `pytest tests/test_contract_review_prefill.py -q` → **60 passed**
- `pytest tests/ --ignore=tests/two_stage -q` → **617 passed, 1 skipped**（红线①：`tests/two_stage/**` 未动）
- `openspec validate contract-review-mvp-prefill --strict` → **is valid**
- `tmp/check_yaml_sections.py` → 非 prefill 各段**逐行相同** ✅（红线②）
- 🔴 **实跑（示例去值化后，d02 ×3 合同）**：
  | 合同 | 关键字段实测 | 结果 |
  |---|---|---|
  | c1 | `milestone_text` 三行 | 均为**完整原文句** ✅（示例去值后未出现概括短语） |
  | 26年运维 | `inspection_count` = `每周1次系统运行情况检查；每月1次系统安全隐患及故障大排查。`；`service_sla` = 完整 SLA 句；`onsite_service_count` = `None` | ✅（**时长 → null** 正确） |
  | c4 | `onsite_service_count` = `每月 1 次`；`milestone_text` 均为完整原文句；`service_sla` = `一般故障 4 小时内响应、48 小时内修复；重大故障 1 小时内响应、8 小时内修复。` | ✅（**频次 → 取原文** 正确） |

**改动性质**：**prompt 层规则补齐 + 示例去值化** → **对外接口契约零变化**；服务端业务代码**零改动**。**不新增 change**（就地修订在途 delta）。

⚠️ **对外影响提示**：**无新增字段、无新增取值**。唯一行为变化 = 4 个字段**取值更贴合原文、更少被示例诱导**；`onsite_service_count` 在"只有时长"的合同上**更可能为 `null`**（此为**预期正确行为**，非缺陷）。下游**无需**兼容改动。

📌 **本轮教训**：
1. 🔴 **示例去值化必须成体系做** —— §26 只改了 `_EXAMPLES["guarantee"]` 一处，本轮全量排查才发现 `_EXAMPLES` **每个组**都有污染、`_FIELDS` 里也藏着合同原文摘录。**"改一处" = 系统性遗漏**；应对失效模式的修复，必须**按失效模式横扫全落点**，而非按被点名的那一处修。
2. 🔴 **字段级规则空白是比示例污染更隐蔽的失效源** —— 示例污染至少会留下"照抄痕迹"（可被实测抓到）；字段**没有规则**时，输出看似合理、实则每次自由发挥，**没有任何"异常信号"**。⇒ **接入新字段时，第一件事是检查它在 prompt 里是否真的有一条规则**（而非只有「原文」二字）。
3. **规则与示例必须同向** —— `_EXAMPLES` 的 `milestone_text: "合同签订及预付款"` 与 spec「SHALL 为原文描述」**互相打脸**：规则说"照抄整句"、示例给"概括短语"。**示例是模型实际会模仿的东西**，与规则不同向的示例 = 隐性反规则。
4. **全量审查 ≠ 单线审查** —— 用户这一问直接暴露了上一轮的范围偏差：**只沿着"用户刚提到的那个问题"排查**，会系统性漏掉同类问题在其他字段上的复现。**失效模式的排查范围应按"模式"划定，不按"话题"划定。**

---

## §28 第五轮：`evidence.quote` 可空性 —— 方案 A 落地（2026-10-14，用户拍板「执行」）

**背景**：D27.7 记录的「两侧不一致」经 2026-10-14 新窗口实证后定性升级为「**合法输入即致命**」——JSON schema（`prefill_response_formats.py:21` `_nullable_string(max_length=300)`）与对外接口文档（integration L367「string 或 null」）**都声明 `quote` 可空**，但 Pydantic（`prefill_schemas.py:46` `quote: str = ""`）**非空** ⇒ 模型合法输出 `null` → `_build_payload`（L38，无 try）抛 ValidationError → 被 `run_prefill` 的 `except Exception`（L54-56）吞掉 → **整次预填静默降级 `prefill_status=failed` + 26 字段全空**（HTTP 仍 200）。

**定案**：

| 编号 | 定案 |
| --- | --- |
| **D28.1** | 采纳**方案 A**：`PrefillEvidence.quote` 改 `str \| None = None`，实现对齐**已对外声明**的契约；**对外接口契约零变更**，JSON schema / prompt 均不动 |
| **D28.2** | 🔴 不一致实为**三处**（新窗口回查，上一窗口版图只画了两处）：spec delta `spec.md:531` 与 design `design.md:274` **亦声明非空**（`"quote": string`），且 design L572 自认 `string | null`（内部矛盾）⇒ 两处同步改为 `string | null`，矛盾消除 |
| **D28.3** | 🔴 integration 消费方判定表（L388-394）**不覆盖 null**，`"无".equals(quote.trim())` 指引遇 null 会 NPE ⇒ 补 `quote: null` 判定行 + 判空指引改 null-safe。**单改 Pydantic = 把服务端的炸换成下游 NPE**，故 A 必须打包同步 |
| **D28.4** | 取 `= None` **不取** `= ""`：与 `section` 及全 schema 家族一致，且合 design §4.5「缺失表达一律 null、不用空字符串占位」；`""` 是无意义意外值 |
| **D28.5** | Pydantic 侧**不加** `maxLength=300`：超长 quote 应从「文档违规但送达」，不应变成第二次「整单死刑」（与 A 的目的相反） |
| **D28.6** | prompt **不加**「不得写 null」：已教固定写「无」（`prefill_prompts.py:163-166`）、实跑 0 触发，Pydantic 为兜底层（YAGNI） |
| **D28.7** | 副作用实证（上一窗口唯一未验证点）：A 后线上 JSON = `{"section": "第四条 付款方式及条件", "quote": null}`（fastapi jsonable_encoder 实测）；`evidence` 内 null 字段**本就常态**（`{"section": null, "quote": "无"}` 每份响应出现）⇒ 不引入新形状；边缘变化 = 非 strict 后端缺省键 `''` → `null`（strict 下不可达：`_object` 全键 required） |

**改动清单**：

- [x] 28.1 `prefill_schemas.py` —— `quote: str | None = None` + docstring 补 null 语义（与「无」不同义）
- [x] 28.2 本 change spec delta —— L531 元素结构 `"quote": string | null`
- [x] 28.3 `docs/superpowers/specs/2026-09-15-…design.md` —— L274 同改（消 L572 矛盾）
- [x] 28.4 `docs/integration/2026-09-16-…prefill-api-integration.md` —— 判定表补 `quote: null` 行 + 全等判定指引改 null-safe
- [x] 28.5 `tests/test_contract_review_prefill.py` —— 新增 `test_prefill_evidence_quote_accepts_null_and_serializes_as_null`（validate + `_build_payload` 端到端 + jsonable_encoder 线上形态三断言）
- [x] 28.6 验证（见下）

**验证（2026-10-14）**：

- 🔴 证伪实验 `tmp/exp_quote_nullability.py`：**改前** `PrefillEvidence(quote=None)` / `PrefillPayload.model_validate` 均 ValidationError；`run_prefill` 端到端 → `prefill_status='failed'` + 26 字段全空（对照 `"无"` → ok，触发点确认为 null）
- 🔴 **改后**复跑同实验（仓库原码）：null → `prefill_status='ok'`、1 行保留、线上 `{"section": "第四条 付款方式及条件", "quote": null}`
- `pytest tests/test_contract_review_prefill.py -q` → **61 passed**（60 + 新增 1）
- `pytest tests/ --ignore=tests/two_stage -q` → **618 passed, 1 skipped**
- `openspec validate contract-review-mvp-prefill --strict` → **is valid**

**改动性质**：**服务端校验放宽（对齐已声明契约）** —— 不新增字段 / 不改名 / 不改 JSON schema / 不改 prompt / 不碰 `two_stage/**` / 不碰 review 链；**对外接口契约零变更**。**不新增 change**（就地修订在途 delta）。

⚠️ **对外影响提示**：`quote` 为 `null` 时下游按「无片段」处理（留空、不标红）——已在接口文档判定表明示；`evidence` 内 null 字段本就常态，不引入新形状。下游**无需**兼容改动（判定指引已同步）。

📌 **本轮教训**：
1. 🔴 **「未验证点」必须闭环再答** —— 上一窗口对 A 的副作用只做推断（「下游无需改动」），新窗口用 jsonable_encoder 实测线上形态 + 回查文档判定表，才发现**判定指引不覆盖 null**：不补这句，A 就是把服务端的炸换成下游的 NPE。**推断可以当时说，但不能带着它收官。**
2. 🔴 **不一致的版图要按「落点类型」扫全** —— 上一窗口只对照了「JSON schema vs Pydantic」，漏了 spec delta 与 design 文档也声明非空（实为三处）。凡「契约不一致」，落点 = 代码 + schema + 内部 spec/design + 对外文档 + 测试，五类都要过一遍。
