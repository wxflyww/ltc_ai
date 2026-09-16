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
- [x] 2.7 预填 prompt / schema 按 `prefill_scope` 分三套：`d02`（`contract_info` + `contract_plan`）、`d03`（`finance_info` + `guarantee`）各一套，`all` 由两者拼装生成（不重复维护字段定义） → `test_scope_groups_match_with_design`、`test_schema_scope_only_exposes_requested_groups`

## 3. 抽取本体（D1：最大不确定性）

- [x] 3.1 在 `tmp/samples/c1.md`、`c2.md` 上跑通 `contract_info` 9 个字段，记录命中情况 → c1 命中 4/9、c2 命中更多；未命中项经核为**合同确实未写**（服务起止时间 / 现场服务次数 / 巡检次数），非抽取缺失
- [x] 3.2 跑通 `contract_plan` 数组：里程碑 13 标准名语义归一、`milestone_seq` 原文顺序、按 `milestone_seq` 升序返回 → `test_run_prefill_sorts_plan_by_milestone_seq`（断言排序结果为 `[1, 3]`）
- [x] 3.3 跑通 `finance_info` 2 个字段与 `guarantee` 多笔记录 → 真实样例 6/6 `ok`；c1 履约保证金 524,625（对得上"合同金额 5%"），c2 为固定额 130,000（原文即固定额，非比例）
- [ ] 3.4 跑通 `evidence` 为 `{section, quote}[]`：按出处各列一条、去重、`section` 取顶层条款标题原文、`quote` ≤ 60 字 → **部分完成**：结构与两键已由 `test_evidence_is_object_array_with_section_and_quote` 锁定，真实样例中 `section` / `quote` 均已产出；但「去重」「`quote` ≤ 60 字」**未写自动化断言**（仅靠 prompt 约束 + 人工抽查）
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

- [x] 6.1 不新增独立接口，不改 `upload-md` 入口
- [x] 6.2 不实现 `review` / `prefill` 之外的任何 `mode` 取值（非法取值由 `Literal` 校验 → 422）
- [x] 6.3 不动 `app/capabilities/contract_review/two_stage/**`（本 change 零改动；其中 `prepare_model.py` 的唯一改动属依赖 change `llm-disable-thinking`） → 提交时精确白名单，`two_stage/**` 零新增条目
- [x] 6.4 不解析附件，不做附件与正文关联 → `test_prefill_ignores_attachments`
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
- **3.4 的自动化缺口**：`evidence` 的「去重」「`quote` ≤ 60 字」目前仅靠 prompt 约束，若联调中发现质量问题，建议补断言而非继续放宽 prompt。
- **5.2** 待用户补足样例合同后复测。
