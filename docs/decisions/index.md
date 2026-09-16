# LTC AI 项目决策台账

> 状态：Active
>
> 建立日期：2026-08-26
>
> 作用：保存持久决策的身份、作用域、权威证据、取代关系和传播状态，防止跨窗口、跨文档、跨阶段或跨代理协作时发生遗漏和静默覆盖。
>
> 权威边界：本台账不复制或替代正式 OpenSpec、Schema、业务设计和项目约束。详细业务规则仍以其声明的权威来源为准；本台账负责说明“当前哪项决定有效、适用于哪里、是否取代旧决定、应传播到哪些工件”。

## 1. 台账边界与作用域

- 默认一套台账覆盖当前 Git 仓库。
- 子产品、能力、模块、阶段和 OpenSpec change 使用决策记录的 `scope` 区分，不因目录不同自动创建独立台账。
- 只有子项目具备独立负责人、决策权威、版本体系、发布生命周期和权威文档时，才允许建立子台账；子台账必须由本索引回链。
- 当前合同评审 `prepare`、`evaluate` 和合同系统协作属于同一工程内的不同作用域，不建立互不关联的平级台账。

支持的作用域形式：

- `project`
- `capability:<name>`
- `module:<path>`
- `change:<name>`
- `release:<id>`

## 2. 权威来源登记

| 作用域 | 权威来源 | 职责 | 状态 |
|---|---|---|---|
| `project` | `AGENTS.md` | 仓库级工程约束和操作边界 | Active |
| `module:contract-review/two-stage` | `app/capabilities/contract_review/two_stage/AGENTS.md` | 两阶段模块的权威路由、架构不变量、工作门禁和专用验收边界 | Active |
| `module:contract-review/two-stage` | `docs/superpowers/specs/2026-07-28-contract-review-two-stage-upgrade-draft.md` | 两阶段整体架构与已确认业务边界 | Active |
| `module:contract-review/two-stage` | `docs/superpowers/specs/2026-08-03-contract-review-two-stage-field-glossary.md` | 术语解释；不单独定义接口契约 | Active |
| `module:contract-review/two-stage` | `docs/integration/2026-07-28-contract-system-two-stage-review-communication-draft.md` | 合同系统沟通摘要；不作为字段定义来源 | Active |
| `module:contract-review/two-stage` | `docs/superpowers/baselines/2026-07-31-contract-review-legacy-baseline.md` | 旧流程实际行为、已知问题和回归基线 | Active |
| `change:contract-review-prepare-api` | `openspec/changes/contract-review-prepare-api/` | Prepare 字段、行为、设计和实施任务的当前正式变更权威 | Active，代码待实现 |
| `module:contract-review/two-stage` | `docs/superpowers/specs/2026-08-15-contract-review-mvp-two-stage-sync-ledger.md` | MVP 问题到两阶段事实与裁决边界的动态同步记录 | Active |

## 3. 决策登记表

| 决策 ID | 标题 | 作用域 | 状态 | 取代 | 传播状态 |
|---|---|---|---|---|---|
| `DEC-LTC-20260826-001` | 仓库级台账与作用域颗粒度 | `project` | `active` | — | `synchronized` |
| `DEC-LTC-20260826-002` | 台账自动发现与创建授权边界 | `project` | `active` | — | `synchronized` |
| `DEC-LTC-20260826-003` | 决策完整性门禁触发方式 | `project` | `active` | — | `synchronized` |
| `DEC-LTC-20260826-004` | 合同评审两阶段现有决定的基线接管 | `module:contract-review/two-stage` | `active` | — | `synchronized` |
| `DEC-LTC-20260827-001` | 两阶段模块 AGENTS 职责边界 | `module:contract-review/two-stage` | `active` | — | `synchronized` |
| `DEC-LTC-20260829-001` | 合同评审两阶段交付控制与审计沉淀机制 | `module:contract-review/two-stage` | `superseded` | `DEC-LTC-20260831-002` | `synchronized` |
| `DEC-LTC-20260831-001` | 交付控制事件 ID 使用完整限定格式 | `module:contract-review/two-stage` | `superseded` | `DEC-LTC-20260831-002` | `synchronized` |
| `DEC-LTC-20260831-002` | 会话交接复用通用 handoff 并停止项目专用状态机制 | `module:contract-review/two-stage` | `superseded` | `DEC-LTC-20260831-003` | `synchronized` |
| `DEC-LTC-20260831-003` | 会话交接改用独立 session-handoff 增强 Skill | `module:contract-review/two-stage` | `active` | `DEC-LTC-20260831-002` | `synchronized` |
| `DEC-LTC-20260901-001` | 两阶段实施改为用户手动创建 Codex 角色窗口 | `module:contract-review/two-stage` | `active` | — | `synchronized` |
| `DEC-LTC-20260907-001` | Prepare 后续采用有界人工协作与有效证据复用 | `change:contract-review-prepare-api` | `superseded` | `DEC-LTC-20260910-001` | `synchronized` |
| `DEC-LTC-20260908-001` | Prepare 跨层契约簇闭合与两轮熔断 | `change:contract-review-prepare-api` | `active` | — | `synchronized` |
| `DEC-LTC-20260909-001` | 签章事实采用保守装配与业务歧义人工确认 | `change:contract-review-prepare-api` | `active` | — | `pending` |
| `DEC-LTC-20260910-001` | Prepare 固定三窗口协作与增量读取 | `change:contract-review-prepare-api` | `superseded` | `DEC-LTC-20260913-002` | `synchronized` |
| `DEC-LTC-20260910-002` | Prepare 实现窗口使用 DeepSeek V4.1 Flash | `change:contract-review-prepare-api` | `active` | — | `synchronized` |
| `DEC-LTC-20260910-003` | Task 7 商业事实内部候选与装配入口 | `change:contract-review-prepare-api` | `active` | — | `synchronized` |
| `DEC-LTC-20260911-001` | Task 7 附件模型上下文与无定位来源缺口键 | `change:contract-review-prepare-api` | `active` | — | `synchronized` |
| `DEC-LTC-20260911-002` | Task 8 标准附件扫描的边界证明责任 | `change:contract-review-prepare-api` | `active` | — | `synchronized` |
| `DEC-LTC-20260911-003` | Task 8 标准附件正文结构交叉印证的保守判据 | `change:contract-review-prepare-api` | `active` | — | `synchronized` |
| `DEC-LTC-20260911-004` | Task 8 扫描计划与 Task 9 服务编排的唯一责任边界 | `change:contract-review-prepare-api` | `active` | — | `synchronized` |
| `DEC-LTC-20260911-005` | Task 9 Prepare 流程的语义顺序与运行时观测边界 | `change:contract-review-prepare-api` | `active` | — | `synchronized` |
| `DEC-LTC-20260912-001` | Prepare 三窗口的低消耗证据复用与交接回执 | `change:contract-review-prepare-api` | `superseded` | `DEC-LTC-20260913-002` | `synchronized` |
| `DEC-LTC-20260913-001` | Prepare 契约簇熔断状态与不可达 RED 断言护栏 | `change:contract-review-prepare-api` | `active` | — | `synchronized` |
| `DEC-LTC-20260913-002` | Prepare 日常双窗口与按门禁临时复核 | `change:contract-review-prepare-api` | `active` | `DEC-LTC-20260910-001`, `DEC-LTC-20260912-001` | `synchronized` |
| `DEC-LTC-20260913-003` | Prepare 上下文与 token 卫生的可复用操作规则 | `change:contract-review-prepare-api` | `active` | — | `synchronized` |
| `DEC-LTC-20260914-001` | Prepare 风险分级纵向切片与 Gate 式独立审计 | `change:contract-review-prepare-api` | `active` | — | `synchronized` |
| `DEC-LTC-20260915-001` | Prepare 风险驱动测试取证与特征化测试边界 | `change:contract-review-prepare-api` | `active` | — | `synchronized` |
| `DEC-LTC-20260915-002` | Prepare SITE 探针必须命中真实调用边界 | `change:contract-review-prepare-api` | `active` | — | `synchronized` |
| `DEC-LTC-20260915-003` | Prepare Task Card 定点读取与主控派发前硬门槛 | `change:contract-review-prepare-api` | `active` | — | `synchronized` |
| `DEC-LTC-20260915-004` | Prepare 通用 Retry Gate | `change:contract-review-prepare-api` | `active` | — | `synchronized` |
| `DEC-LTC-20260916-001` | Prepare 测试有效性与 PowerShell 执行通道切换 | `change:contract-review-prepare-api` | `active` | — | `synchronized` |

## 4. 决策记录

### `DEC-LTC-20260826-001` — 仓库级台账与作用域颗粒度

- 状态：`active`
- 作用域：`project`
- 决定日期：2026-08-26
- 确认人：用户明确确认
- 决定：当前仓库使用一套项目决策台账；模块、阶段和 change 通过决策级 `scope` 隔离。只有具备独立决策权威和生命周期的子项目才建立子台账，并必须回链本索引。
- 权威证据：
  - 2026-08-26 关于 `decision-integrity-gate` 台账颗粒度的用户确认
