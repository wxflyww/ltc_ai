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

## 5. 开放完整性缺口

- 建账前的历史决定尚未逐条迁移；当前通过 `DEC-LTC-20260826-004` 登记权威基线，后续在首次修改、澄清、交接或取代某项既有结论前渐进补建独立记录。
- Git Hook、确定性检查脚本、CI 任务和分支保护尚未建设，不属于当前第一步交付范围。
