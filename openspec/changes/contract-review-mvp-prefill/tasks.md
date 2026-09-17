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