- 取代：无
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
- 备注：该规则避免 `prepare`、`evaluate` 或单一模块形成需要人工同步的平级事实源。

### `DEC-LTC-20260826-002` — 台账自动发现与创建授权边界

- 状态：`active`
- 作用域：`project`
- 决定日期：2026-08-26
- 确认人：用户明确确认
- 决定：决策门禁自动识别是否缺少项目台账；遇到首个会产生或改变持久决定的任务且台账不存在时，必须主动进入 `LEDGER_REQUIRED` 并提出创建建议，使用户无需记住创建时机。实际创建或写入仍需用户明确授权，不得静默新增治理文件。
- 权威证据：
  - 2026-08-26 关于 Skill 是否负责台账创建的用户确认
- 取代：无
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
- 备注：简单解释、翻译、格式调整和不改变公共行为的局部实现细节不触发建账门禁。

### `DEC-LTC-20260826-003` — 决策完整性门禁触发方式

- 状态：`active`
- 作用域：`project`
- 决定日期：2026-08-26
- 确认人：用户明确确认
- 决定：`decision-integrity-gate` 默认允许自动识别调用；确认或取代业务决定、传播到权威文档、OpenSpec、计划、实现交接、提交或归档前均属于触发点。显式 `$decision-integrity-gate` 口令仅作为人工兜底，不要求用户每次主动记忆和调用。
- 权威证据：
  - 2026-08-26 关于 Skill 强制运行方式的用户确认
- 取代：无
- 受影响工件：
  - `app/capabilities/contract_review/two_stage/AGENTS.md` — `synchronized`
  - `docs/decisions/index.md` — `synchronized`
- 备注：本阶段不包含 Git Hook、确定性检查脚本、CI 任务或分支保护。

### `DEC-LTC-20260826-004` — 合同评审两阶段现有决定的基线接管

- 状态：`active`
- 作用域：`module:contract-review/two-stage`
- 决定日期：2026-08-26
- 确认人：用户授权保护并收口当前设计成果
- 决定：第 2 节登记的两阶段权威来源共同构成建账时的现有决定基线。建账不复制全部历史结论，也不改变原权威顺序；以后某项既有结论被修改、澄清、实现交接或取代时，必须先为该结论补建独立决策记录，并显式维护取代与传播关系。
- 权威证据：
  - `app/capabilities/contract_review/two_stage/AGENTS.md`
  - `docs/superpowers/specs/2026-07-28-contract-review-two-stage-upgrade-draft.md`
  - `docs/superpowers/specs/2026-08-03-contract-review-two-stage-field-glossary.md`
  - `docs/integration/2026-07-28-contract-system-two-stage-review-communication-draft.md`
  - `openspec/changes/contract-review-prepare-api/`
- 取代：无
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
- 备注：对话记忆和模型记忆只能帮助发现历史线索，不能单独取代仓库内权威证据。

### `DEC-LTC-20260827-001` — 两阶段模块 AGENTS 职责边界

- 状态：`active`
- 作用域：`module:contract-review/two-stage`
- 决定日期：2026-08-27
- 确认人：用户明确确认
- 决定：`app/capabilities/contract_review/two_stage/AGENTS.md` 使用生命周期中性的模块约束定位，只承载权威路由、架构不变量、Agent 工作与决策门禁以及两阶段特有验收边界；业务枚举、字段和 API 细节、具体判断条件、确定性算法及阶段进度只保存在各自唯一权威文档中。项目约束不得仅依赖个人 Skill；Skill 不可用时仍必须执行工具无关的最低决策完整性检查。
- 权威证据：
  - 2026-08-27 关于两阶段 `AGENTS.md` 长期职责边界的用户明确确认
- 取代：无
- 受影响工件：
  - `app/capabilities/contract_review/two_stage/AGENTS.md` — `synchronized`
  - `docs/decisions/index.md` — `synchronized`
- 备注：本决定不改变任何 Prepare、Evaluate 或合同系统业务规则，也不授权修改个人 `decision-integrity-gate` Skill；业务细节从约束文件移除前必须确认其已有有效权威落点。

### `DEC-LTC-20260829-001` — 合同评审两阶段交付控制与审计沉淀机制

- 状态：`superseded`
- 作用域：`module:contract-review/two-stage`
- 决定日期：2026-08-29
- 确认人：用户明确确认
- 决定：Prepare、Evaluate 和 Pilot 共用一套仓库内交付控制机制；`current-state.yaml` 是唯一当前状态源，ledger 保存追加历史，修复复审、批次验收和 change 最终审计分级执行；审计仪表盘由专业工具生成并经用户批准的固定模板与确定性数据适配器共同产生，日常刷新不调用模型或专业页面工具，不修改 Prepare、Evaluate 或 Pilot 业务契约。
- 权威证据：
  - 2026-08-29 用户对完整设计及“专业工具生成视觉模板＋最小确定性数据适配器”实现边界的明确确认
  - 2026-08-31 用户确认停止项目专用方案，并将复盘、经验沉淀和仪表盘内容剥离为项目外接续底稿
- 取代：已由 `DEC-LTC-20260831-002` 取代
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `docs/superpowers/specs/2026-08-29-contract-review-two-stage-delivery-control-design.md` — `not_applicable`
  - `docs/superpowers/plans/2026-08-29-contract-review-two-stage-delivery-control.md` — `not_applicable`
  - `app/capabilities/contract_review/two_stage/AGENTS.md` — `not_applicable`
  - `docs/superpowers/execution/contract-review-two-stage/` — `not_applicable`
  - `.agents/skills/ltc-two-stage-delivery-control/` — `not_applicable`
  - `tests/delivery_control/` — `not_applicable`
- 备注：本决定只建立工程交付治理、证据沉淀和只读展示机制；OpenSpec、Schema、业务规则、Prepare/Evaluate 阶段职责和真实端点验收边界保持不变。项目专用实施已于 2026-08-31 停止；复盘、经验沉淀与仪表盘想法仅保留为后续通用能力剥离参考。

### `DEC-LTC-20260831-001` — 交付控制事件 ID 使用完整限定格式

- 状态：`superseded`
- 作用域：`module:contract-review/two-stage`
- 决定日期：2026-08-31
- 确认人：用户明确确认
- 决定：交付控制事件的正式稳定 ID 必须包含完整所属坐标。finding-owned 事件使用 `<finding_id>-(FIX|AUDIT|VALIDATION|REOPEN|EVIDENCE-STALE)-[0-9]{2,}`，scope 事件使用 `CR2S-<change>-<batch>-<repair_scope>-(RECONCILE|GATE)-[0-9]{2,}`；`FIX-01`、`AUDIT-01` 等短格式只能作为事件类型与序号后缀，不得独立作为正式稳定 ID。修复和复审仍是事件，不占用新的 repair scope。
- 权威证据：
  - 2026-08-31 用户关于事件 ID 完整限定格式的明确确认
- 取代：已由 `DEC-LTC-20260831-002` 取代；本澄清不再作为本项目实施要求
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `docs/superpowers/specs/2026-08-29-contract-review-two-stage-delivery-control-design.md` — `not_applicable`
  - `docs/superpowers/execution/contract-review-two-stage/README.md` — `not_applicable`
  - `docs/superpowers/plans/2026-08-29-contract-review-two-stage-delivery-control.md` — `not_applicable`
  - `.agents/skills/ltc-two-stage-delivery-control/scripts/validate_state.py` — `not_applicable`
  - `tests/delivery_control/` — `not_applicable`
- 备注：本记录只澄清交付控制技术标识格式，不修改 finding、evidence、lesson 的既有格式，不修改交付控制整体机制，也不授权进入 Task 4。

### `DEC-LTC-20260831-002` — 会话交接复用通用 handoff 并停止项目专用状态机制

- 状态：`superseded`
- 作用域：`module:contract-review/two-stage`
- 决定日期：2026-08-31
- 确认人：用户明确确认
- 决定：跨 Codex、Copilot 或其他新会话的上下文搬运改用通用 `handoff` Skill；handoff 摘要不作为业务权威或当前事实源，新会话必须重新读取仓库权威并现场核对 branch、HEAD、tracked/untracked 状态和受保护修改。停止在本项目实施 `current-state.yaml`、revision、稳定事件 ID、项目专用校验器及 `ltc-two-stage-delivery-control` Skill。复盘、经验沉淀和仪表盘想法已从本项目剥离至项目外接续底稿；是否建设通用 Skill 留待未来另行讨论。
- 权威证据：
  - 2026-08-31 用户对“通用 handoff + 模块 AGENTS 极薄现场核对规则”方案的明确确认
