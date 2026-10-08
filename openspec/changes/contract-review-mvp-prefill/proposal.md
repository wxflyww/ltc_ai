## Why

现行单阶段旧流程 `POST /api/v1/contract-review` 只输出组织评审结论（`overall_result` / `check_time` / `checks` / `metrics`）。合同系统的 D-02（合同管理员智能预填，13 项）和 D-03（销售人员 AI 预填，8 项）共 21 个需求项只能靠业务人员翻阅合同手工录入，无法由现有接口支撑。

两阶段 Prepare 仍在精雕细琢，且已冻结的 Prepare 契约（只输出事实、不输出裁决）与本次"把字段直接回填表单"的形态并不相同，不能为了一次最小版本演示等待 Prepare 落地。因此需要在**冻结的旧流程入口上**新增一个与评审互相隔离的预填调用形态：同一地址、同一鉴权、同一响应壳，用请求参数区分本次调用要评审还是要预填。

硬边界：`app/capabilities/contract_review/two_stage/**` 零改动，D-02 / D-03 后续并入 Prepare 事实域时另行设计。

## What Changes

- 在 `POST /api/v1/contract-review` 请求体新增**可选**参数 `mode`，取值仅两个：`review`（默认，行为与今天逐字段一致）/ `prefill`（只跑预填，不跑评审链路）。不新增独立接口、不新增网关白名单。
- 请求体再新增**可选**参数 `prefill_scope`（`all` / `d02` / `d03`，默认 `all`），仅 `mode=prefill` 时生效：让 D-02 / D-03 两个场景各取所需、只抽自己关心的组，未请求的组按未取到规则表达（仍返回、不省键）。实测 D-03 场景由 7.42s 降到 3.01s。
- `mode=prefill` 返回独立的预填数据体：`mode` / `prefill_status` / `prefill`，其中 `prefill` 由四组构成——`contract_info`（9 字段）、`contract_plan`（数组，每项 8 字段）、`finance_info`（2 字段）、`guarantee`（数组，每项 7 字段），共 26 个返回字段。**`finance_info` 由 `d02` 与 `d03` 共用**（2026-09-18 第十四轮），26 为去重后的字段总数。
- `mode=review` 的 `data` 段保持 4 个键（`overall_result` / `check_time` / `checks` / `metrics`），**不新增、不回显任何字段**；`mode` 只出现在预填响应里。
- 里程碑按固定 13 个标准名做**语义归一**（靠语义理解，不做词表硬匹配），同时返回标准名、标准名 code、原文描述与原文序号，供业务人员核对。
- `contract_plan` 与 `guarantee` 的**每一行**附 `evidence`，元素为 `{ section, quote }` 对象：按出处各列一条、去重，`section` 标注该原文片段所在的章节 / 条款标题，使业务人员能从"AI 依据"直接定位回合同原文。
- 预填在 prompt 边界内对输入做**换行归一化**：合同系统实际传入的正文可能是"一整行 + 字面量 `\n`、无真换行"的形态，不归一化会丢掉 Markdown 结构（尤其是付款计划表）。
- 预填失败 / 超时不改变 HTTP 成功语义，统一以 `prefill_status: "failed"` 与字段全 `null` / 数组全空（结构仍在，不省略键）兜底，**不抛 5xx**。
- 未取到的字段一律 `null`（数组类为空数组），不用空字符串占位；允许基于已抽到事实的推算，不允许无依据臆造。
- **取值规则补强（2026-10-03 第十五轮）**：三个金额型字段（`contract_plan[].payment_amount`、`finance_info.contract_amount`、`guarantee[].amount`）返回**不带货币符号与千分位**，但保留 `%`、小数点及其后原样小数位、数量级「万 / 亿」，且**不做任何换算**（不折「万」、不折 `%`、不转中文大写数字）；**除这 3 个字段外任何字段一律不剥离符号**。合同以 `【】` 等填空标记书写的，取值须去掉标记本身并保留紧邻的单位 / 符号 / 量纲（不得返回裸数字、裸量词）。`service_start_date` / `service_end_date` 的取值来源限定服务 / 售后 / 质保条款 —— 合同只有「事件起算 + 期限」时两字段同为 `null`，不得用合同内其他绝对日期顶替。`currency` 明确为 ISO 4217 三位大写码（`CNY` / `USD` / `JPY`），**不恒为 `CNY`**。上述规则**全部在 prompt 层实现，服务端不做任何字符串后处理**。
- 不修改 `mode=review` 的现有链路、现有响应字段与现有测试期望；不触碰 `two_stage/**`、现有评审 prompt 与 `ContractReviewData` 模型。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `contract-review`：在两个既有入口（JSON 入口与 Markdown 文件入口）上新增预填调用形态（`mode=prefill`）、预填字段数据契约、里程碑语义归一、原文依据定位与预填失败兜底；`mode=review` 及既有评审行为保持不变。