- 取代：
  - `DEC-LTC-20260829-001`
  - `DEC-LTC-20260831-001`
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `app/capabilities/contract_review/two_stage/AGENTS.md` — `synchronized`
  - `.agents/skills/ltc-two-stage-delivery-control/` — `not_applicable`
  - `tests/delivery_control/` — `not_applicable`
  - `docs/superpowers/execution/contract-review-two-stage/` — `not_applicable`
  - `docs/superpowers/specs/2026-08-29-contract-review-two-stage-delivery-control-design.md` — `not_applicable`
  - `docs/superpowers/plans/2026-08-29-contract-review-two-stage-delivery-control.md` — `not_applicable`
- 备注：本决定不修改 Prepare、Evaluate 或 Pilot 业务契约。原设计和计划中的复盘、经验沉淀及仪表盘内容已剥离至项目外个人底稿 `C:\Users\Cold_\Documents\Codex\skill-ideas\retrospective-lessons-dashboard\README.md`；该底稿不是当前 Skill、项目权威或实施计划。

### `DEC-LTC-20260831-003` — 会话交接改用独立 session-handoff 增强 Skill

- 状态：`active`
- 作用域：`module:contract-review/two-stage`
- 决定日期：2026-08-31
- 确认人：用户明确确认
- 决定：保留上游 `handoff` 不动，跨 Codex、Copilot 或其他新会话的上下文搬运改用独立个人通用 `session-handoff` Skill。该 Skill 继承临时目录输出、引用既有权威、敏感信息脱敏和按下一会话目标裁剪，并增加现场 Git 核对、权威重读、单一下一动作、受保护修改、验证分层、停止条件和过期交接处理。交接摘要仍不是业务权威或完成证据；本项目不恢复 `current-state.yaml`、revision、稳定事件 ID、项目专用校验器、复盘或仪表盘实现。
- 权威证据：
  - 2026-08-31 用户明确确认“基于上游 handoff 新建独立 session-handoff Skill”方案
- 取代：
  - `DEC-LTC-20260831-002`
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `app/capabilities/contract_review/two_stage/AGENTS.md` — `synchronized`
  - `.agents/skills/ltc-two-stage-delivery-control/` — `not_applicable`
  - `tests/delivery_control/` — `not_applicable`
  - `docs/superpowers/execution/contract-review-two-stage/` — `not_applicable`
- 备注：个人 Skill 安装于 `C:\Users\Cold_\.codex\skills\session-handoff\`，不作为 LTC 仓库权威，也不修改 Prepare、Evaluate 或 Pilot 业务契约。原版 `handoff` 保留为上游参考；由于其 frontmatter 不通过当前 Codex Skill 结构校验，不作为本项目的可用备用入口。

### `DEC-LTC-20260901-001` — 两阶段实施改为用户手动创建 Codex 角色窗口

- 状态：`active`
- 作用域：`module:contract-review/two-stage`
- 决定日期：2026-09-01
- 确认人：用户明确确认
- 决定：两阶段后续主控制、实现和独立复核均在 Codex 窗口内执行，所有窗口由用户手动创建并自行选择模型；主控制窗口不得自动创建、fork 或切换窗口。每个 Task 开始前，主控制窗口必须主动提供可直接粘贴的单任务指令；同一实现窗口继续下一 Task 时只更新任务指令，新开、替换、切换窗口角色或上下文不可靠时才使用 `session-handoff` 生成临时交接文件。所有窗口继续遵守单写入者、受保护修改、阶段门禁、停止条件和自动化/真实端点证据分层。
- 权威证据：
  - 2026-09-01 用户明确要求窗口由其手动创建并自行切换模型、协作约定同步修改、主窗口重新建立，以及澄清 `session-handoff` 触发和任务指令责任
- 取代：无；本决定将 `app/capabilities/contract_review/AGENTS.md` 中未登记为独立决策的 VS Code Copilot 实现方式替换为 Codex 角色窗口，不取代 `DEC-LTC-20260827-001` 的 AGENTS 职责边界或 `DEC-LTC-20260831-003` 的 handoff 机制
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `app/capabilities/contract_review/AGENTS.md` — `synchronized`
  - `app/capabilities/contract_review/two_stage/AGENTS.md` — `synchronized`
  - `C:\Users\Cold_\.codex\skills\session-handoff\` — `not_applicable`
  - `openspec/changes/contract-review-prepare-api/` — `not_applicable`
  - `docs/superpowers/plans/2026-08-25-contract-review-prepare-api.md` — `not_applicable`
- 备注：本决定只改变协作载体、窗口创建权和任务交接责任，不修改 Prepare、Evaluate、Pilot 或合同系统业务契约，也不授权自动创建窗口、提交、推送或归档。

### `DEC-LTC-20260907-001` — Prepare 后续采用有界人工协作与有效证据复用

- 状态：`superseded`
- 作用域：`change:contract-review-prepare-api`
- 决定日期：2026-09-07
- 确认人：用户明确确认“还是不要轻易启动子agent了。就按你的建议往下执行”，并要求整理供后续遵循的步骤和用户介入时点
- 决定：Prepare 后续采用主控制与实现两个常驻人工窗口，在依赖边界、公共语义变化及阶段门禁进行独立复核；变化检测使用确定性命令，不默认启动子 Agent。新窗口完整读取权威并现场核对，同一窗口复用未失效的权威理解与验证证据，按变化和 Task 关键语义定点重读、补验。单任务护栏只作为权威与验证的临时索引；独立审计已覆盖一致性要求时不重复审计。保持单写入者、Task 完成即停、受保护修改、真实端点证据分层和原有操作授权边界。具体步骤与用户介入时点统一在执行指南维护。
- 权威证据：
  - 2026-09-07 本决策窗口内用户对节省时间/token、防漂移、满足验收和不默认子 Agent 方案的明确采纳
  - 用户要求 Astra 仅用于极特殊情况；公司三个 Qwen 模型免费、速度较慢且工具链可用由用户说明，本轮未执行端点实测
- 取代：已由 `DEC-LTC-20260910-001` 取代；后者继承本记录的人工协作、有效证据复用、单写入者、停止边界和不默认子 Agent 约束，并将窗口拓扑澄清为固定三窗口
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `docs/superpowers/playbooks/2026-09-07-prepare-execution-guide.md` — `synchronized`
  - `app/capabilities/contract_review/two_stage/AGENTS.md` — `synchronized`
  - `docs/superpowers/plans/2026-08-25-contract-review-prepare-api.md` — `synchronized`
  - `app/capabilities/contract_review/AGENTS.md` — `not_applicable`，既有角色、读取及单任务约束继续适用
  - Prepare OpenSpec 业务契约、任务勾选、代码、测试、生产配置与个人/全局 Skill — `not_applicable`
- 备注：模型分工是指南内可调整的起始建议，不登记为性能已验证的业务规则。Astra 仅在用户明确同意的极特殊问题中使用；本次不授权 Task 5 修复、Task 6、模型通道配置或 commit/push/archive。

### `DEC-LTC-20260908-001` — Prepare 跨层契约簇闭合与两轮熔断

- 状态：`active`
- 作用域：`change:contract-review-prepare-api`
- 决定日期：2026-09-08
- 确认人：用户明确确认将 Task 5 的多轮复核复盘结论写入执行流程，并在同步后继续推进
- 决定：同一事实域中相互依赖的 Prompt、候选 Schema、装配、证据/coverage、稳定键和测试构成一个“跨层契约簇”。任务启动或首次发现跨层阻断时，主控制先建立“正式要求 → 各层实现位置 → 测试证据”的闭合矩阵；实现者与独立 reviewer 使用同一矩阵。若同一契约簇连续两轮修复后仍出现新的 P1/P2 阻断，即使单个失败用例已关闭，也必须冻结写入，先归因规则、实现、测试矩阵或环境，再补齐该簇 RED 用例并重新派发有界修复。通过数增长不单独构成有效闭合。
- 权威证据：
  - 2026-09-08 用户对 Task 5 七轮复核的复盘及对上述流程优化的明确确认
  - `docs/superpowers/playbooks/2026-09-07-prepare-execution-guide.md` 的单任务、独立复核和两轮停止边界
- 取代：无；补充 `DEC-LTC-20260907-001`，不改变 Prepare/Evaluate 业务契约、模型配置、提交或归档授权
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `docs/superpowers/playbooks/2026-09-07-prepare-execution-guide.md` — `synchronized`
  - `app/capabilities/contract_review/two_stage/AGENTS.md` — `not_applicable`，继续通过执行指南引用该流程
  - Prepare OpenSpec、实施计划、代码、测试、生产配置与个人/全局 Skill — `not_applicable`
- 备注：本决定以“契约簇”扩大既有两轮熔断的判断单位，不要求增加常设 reviewer 或重复已有效的独立审计。

### `DEC-LTC-20260909-001` — 签章事实采用保守装配与业务歧义人工确认

- 状态：`active`
- 作用域：`change:contract-review-prepare-api`
- 决定日期：2026-09-09
- 确认人：用户明确确认“关系出现不可唯一确定的歧义时停止自动装配、交由人工判断”的签章契约方向
- 决定：签章事实仅在证据可定位且关系唯一时自动装配。事实值可定位但主体、用途或归属证据不足时，保留该值并使用 `UNBOUND` 或 `UNCERTAIN`，不得猜测。存在多个合理签署栏位、人员归属、替代关系或主体/用途关系解释时，Prepare SHALL 抛出 `NeedsConfirmationError` 并不返回残缺 `ReviewContext`；不得通过新增模型内部标签或位置/顺序推断强行自动消解。模型候选的无效、跨文档或跨块引用，以及证据/引用不闭合，仍是 `ModelFormatError` 或既有技术失败，而非人工确认。`PARTIAL/UNAVAILABLE` 只表示可定位来源缺口；可靠扫描后无签章为 `COMPLETE`。
- 权威证据：
  - 2026-09-09 用户对“两个甲方”等无法唯一解释签章结构必须人工判断的明确确认
  - `openspec/changes/contract-review-prepare-api/specs/contract-review/spec.md` 的事实证据、覆盖和技术失败边界
- 取代：无；补充 `DEC-LTC-20260908-001`，不授权 Task 6 继续修复、Task 7、提交、推送或归档
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `openspec/changes/contract-review-prepare-api/design.md` — `synchronized`
  - `openspec/changes/contract-review-prepare-api/specs/contract-review/spec.md` — `synchronized`
  - `openspec/changes/contract-review-prepare-api/tasks.md` — `synchronized`
  - `docs/superpowers/plans/2026-08-25-contract-review-prepare-api.md` — `synchronized`
  - `app/capabilities/contract_review/two_stage/extract_signature.py` — `pending`
  - `tests/two_stage/test_prepare_signature.py` — `pending`
  - 生产配置、提交、推送与归档 — `not_applicable`
- 备注：下一实现包必须将候选、装配、证据/coverage、稳定键和对抗测试作为同一契约簇，先补 RED 再修复；本决定不要求新增 `slot_ref` 或关系引文 Schema。

### `DEC-LTC-20260910-001` — Prepare 固定三窗口协作与增量读取

- 状态：`superseded`
- 作用域：`change:contract-review-prepare-api`
- 决定日期：2026-09-10
- 确认人：用户明确确认固定使用主控制、实现和复核三个窗口；非必要不新开窗口，既有窗口只重读直接相关变更
- 决定：Prepare 后续固定保留主控制、实现和复核三个用户手动管理的角色窗口。主控制是唯一的任务派发与推进出口，向实现或复核窗口提供清晰的单任务指令；实现窗口是唯一代码/测试写入者，只在白名单内工作并完成即停；复核窗口始终只读，独立核对变更与证据，向主控制提交单一门禁结论和可执行的最小修复方向，不直接授权实现。三个既有窗口均按变更增量读取，复用未失效的权威理解和验证证据；只有窗口新建、替换、角色切换、上下文不可靠、权威/工作区基线漂移或用户明确要求时，才执行完整接收门禁和必要交接。复核期间实现窗口冻结写入。用户负责创建、替换窗口及选择模型；助手不得自动创建、fork、替换或静默切换窗口。
- 权威证据：
  - 2026-09-10 用户对固定三窗口、清晰跨窗口指令及增量重读的明确确认
  - `DEC-LTC-20260901-001` 的用户手动创建窗口和交接责任边界
- 取代：已由 `DEC-LTC-20260913-002` 取代；后者保留本记录的用户手动窗口、单写入者、增量读取和复核职责，但将日常活跃窗口改为主控制与实现两个，复核按门禁临时启用
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `docs/superpowers/playbooks/2026-09-07-prepare-execution-guide.md` — `synchronized`
  - `app/capabilities/contract_review/two_stage/AGENTS.md` — `synchronized`
  - OpenSpec、业务设计、实施计划、代码、测试、生产配置、提交、推送与归档 — `not_applicable`
- 备注：执行指南是三窗口职责、增量重读和跨窗口指令格式的唯一详细规则源；AGENTS 只保留入口约束和链接，避免多处维护完整细则。

### `DEC-LTC-20260910-002` — Prepare 实现窗口使用 DeepSeek V4.1 Flash

- 状态：`active`
- 作用域：`change:contract-review-prepare-api`
- 决定日期：2026-09-10
- 确认人：用户明确确认当前需要替换实现窗口，且后续实现窗口改用 DeepSeek V4.1 Flash，不再使用 Qwen
- 决定：Prepare 的实现窗口后续统一选择 DeepSeek V4.1 Flash。现有实现窗口不由助手自动切换；需要替换时由用户手动创建或替换窗口并选择该模型。主控制和复核窗口保持其现有、由用户选择的模型，不因本决定切换。模型的具体 UI 展示名或部署标识以用户当时可选项为准，助手不得臆测映射为其他模型 ID。用户明确授权前，不建议或自动回退实现窗口到 Qwen、Terra、Sol、Luna 或 Astra。此决定只改变 Codex 协作窗口的模型选择，不修改 LTC 生产模型、路由、配置、Prompt、Schema 或业务契约。
- 权威证据：
  - 2026-09-10 用户对实现窗口改用 DeepSeek V4.1 Flash 及当前新开实现窗口的明确确认
- 取代：无；补充 `DEC-LTC-20260910-001` 的固定三窗口规则，并仅替换执行指南中实现窗口的 Qwen 起始模型建议
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `docs/superpowers/playbooks/2026-09-07-prepare-execution-guide.md` — `synchronized`
  - `app/capabilities/contract_review/two_stage/AGENTS.md` — `not_applicable`，该文件仅链接执行指南的模型规则
  - OpenSpec、业务设计、实施计划、代码、测试、LTC 生产配置、提交、推送与归档 — `not_applicable`
- 备注：模型选择是用户确认的协作资源规则，不作为模型能力、时延、成本或生产可用性的实测结论。

### `DEC-LTC-20260910-003` — Task 7 商业事实内部候选与装配入口

- 状态：`active`
- 作用域：`change:contract-review-prepare-api`
- 决定日期：2026-09-10
- 确认人：用户明确确认 Task 7 在 GREEN 前锁定商业装配入口与最小内部候选字段，避免 Prompt、候选 Schema、装配和测试漂移
- 决定：`extract_commercial.py` 唯一入口为 `extract_amount_copy_manifest(documents, canonical_parties, evidence, extraction_ranges=None) -> CommercialFactDomains`，其中 `documents` 为 `PreparedDocuments`，结果仅承载 `amount_payment`、`copy_terms` 和 `attachment_manifest` 三个 `FactDomain`。`prepare_amount_copy_main` 只处理主合同金额/份数；附件清单候选按文档处理，实际物理附件只能引用 `source_snapshot.attachments`。为表达既有公开事实字段，`AmountCopyCandidate` 增加金额角色、税务口径、关系种类、阶段顺序/触发条件/期限/方式和份数分配语义；`AttachmentCandidate` 增加声明候选引用、实际目标文档键集合和关系状态。模型 `candidate_ref` 只在单次调用内有效；附件关系的目标必须使用实际 `document_key`，逻辑附件的 `source_locator` 由其已定位 `quote` 生成。本决定不改变公开 `ReviewContext`、既有事实域或 Prepare 的不计算/中性关系边界。
- 权威证据：
  - 2026-09-10 用户对上述内部候选与装配接口方案的明确确认
  - `openspec/changes/contract-review-prepare-api/specs/contract-review/spec.md` 的 amount_payment、copy_terms、attachment_manifest 公开事实要求
  - `openspec/changes/contract-review-prepare-api/design.md` 第 7—10 节
- 取代：无；补充 `DEC-LTC-20260908-001` 的跨层契约簇闭合要求，不改变已确认业务语义；附件模型上下文和无定位 source gap 键的具体口径由 `DEC-LTC-20260911-001` 澄清
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `openspec/changes/contract-review-prepare-api/design.md` — `synchronized`
  - `docs/superpowers/plans/2026-08-25-contract-review-prepare-api.md` — `synchronized`
  - `app/capabilities/contract_review/two_stage/prepare_model.py` — `synchronized`
  - `app/capabilities/contract_review/two_stage/prepare_response_formats.py` — `synchronized`
  - `prompts/contract_review_prepare.yaml` — `synchronized`
  - `app/capabilities/contract_review/two_stage/extract_commercial.py` — `synchronized`
  - `tests/two_stage/test_prepare_amount_payment.py` — `synchronized`
  - `tests/two_stage/test_prepare_copy_terms.py` — `synchronized`
  - `tests/two_stage/test_prepare_attachment_manifest.py` — `synchronized`
  - OpenSpec public spec、公共 Schema、生产配置、提交、推送与归档 — `not_applicable`
- 备注：实现前先将当前双形态兼容 RED 改为该唯一入口的 RED；随后只以同一批次完成 Prompt、候选 Schema、响应 Schema、装配、证据/coverage、稳定键和测试闭合。2026-09-11 独立只读复核判定 Task 7 商业三域代码实现阶段 `READY`；组件/Mock 与静态契约证据不替代服务/API、真实 vLLM、真实合同或生产端点验证。

### `DEC-LTC-20260911-001` — Task 7 附件模型上下文与无定位来源缺口键

- 状态：`active`
- 作用域：`change:contract-review-prepare-api`
- 决定日期：2026-09-11
- 确认人：用户明确确认 A+B，并授权同步文档
- 决定：本记录澄清并补充 `DEC-LTC-20260910-003`，不取代其唯一入口、候选或公开事实边界。每次 `prepare_attachment_document` 调用的 `extraction_input` SHALL 为确定性 JSON 对象，并始终同时提供 `extraction_ranges`（无范围为 `[]`）、当前 `document_key` 和排序后的 `available_attachment_document_keys`；后者只能来自 `source_snapshot.attachments`。该载荷只属于模型内部上下文，不改变 `invoke_typed_prepare_model` 或公开 Prepare 接口；后端仍须拒绝快照外目标及将单次调用 `candidate_ref` 当作目标文档键的输出。对于无可信可定位引文的 source gap（包括无引文和引文无法定位），`FactIssue` 的稳定键只使用既有固定错误码、`document_key` 和排序后的 `affected_fact_kinds`，不得使用模型 `quote`、`message`、候选数组顺序或候选引用。相同稳定坐标的重复缺口合并为一个 `FactIssue`，使用确定性系统消息且不伪造 `evidence_ids`。
- 权威证据：
  - 2026-09-11 用户对上述 A+B 的明确确认
  - `openspec/changes/contract-review-prepare-api/design.md` 第 4、7—10 节的证据、覆盖、稳定键和 Task 7 内部接口边界
  - `openspec/changes/contract-review-prepare-api/specs/contract-review/spec.md` 的来源快照、覆盖和稳定键要求
- 取代：无；澄清 `DEC-LTC-20260910-003`
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `openspec/changes/contract-review-prepare-api/design.md` — `synchronized`
  - `docs/superpowers/plans/2026-08-25-contract-review-prepare-api.md` — `synchronized`
  - `prompts/contract_review_prepare.yaml` — `synchronized`
  - `app/capabilities/contract_review/two_stage/extract_commercial.py` — `synchronized`
  - `tests/two_stage/test_prepare_amount_payment.py` — `synchronized`
  - `tests/two_stage/test_prepare_copy_terms.py` — `synchronized`
  - `tests/two_stage/test_prepare_attachment_manifest.py` — `synchronized`
  - `app/capabilities/contract_review/two_stage/prepare_model.py`、`app/capabilities/contract_review/two_stage/prepare_response_formats.py`、OpenSpec public spec、公共 Schema、生产配置、提交、推送与归档 — `not_applicable`
- 备注：本记录只闭合本轮 P1-3 和 P1-5 的内部接口与键语义；阶段付款、多个整体金额关系及金额/份数各自消费来源缺口已按既有正式要求在同一 GREEN 批次闭合。2026-09-11 独立只读复核确认本记录无遗留 P1/P2；服务/API、真实 vLLM、真实合同和生产端点验证仍未执行。

### `DEC-LTC-20260911-002` — Task 8 标准附件扫描的边界证明责任

- 状态：`active`
- 作用域：`change:contract-review-prepare-api`
- 决定日期：2026-09-11
- 确认人：用户明确确认采用派生式边界证明
- 决定：本记录澄清 Task 8 的“附件边界可靠”条件，不取代标准附件目录或普通完整提取回退边界。标准附件扫描计划只能从 `PreparedDocuments` 与待处理 `document_key` 派生，不接受只有 `document_key` 与 Markdown 的旧提取器 `PreparedDocument`，也不接受调用方/模型提供的 `boundary_reliable` 标记。上传附件仅在其 `document_key` 同时存在于 `source_snapshot.attachments` 和 `markdown_by_document` 时具有扫描资格；内嵌附件还必须以 `source_locator` 验证主 Markdown 切片与该附件 Markdown 一致。无法证明边界可靠时，扫描计划返回 `None` 并走普通完整提取。`SafetyScanPlan.scanned_range` 和 `candidate_ranges` 固定为 `MarkdownCharLocator` 字符串，不兼容 tuple、list 或任意带 `start/end` 的对象。
- 权威证据：
  - 2026-09-11 用户对上述派生式边界证明方案的明确确认
  - `openspec/changes/contract-review-prepare-api/specs/contract-review/spec.md` 的标准附件边界可靠、安全扫描与普通提取回退要求
  - `openspec/changes/contract-review-prepare-api/design.md` 第 10 节的标准附件目录与扫描失败边界
- 取代：无；澄清实施计划 Task 8 的内部扫描入口
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `openspec/changes/contract-review-prepare-api/design.md` — `synchronized`
  - `docs/superpowers/plans/2026-08-25-contract-review-prepare-api.md` — `synchronized`
  - `app/capabilities/contract_review/two_stage/long_document.py` — `synchronized`
  - `tests/two_stage/test_prepare_long_document.py` — `synchronized`
  - `app/capabilities/contract_review/two_stage/documents.py`、`app/capabilities/contract_review/two_stage/extract_header_parties.py`、公共 Schema、OpenSpec public spec、Prompt、生产配置、提交、推送与归档 — `not_applicable`
- 备注：本决定只决定扫描资格的证据来源和强类型 locator 形态；目录四类、同义名称为空、全文扫描召回范围与局部提取/技术失败边界仍按现有正式契约执行。

### `DEC-LTC-20260911-003` — Task 8 标准附件正文结构交叉印证的保守判据

- 状态：`active`
- 作用域：`change:contract-review-prepare-api`
- 决定日期：2026-09-11
- 确认人：用户明确确认采用保守 Markdown 正文结构判据
- 决定：本记录细化 Task 8 的“正文结构可交叉印证”，不取代 `DEC-LTC-20260911-002` 的边界证明责任。首期只有规范化 Markdown 中存在至少一个非身份元数据的 `##` 至 `######` 正文标题，且该标题后存在非空、非身份元数据正文时，才满足正文结构条件。任何 `#`/H1 标题（无论是否与文档名称相同）均不构成正文分节。首期不启用中文编号段落标题兼容；不满足该条件的附件返回 `None` 并走普通完整提取。
- 权威证据：
  - 2026-09-11 用户对保守 Markdown 正文结构判据的明确确认
  - `openspec/changes/contract-review-prepare-api/design.md` 第 10 节的“正文结构可交叉印证”与普通完整提取回退要求
  - `docs/superpowers/plans/2026-08-25-contract-review-prepare-api.md` Task 8 的可靠识别与安全扫描要求