## Impact

- **API**：`POST /api/v1/contract-review` 请求体新增可选 `mode` 与可选 `prefill_scope`；`POST /api/v1/contract-review/upload-md` 表单新增同名两个可选字段（默认 `review` / `all`，**不传时行为与改造前逐字段一致**）；新增预填响应数据体。非法取值由现有请求校验机制统一返回 `code=10001` / HTTP 422，无需额外设计。
- **代码**：`app/capabilities/contract_review/` 内新增预填 prompt 构造、预填编排与**独立响应模型**（`ContractReviewData` 零改动）；复用 `app/models/llm.py` 的模型适配与现有重试 / 错误码；`checks.py`、`amounts.py`、`_run_b1`、`_run_b4` 等检查点逻辑一行不动。预填与评审在路由层分流，走两条独立路径。
- **依赖（跨 capability，不在本 change 内）**：预填正确性依赖"关闭模型思考模式"，该改动同时涉及 `contract_review` 与 `two_stage` 两条链路、并须显式**排除 `translate`**，故另立 change `llm-disable-thinking`（本 change 声明依赖，具体实施项见该 change）。本 change 自带的结构化输出（`response_format`）与 `required_keys` 校验不依赖它，可先独立落地。
- **Prompt**：新增预填专用 prompt 资源；现有评审 prompt 不改。
- **配置**：无新增配置项，不新增依赖。
- **测试**：新增预填契约测试（两种 mode 的响应形状、`prefill_status` 各分支、`null` 与空数组表达、`evidence` 元素必带 `section` / `quote`）与换行归一化用例；**最强回归判据**是 `mode` 不传 / `=review` 时 `data` 段与今天逐字段一致。
- **调用方**：D-02（合同管理员预填）与 D-03（销售预填）是**两个触发时机不同的场景，但共用同一个 `mode=prefill` 调用**——接口无状态、返回值不依赖调用时机，响应四组字段已按场景分组（D-02 取 `contract_info` + `contract_plan` + `finance_info`，D-03 取 `finance_info` + `guarantee`；**`finance_info` 为两场景共用** —— D-02 需要其中的 `contract_amount` 才能把 `payment_amount` 的比例原文折算成金额），合同系统各取各的组回填表单；`section` / `quote` 用于"AI 依据"的原文定位展示。不拆接口的理由与已知代价见 `docs/superpowers/specs/2026-09-15-contract-review-prefill-design.md` §3.4。**第十五轮起金额型字段不再带货币符号**，调用方仍需**按字符串接收并自行解析**（值可能含 `%`、`万 / 亿`、小数位，也可能为 `null` 或中文大写）；本次调整**不改字段名 / 类型 / 响应结构 / 请求参数 / 错误码**，调用方**无需改动**，增量说明见 `docs/integration/2026-10-03-contract-review-prefill-value-rules-change.md`。
- **不做**：不新增独立接口；不实现 `review` / `prefill` 之外的任何 mode 取值；**不动 `two_stage/**`（零改动，红线）**；不解析附件；不引入证据索引 / 覆盖度（含字段级抽取状态）/ 事实域等两阶段概念；不给 `ContractReviewData` 增加任何字段；**不改动 `translate` 能力的任何行为**；**`mode=review` 的既有链路除依赖 change 的"关思考"外不做任何改动**。

> 详细字段清单、抽取与计算口径、四轮修订记录见 `docs/superpowers/specs/2026-09-15-contract-review-prefill-design.md`（本 change 按 AGENTS.md「design.md 可选」约定不另写 design.md）。