- 取代：无；补充 `DEC-LTC-20260911-002`，两者共同约束 Task 8 标准附件扫描资格
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `openspec/changes/contract-review-prepare-api/design.md` — `synchronized`
  - `docs/superpowers/plans/2026-08-25-contract-review-prepare-api.md` — `synchronized`
  - `app/capabilities/contract_review/two_stage/long_document.py` — `synchronized`
  - `tests/two_stage/test_prepare_long_document.py` — `synchronized`
  - `app/capabilities/contract_review/two_stage/documents.py`、公共 Schema、OpenSpec public spec、Prompt、生产配置、`prepare_service.py`、提交、推送与归档 — `not_applicable`
- 备注：本决定只固定首期正文结构资格判据；四类目录、空同义名称、边界证明、全文扫描召回范围、局部提取和技术失败边界仍按既有正式契约执行。中文编号段落标题的支持如有需要，必须另行经业务确认和版本化变更。

### `DEC-LTC-20260911-004` — Task 8 扫描计划与 Task 9 服务编排的唯一责任边界

- 状态：`active`
- 作用域：`change:contract-review-prepare-api`
- 决定日期：2026-09-11
- 确认人：用户明确确认将 Task 8 Step 4–5 的服务编排行为并入 Task 9
- 决定：`long_document.py` 只负责四类标准附件的可靠识别、全文确定性安全扫描和局部范围计划，不调用领域提取器、不聚合域覆盖，也不决定整个 Prepare 请求的成功或失败。标准附件无候选时不调用该附件的全文 LLM 提取、相关域以 `COMPLETE` 空事实结束；命中时仅以合并后的可验证局部范围调用适用的 party/signature 提取器；最终证据坐标去重以及扫描、定位、局部提取、证据装配或合并失败时整个请求失败，均由唯一的 `prepare_service.py` 在 Task 9 服务编排中验证并实现。Task 8 Step 4–5 作为该服务测试的依赖需求保留，不单独创建或提前接入服务。
- 权威证据：
  - 2026-09-11 用户对上述 Task 8/Task 9 编排归属方案的明确确认
  - `openspec/changes/contract-review-prepare-api/specs/contract-review/spec.md` 的标准附件局部提取与整请求失败要求
  - `openspec/changes/contract-review-prepare-api/design.md` 第 10 节固定流水线与失败边界
  - `docs/superpowers/plans/2026-08-25-contract-review-prepare-api.md` 的单向依赖和 Task 8/Task 9 实施顺序
- 取代：无；澄清 Task 8 Step 4–5 与 Task 9 的执行责任，不改变 OpenSpec 7.5 的正式行为要求
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `openspec/changes/contract-review-prepare-api/design.md` — `synchronized`
  - `docs/superpowers/plans/2026-08-25-contract-review-prepare-api.md` — `synchronized`
  - `openspec/changes/contract-review-prepare-api/tasks.md` — `synchronized`
  - `app/capabilities/contract_review/two_stage/prepare_service.py` — `synchronized`
  - `tests/two_stage/test_prepare_service.py` — `synchronized`
  - `app/capabilities/contract_review/two_stage/long_document.py`、`tests/two_stage/test_prepare_long_document.py`、公共 Schema、Prompt、生产配置、提交、推送与归档 — `not_applicable`
- 备注：OpenSpec 7.5 保持未勾选，直到 Task 9 对无候选结束、命中局部提取、普通完整提取回退和整请求失败闭合取得独立证据；本决定不授权提前创建服务或进入 API 路由。

### `DEC-LTC-20260911-005` — Task 9 Prepare 流程的语义顺序与运行时观测边界

- 状态：`active`
- 作用域：`change:contract-review-prepare-api`
- 决定日期：2026-09-11
- 确认人：用户明确确认采用语义顺序与关键依赖，不要求运行时逐一暴露十二个独立阶段
- 决定：`prepare_contract` 必须满足既定 Prepare 流程的语义顺序和关键依赖：输入规范化、来源快照/内嵌附件/重复门禁在领域提取前完成；标准附件分类与安全扫描在其局部或全文提取前完成；canonical parties 在依赖它的附件 party 装配前完成；六域提取在证据/覆盖聚合、引用验证、稳定排序和摘要计算前完成。允许一个内部组件封装多个逻辑阶段，不要求运行时逐一暴露十二个独立阶段，也不新增任何调用方可见的阶段追踪接口。测试验证上述可观察依赖与最终行为；既有组件内的细分行为仍由其独立测试负责。
- 权威证据：
  - 2026-09-11 用户对上述语义顺序和运行时观测边界的明确确认
  - `openspec/changes/contract-review-prepare-api/design.md` 第 10 节固定 Prepare 流水线
  - `docs/superpowers/plans/2026-08-25-contract-review-prepare-api.md` Task 9 的服务装配要求
- 取代：无；细化 Task 9 Step 1 的测试观测方式，不改变既有 Prepare 逻辑顺序、失败边界或唯一公开入口
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `openspec/changes/contract-review-prepare-api/design.md` — `synchronized`
  - `docs/superpowers/plans/2026-08-25-contract-review-prepare-api.md` — `synchronized`
  - `openspec/changes/contract-review-prepare-api/tasks.md` — `synchronized`
  - `tests/two_stage/test_prepare_service.py` — `synchronized`
  - `app/capabilities/contract_review/two_stage/prepare_service.py`、公共 Schema、Prompt、生产配置、提交、推送与归档 — `not_applicable`
- 备注：本决定只取消“必须精确观测十二个运行时独立阶段”的测试要求；Task 9 对标准附件、证据、技术失败和 coverage 的严格验收要求不变。

### `DEC-LTC-20260912-001` — Prepare 三窗口的低消耗证据复用与交接回执

- 状态：`superseded`
- 作用域：`change:contract-review-prepare-api`
- 决定日期：2026-09-12
- 确认人：用户明确确认在不降低代码质量与门禁的前提下优化 token 消耗
- 决定：固定主控制、实现、复核三窗口不变，窗口间仍须输出可复用的终结交接回执，不能以完全静默替代证据交接。既有可靠窗口只按主控制给出的增量清单重读；主控制维护当前 Task 的权威位置、基线、白名单、可复用证据和门禁状态，不要求每轮重读未变的大型权威文档。首次建立或语义变更时使用完整闭合矩阵；后续仅报告矩阵变化与阻断。RED 测试或纯测试收紧默认运行定点验证，GREEN 实现运行定点及直接受影响回归；全量两阶段回归和严格 OpenSpec 校验保留给阶段门禁、独立复核收尾、服务/API 接通或影响范围无法确定时，不能因精简而取消。每轮只保留必要的短测试摘要和终结回执；同一内容未变时复用有效证据。主控制按风险建议推理强度：只读基线/证据核对可用 low，窄测试或局部修复通常 medium，首次跨层 GREEN 实现、公共契约或架构编排通常 high；用户保留模型与窗口选择权。该规则不放宽独立复核、两轮熔断、受保护配置、真实环境分层证据或提交授权要求。
- 权威证据：
  - 2026-09-12 用户基于实际 token 消耗结构作出的明确优化确认
  - `docs/superpowers/playbooks/2026-09-07-prepare-execution-guide.md` 的固定三窗口、增量读取、证据复用与独立复核规则
  - `DEC-LTC-20260908-001` 的跨层契约簇闭合与两轮熔断
  - `DEC-LTC-20260910-001` 的固定三窗口与增量读取
- 取代：已由 `DEC-LTC-20260913-002` 取代；后者继承本记录的低消耗证据复用、短回执、分层验证和两轮熔断，不再要求复核窗口日常常驻
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `docs/superpowers/playbooks/2026-09-07-prepare-execution-guide.md` — `synchronized`
  - `app/capabilities/contract_review/two_stage/AGENTS.md` — `synchronized`
  - OpenSpec public spec、设计、实施计划、任务清单、生产代码、测试、Prompt、Schema、生产配置、提交、推送与归档 — `not_applicable`
- 备注：交接回执是最低限度的窗口间证据接口，不是新的状态数据库、业务权威或对外接口；完整证据仍可按需从代码、测试、权威文档和实际命令重新核对。

### `DEC-LTC-20260913-001` — Prepare 契约簇熔断状态与不可达 RED 断言护栏

- 状态：`active`
- 作用域：`change:contract-review-prepare-api`
- 决定日期：2026-09-13
- 确认人：用户明确授权同步本澄清，以防止主控制将同一契约簇的连续 P1/P2 误作独立小任务反复派发
- 决定：主控制在同一契约簇首次 `BLOCKED` 时，必须固定记录 `cluster`、`repair_cycle` 和 `fuse_state`；新任务卡、失败数量变化、测试函数拆分或 P1 文案变化均不得重置轮次。每次为关闭同一簇 P1/P2 的写入使轮次加一；连续两轮后仍有新的、具正式依据的 P1/P2 时立即标记 `FROZEN`。`FROZEN` 的唯一下一动作只能是只读归因（规则、实现、测试矩阵或环境）及矩阵闭合判断，不得继续测试写入、派发 GREEN 或以新的 P1 文案绕过熔断。只有归因结论明确最小必要 RED 集并由主控制重新建立有界闭合矩阵后，才可恢复一次有界写入。

  `BLOCKED` 回执中的 P1/P2 必须引用当前有效的 OpenSpec、设计、计划、决策或仓库约束；仅有聊天指令、实现报告或测试行号的意见是审计观察，不能单独作为写入派发依据。若服务模块缺失使目标测试在断言体前一致终止，结果仅证明 `MODULE_ABSENT_RED`，不证明新增断言语义；reviewer 必须一次性按闭合矩阵做静态契约审计，不得以重复运行同一导入失败来驱动零散测试补丁。
- 权威证据：
  - 2026-09-13 用户对重复违反两轮熔断的根因审计，以及对本澄清和传播的明确授权
  - `DEC-LTC-20260908-001` 的跨层契约簇与两轮熔断
  - `docs/superpowers/playbooks/2026-09-07-prepare-execution-guide.md` 第 2.1、2.2、3、6 节
- 取代：无；细化 `DEC-LTC-20260908-001` 和 `DEC-LTC-20260912-001` 的执行状态与证据边界，不改变业务契约、Task 9 验收范围或三窗口职责
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `docs/superpowers/playbooks/2026-09-07-prepare-execution-guide.md` — `synchronized`
  - `app/capabilities/contract_review/two_stage/AGENTS.md` — `not_applicable`，继续只链接执行指南的详细协作规则
  - OpenSpec、业务设计、实施计划、生产代码、测试、Prompt、Schema、生产配置、提交、推送与归档 — `not_applicable`
- 备注：本决定不创建常设状态数据库；`cluster`、`repair_cycle` 和 `fuse_state` 仅作为主控制任务卡和终结回执中的最小临时证据。

### `DEC-LTC-20260913-002` — Prepare 日常双窗口与按门禁临时复核

- 状态：`active`
- 作用域：`change:contract-review-prepare-api`
- 决定日期：2026-09-13
- 确认人：用户明确确认日常仅使用主控制和实现窗口；复核窗口只在主控制判定的必要门禁临时启用
- 决定：Prepare 日常活跃窗口固定为主控制与实现两个。主控制仍是唯一派发出口，实现仍是唯一代码/测试写入者；复核保留为只读角色而非日常常驻窗口。主控制只在首次完整跨层 RED 矩阵、两轮熔断后的矩阵闭合审计、首次跨层 GREEN 服务实现、公共契约/稳定键/引用/覆盖/失败/模型调用语义变化、服务/API 接通或阶段收口，以及用户明确要求时，向复核窗口派发单一只读任务。普通定点 RED 补强和未触发上述门禁的局部实现，由主控制核对差异、测试断言和有效证据后直接给出唯一下一动作，不自动复审。需要复核而没有可用窗口时，用户才创建或替换该窗口并选择模型；助手不得自动创建、替换或并行重开角色窗口。
- 权威证据：
  - 2026-09-13 用户对“日常主控+实现，复审仅在必要门禁”工作方式的明确确认
  - `DEC-LTC-20260908-001` 的跨层契约簇与两轮熔断
  - `DEC-LTC-20260913-001` 的熔断状态与不可达 RED 护栏
  - `docs/superpowers/playbooks/2026-09-07-prepare-execution-guide.md` 的角色、独立复核与低消耗证据规则
- 取代：`DEC-LTC-20260910-001`、`DEC-LTC-20260912-001`；继承其用户手动窗口、增量读取、短回执、低消耗验证、单写入者、独立复核职责和两轮熔断，不改变业务契约、模型选择、提交授权或真实环境证据分层
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `docs/superpowers/playbooks/2026-09-07-prepare-execution-guide.md` — `synchronized`
  - `app/capabilities/contract_review/two_stage/AGENTS.md` — `synchronized`
  - OpenSpec、业务设计、实施计划、生产代码、测试、Prompt、Schema、生产配置、提交、推送与归档 — `not_applicable`
- 备注：复核角色仍是独立门禁，不得由实现窗口自我放行；本决定只减少其日常启动频率。

### `DEC-LTC-20260913-003` — Prepare 上下文与 token 卫生的可复用操作规则

- 状态：`active`
- 作用域：`change:contract-review-prepare-api`
- 决定日期：2026-09-13
- 确认人：用户明确要求将本轮关于缓存命中、未命中输入、短交接和窗口使用的讨论同步为后续窗口遵循规则
- 决定：在不降低既有门禁和证据标准的前提下，主控制、实现和按门禁启用的复核窗口均按“稳定规则在前、动态事实在后”组织指令；正常任务只传递当前 `Task / cluster / repair_cycle / fuse_state`、变更胶囊、权威定位和必要验证，不重复粘贴历史 P1/P2、完整回执、完整矩阵、完整 Git 状态、traceback 或未变基线。日常读取当前有效决定和指定段落，完整接收门禁只在既有触发条件下执行；历史 DEC 保留取代链和追溯价值，不得仅为节省 token 而合并、删除或重写，日常以活跃决定和执行指南作操作索引。不得为了提高缓存率而替换窗口、切换模型/推理档位、跳过必要现场核对或增加常设复核；模型和窗口变更仍依既有决定由用户选择。平台仅提供汇总 token 指标时，只报告已测得的未命中输入、缓存命中和输出，不臆造未命中原因或可复用 token；不得仅为该诊断新增 API 调用、日志采集或项目持久化。缓存与 token 数据只用于优化协作开销，不构成业务、实现或验收证据。
- 权威证据：
  - 2026-09-13 用户对将 19:20 后上下文、缓存与 token 优化讨论作为后续窗口规则的明确授权
  - `DEC-LTC-20260913-001` 的短状态证据、熔断与不可达 RED 断言边界
  - `DEC-LTC-20260913-002` 的日常双窗口与按门禁临时复核
  - `docs/superpowers/playbooks/2026-09-07-prepare-execution-guide.md` 的增量读取、短回执和分层验证规则
- 取代：无；补充 `DEC-LTC-20260913-001`、`DEC-LTC-20260913-002` 的资源高效执行方式，不改变业务契约、复核门禁、模型选择权、验证预算或真实环境证据要求
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `docs/superpowers/playbooks/2026-09-07-prepare-execution-guide.md` — `synchronized`
  - `app/capabilities/contract_review/two_stage/AGENTS.md` — `not_applicable`，该文件已将详细协作约束统一路由至执行指南
  - OpenSpec、业务设计、实施计划、生产代码、测试、Prompt、Schema、生产配置、提交、推送与归档 — `not_applicable`
- 备注：本决定不建立 token 台账、缓存诊断服务或新的交接文件；状态胶囊仍是任务卡和终结回执中的临时信息。

### `DEC-LTC-20260914-001` — Prepare 风险分级纵向切片与 Gate 式独立审计

- 状态：`active`
- 作用域：`change:contract-review-prepare-api`
- 决定日期：2026-09-14
- 确认人：用户明确授权将风险分级纵向切片、主控制/实现双角色常驻和 Gate 式独立审计作为后续 Prepare 治理规则落库。
- 决定：主控制是唯一 Task 派发与最终 Gate 决策出口，日常只保持主控制与实现两个活跃角色；不保留常驻第三审计窗口。验证按 LOW/MEDIUM/HIGH 风险分级，组件、Service、API 与真实链路证据分层成立且不得互相替代。普通 Task 不默认独立审计；主控制按 Gate 选择 `AUDIT_TYPE=NONE|MATERIAL|SITE|BOTH`，其中 MATERIAL 使用最小 `AUDIT_PACKET` 供用户交给 ChatGPT 独立审计，SITE 由可进入现场的独立代理取证，BOTH 固定先 SITE 后 MATERIAL。实现者报告不得替代 SITE。跨层契约簇优先一次性闭合矩阵与最小 RED 集；连续两轮仍不能闭合时按既有熔断规则停止零散补丁。稳定且现场未变化的有效证据允许复用。Prepare 后续按可验证纵向能力推进；当前 Service 为 `READY_WITH_NOTES` 后原则上冻结，M1 为 HIGH 风险 API Closure，M2 为 HIGH 风险最小真实 E2E；最小真实 smoke 不自动等于 Prepare DONE。
- 权威证据：
  - 2026-09-14 用户对本治理模式、审计类型、风险分级、M1/M2 编排和 Task 9 状态同步的明确授权
  - `DEC-LTC-20260908-001`、`DEC-LTC-20260913-001` 的契约簇与熔断边界
  - `DEC-LTC-20260913-002`、`DEC-LTC-20260913-003` 的双窗口、按门禁复核与低消耗证据复用规则
- 取代：无；澄清并细化 `DEC-LTC-20260908-001`、`DEC-LTC-20260913-001`、`DEC-LTC-20260913-002` 和 `DEC-LTC-20260913-003` 的执行方式，不改变 Prepare 业务契约、生产模型配置、提交授权或真实环境验收要求。
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `docs/superpowers/playbooks/2026-09-07-prepare-execution-guide.md` — `synchronized`
  - `docs/superpowers/plans/2026-08-25-contract-review-prepare-api.md` — `synchronized`
  - `openspec/changes/contract-review-prepare-api/tasks.md` — `synchronized`
  - `app/capabilities/contract_review/two_stage/AGENTS.md` — `not_applicable`，已保留不可违反核心规则并路由至执行指南
  - OpenSpec public spec/design、实现代码、测试、Prompt、生产配置、提交、推送与归档 — `not_applicable`
- 备注：本记录保存治理变化及其原因；风险分级、审计 Packet 字段和 Gate SOP 以执行指南为唯一详细规则源。Task 9 服务状态只表示已验证的服务层边界，不授权 M1、真实链路或 Prepare DONE。

### `DEC-LTC-20260915-001` — Prepare 风险驱动测试取证与特征化测试边界

- 状态：`active`
- 作用域：`change:contract-review-prepare-api`
- 决定日期：2026-09-15
- 确认人：用户明确要求测试策略优先抓主要矛盾，避免为形式化 RED 或理论覆盖率扩展低概率边界测试。
- 决定：P0 主链路、已实际发生的缺陷、高影响数据/安全/API 契约故障和阻塞 M1/M2 的问题必须取得与风险相称的直接证据并闭环；P1 仅在有明确风险或真实暴露时补最小验证；P2 低概率边缘或仅为覆盖率的组合不预先扩展，实际暴露后再补回归。行为变更或修复仍采用 `RED → GREEN`；对既有冻结行为的纯补证据/特征化测试，允许首次 `GREEN`，并记录为 `RED_N/A + negative-control discrimination verified`，不得为制造 RED 修改生产实现，也不得把变异反例记为标准 TDD RED。相邻层已有充分证据时不重复构造低收益链路测试。
- 权威证据：
  - 2026-09-15 用户对“只抓主要矛盾”、低概率边缘在真实暴露后再补回归的明确确认
  - `DEC-LTC-20260914-001` 的风险分级、分层证据与 Gate 边界
- 取代：无；澄清 `DEC-LTC-20260914-001` 的测试取证方式，不改变其 HIGH Gate、真实环境验收、公共契约验证或独立审计要求。
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `docs/superpowers/playbooks/2026-09-07-prepare-execution-guide.md` — `synchronized`
  - OpenSpec、设计、实施计划、实现代码、测试、Prompt、Schema、生产配置、提交、推送与归档 — `not_applicable`
- 备注：该决定不把“真实出现一个解决一个”解释为跳过已知 P0/P1、真实 M2 失败归因或失败响应契约；它只停止低收益的形式化补测循环。

### `DEC-LTC-20260915-002` — Prepare SITE 探针必须命中真实调用边界

- 状态：`active`
- 作用域：`change:contract-review-prepare-api`
- 决定日期：2026-09-15
- 确认人：用户要求复盘并消除将辅助 `/models` 探针误判为真实模型调用链故障的流程缺陷，并授权清理跨文档遗留规则。
- 决定：涉及真实模型、端点、代理或环境的 SITE 结论必须直接取自项目实际调用边界及其有效运行时配置；辅助健康、目录或 SDK 端点只能作为旁证，除非已证明与目标调用路径等价。目标边界未实际执行时，结论只能是 `INCONCLUSIVE`，不得根据辅助端点的状态码归因认证、代理、路由或模型故障。辅助探针结论与既有真实调用证据或用户提供反证冲突时，主控制必须降级结论并优先核验真实调用边界后再作 Gate 判断。
- 权威证据：
  - 2026-09-15 M2 SITE 中 `/models` 返回 404 而项目 `get_chat_model → invoke_model` 无业务调用成功的现场复盘
  - 2026-09-15 用户对该主控误判的明确质询，以及对跨文档清理与澄清的授权
  - `DEC-LTC-20260914-001` 的 SITE/BOTH Gate 与真实环境分层证据要求
- 取代：无；补充 `DEC-LTC-20260914-001` 的 SITE 取证有效性，不改变真实 M2 验收、公共 API 契约、生产配置或用户对窗口的控制权。
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `docs/superpowers/playbooks/2026-09-07-prepare-execution-guide.md` — `synchronized`
  - `app/capabilities/contract_review/two_stage/AGENTS.md` — `synchronized`
  - `docs/superpowers/plans/2026-08-25-contract-review-prepare-api.md` — `synchronized`
  - `openspec/changes/contract-review-prepare-api/tasks.md` — `synchronized`
  - OpenSpec public spec/design、实现代码、测试、Prompt、Schema、生产配置、提交、推送与归档 — `not_applicable`
- 备注：该决定不要求预设任何通用 `/models`、`/health` 或 SDK 探针；每次 SITE 先从当前项目真实入口反向确定最小验证路径。

### `DEC-LTC-20260915-003` — Prepare Task Card 定点读取与主控派发前硬门槛

- 状态：`active`
- 作用域：`change:contract-review-prepare-api`
- 决定日期：2026-09-15
- 确认人：用户明确确认以 Task Card 的 `TARGETED_READS` / `FORBIDDEN_BROAD_READS` 与主控发送前逐项自检，作为常规派发硬门槛。
- 决定：每张实现、SITE 或复核 Task Card 必须显式给出 `TARGETED_READS` 和 `FORBIDDEN_BROAD_READS`。前者逐项限定“文件 / 精确章节、定义或行段 / 目的”；无读取需求时明确写 `none`。主控制在发送前必须机械核对执行窗口、唯一 Task、权威位置、定点读取、允许范围、禁止操作、验证/停止条件；任一项缺失即不得派发。此检查是派发前的短核对，不要求重读无关文档、重跑验证或增加常驻窗口。
- 权威证据：
  - 2026-09-15 用户对“主控硬门槛、发送前逐项自检”的明确授权
  - `DEC-LTC-20260913-003` 的上下文与 token 卫生要求
  - `DEC-LTC-20260915-002` 对真实边界取证的最小定点读取要求
- 取代：无；澄清 `DEC-LTC-20260913-003` 的派发落实方式，不改变风险分级、窗口控制、业务契约或各证据层的 Gate 标准。
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `docs/superpowers/playbooks/2026-09-07-prepare-execution-guide.md` — `synchronized`
  - `app/capabilities/contract_review/AGENTS.md` — `synchronized`
  - `app/capabilities/contract_review/two_stage/AGENTS.md` — `synchronized`
  - `docs/superpowers/plans/2026-08-25-contract-review-prepare-api.md` — `synchronized`
  - OpenSpec、设计、实现代码、测试、Prompt、Schema、生产配置、提交、推送与归档 — `not_applicable`
- 备注：自包含 Task Card 不授权接收窗口自行扩展探索；未列出的读取、写入或环境诊断必须返回主控制重新派发。

### `DEC-LTC-20260915-004` — Prepare 通用 Retry Gate

- 状态：`active`
- 作用域：`change:contract-review-prepare-api`
- 决定日期：2026-09-15
- 确认人：用户明确要求将 M2 Retry-01 至 Retry-04 暴露的经验固化为不局限于真实 E2E 的通用 Retry Gate。
- 决定：再次执行前，主控制必须判断上一次结果为何未能使任务推进，识别当前核心阻断，并说明本轮解除动作与相较上次新增的可判事实或已修复行为。原样 Retry 仍大概率得到同一不可判定结果时，应先以最小动作补足主要证据、观测、环境条件或有正式依据的修复；原因明确且修复完成时可直接 Retry。该规则适用于测试、接口/模型调用、构建、部署、审计与 SITE 验证，不新增常设审计、日志体系、测试矩阵或机械禁令。
- 权威证据：
  - 2026-09-15 用户对通用 Retry Gate、主要矛盾与最小证据原则的明确确认
  - M2 Retry-01 至 Retry-04：请求构造、结果回收与内部边界证据缺口使原样重试不能推进的来源案例
  - `DEC-LTC-20260914-001` 的风险分级、Gate 式审计和证据分层要求
- 取代：无；补充既有 Task Card、Gate、熔断与停止条件，不改变其触发边界。
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `docs/superpowers/playbooks/2026-09-07-prepare-execution-guide.md` — `synchronized`
  - AGENTS、OpenSpec、设计、实施计划、实现代码、测试、Prompt、Schema、生产配置、提交、推送与归档 — `not_applicable`
- 备注：M2 只作为来源案例；规则不使用 M2 专有字段，也不以“条件未满足”形式机械禁止 Retry。

### `DEC-LTC-20260916-001` — Prepare 测试有效性与 PowerShell 执行通道切换

- 状态：`active`
- 作用域：`change:contract-review-prepare-api`
- 决定日期：2026-09-16
- 确认人：用户明确要求停止“为了测试而测试”，并规定同一 PowerShell 自动执行通道两次卡住后立即切换为用户执行，避免反复试错和死循环。
- 决定：测试、诊断与审计仅在其不同结果能够改变当前实现、归因或 Gate 决策时派发；覆盖率增长、重复证据或不能推进判断的孤立 harness 验证不是独立任务理由。同一 `cluster` 的同一 PowerShell 自动执行通道连续两次未获得可用终结回执后，主控制不得启动第三次助手侧尝试，必须给出一次、可在用户持久终端执行的受控指令，并写明预期完成标识、脱敏回传边界与停止条件。用户执行不绕过 Retry Gate、熔断或真实环境 Gate，也不自动授权连续重试。
- 权威证据：
  - 2026-09-16 M2 PowerShell 自动执行多次卡住、摘要缺失而未能推进的复盘
  - 2026-09-16 用户对停止反复试错、两次卡住即切换用户执行的明确确认
  - `DEC-LTC-20260915-001` 的主要矛盾与最小测试取证原则
  - `DEC-LTC-20260915-004` 的 Retry Gate
- 取代：无；补充测试取证与 Retry Gate 的派发边界，不改变 TDD、HIGH Gate、SITE 独立性、契约簇熔断或用户对窗口的控制权。
- 受影响工件：
  - `docs/decisions/index.md` — `synchronized`
  - `docs/superpowers/playbooks/2026-09-07-prepare-execution-guide.md` — `synchronized`
  - AGENTS、OpenSpec、设计、实施计划、实现代码、测试、Prompt、Schema、生产配置、提交、推送与归档 — `not_applicable`
- 备注：两次的计数单位是同一自动执行通道未获得可用终结回执，不是模型内部重试次数、普通测试失败数或用户持久终端的执行次数。

## 5. 开放完整性缺口

- 建账前的历史决定尚未逐条迁移；当前通过 `DEC-LTC-20260826-004` 登记权威基线，后续在首次修改、澄清、交接或取代某项既有结论前渐进补建独立记录。
- Git Hook、确定性检查脚本、CI 任务和分支保护尚未建设，不属于当前第一步交付范围。
