# review-summary Spec Delta

## ADDED Requirements

### Requirement: 评审智能总结接口
系统 SHALL 提供 JSON-only 的 `POST /api/v1/review-summary`，接收评审环节结构化数据，成功响应的 `data` SHALL 是整包面板 JSON（`review_summary`、`key_concerns[]`、`opinion_details[]`、`degraded_sections[]` 四块齐全）。接口 SHALL 受现有鉴权（`X-API-Key`/`Authorization: Bearer`）、Trace 与耗时中间件保护，沿用统一响应壳 `code`/`message`/`traceId`/`duration_seconds`；SHALL NOT 新增错误码、multipart 入口或响应包装层。命名 SHALL 统一为 review-summary，不引入 approval-summary。

#### Scenario: 合法请求返回整包面板
- **WHEN** 调用方以合法鉴权提交包含 `opinions[]` 的合法请求体
- **THEN** 系统 SHALL 返回 `code=0`
- **AND** `data` SHALL 同时包含 `review_summary`、`key_concerns`、`opinion_details`、`degraded_sections` 四个字段
- **AND** 响应 SHALL 携带 `traceId` 与 `duration_seconds`

#### Scenario: 请求体非法
- **WHEN** 请求体缺失 `opinions` 键，或 `action` 取枚举外的值，或任一必填字段类型错误
- **THEN** 系统 SHALL 返回 `422` 且 `code=10001`
- **AND** 系统 SHALL NOT 发起任何模型调用

### Requirement: 输入契约四组数据
请求体 SHALL 包含四组数据：`contract_meta`（整组可选，字段全 optional，后续 CRM 客户字段以新增可选字段方式向后兼容扩展）、`route_reason`（可选，`text` 为合同系统已生成好的人话原文）、`risk_register[]`（只含高风险项，12 字段全部"有就照搬、没有就不传"）、`opinions[]`（必填，可为空数组；每条含 `node_name`/`approver_name`/`role`/`action`/`comment` 必填与 `submitted_at` 建议字段，`action` SHALL 为 `pass`/`conditional`/`reject` 枚举）。通用约定：缺值给空不省键（`null`/`[]`）；所有文本原样传递，接口只引用不加工；接口对数组顺序与内容零要求，不做过滤、重排或业务正确性判断。

#### Scenario: contract_meta 整组缺省
- **WHEN** 请求未提供 `contract_meta` 或其中任一字段
- **THEN** 系统 SHALL 继续生成
- **AND** 总述 SHALL 只引用已传入的字段，缺位不补不问

#### Scenario: opinions 为空数组
- **WHEN** `opinions=[]`（评审未完成）
- **THEN** 系统 SHALL 接受请求并返回成功
- **AND** 该空态按空态矩阵降级，SHALL NOT 以参数错误拒绝

#### Scenario: 新增可选字段向后兼容
- **WHEN** 请求在 `contract_meta` 中携带本 spec 未列出的新增可选字段
- **THEN** 系统 SHALL NOT 因未知可选字段拒绝请求
- **AND** 已定义字段的行为 SHALL NOT 改变

### Requirement: 装配区按传入数据原文回显
`key_concerns[]` SHALL 为有序列表：`route_reason` 传入时提级原因块（`type=escalation`，`text` 原文照搬）固定置首，此为装配规则而非业务加工；风险项（`type=risk`）按传入数组顺序跟排，`risk_register` 全字段照搬并含「处置参考」`measure` 块（`measure_type`+`measure_desc` 原文）；缺字段的对应行 SHALL NOT 渲染、SHALL NOT 以占位文案填充。`opinion_details[]` SHALL 按传入顺序逐条输出 `node_name`/`approver_name`/`role`/`action` 骨架字段原文。`level`、`decision_type` 等展示值原样输出，不做枚举映射。

#### Scenario: 提级块置首与风险项跟排
- **WHEN** 请求同时传入 `route_reason` 与 2 条 `risk_register`
- **THEN** `key_concerns[0].type` SHALL 为 `escalation` 且 `text` 与输入逐字一致
- **AND** `key_concerns[1..2]` SHALL 按传入顺序输出两条 `risk` 块

#### Scenario: 风险项缺决策字段
- **WHEN** 某风险项未传 `decision_type`/`decision_by`/`decision_note`
- **THEN** 该风险块 SHALL NOT 输出决策状态相关内容
- **AND** `degraded_sections` SHALL NOT 因此标记降级（非降级场景）

### Requirement: AI 生成仅限总述与意见摘要两处
响应中 AI 生成文本 SHALL 只有两处：`review_summary.text`（一句话总述）与 `opinion_details[].summary`（压缩对应 `comment` 原文、保留其主张与条件）。其余全部字段 SHALL 为输入原文装配，零 AI 改写：`route_reason` 照搬、`risk_register` 全字段照搬、「处置参考」一律引用清单应对措施原文，AI 对动作、数字、条款与决策零生成，不输出「建议通过/建议驳回」类决策建议。总述 SHALL 将 `contract_meta` 已传固定信息原样融入自然语句（写"该合同为硬件集成合同"，不写"合同类型：硬件集成"），随后概括整体评审意见。

#### Scenario: 风险块内容零生成
- **WHEN** 请求包含带 `description`/`standard_clause`/`potential_impact`/`measure_desc` 的风险项
- **THEN** 输出的对应字段 SHALL 与输入逐字一致
- **AND** 系统 SHALL NOT 生成或改写任何应对措施或决策文本

### Requirement: 防幻觉五条铁律
系统 SHALL 在服务端强制以下规则，而非仅依赖 Prompt：
1. **数字零生成**：金额、比例、期限等一律原文引用，不解析、不换算、不四舍五入、不润色；
2. **事实单点归属**：两处 AI 生成文本只做话题级引用，不重复展开装配区已有的数字、条款与影响；约束对象是事实而非观点，意见摘要照写人的主张；
3. **source_refs 溯源**：每条 AI 结论 SHALL 携带指向输入字段路径的来源引用；服务端校验，无引用或引用悬空（指向不存在的输入路径）的结论 SHALL 直接丢弃，丢弃 SHALL NOT 阻塞装配区返回；总述被丢弃时 `review_summary.text=null`，意见摘要被丢弃时该条 `summary=null`，并分别在 `degraded_sections` 以 `review_summary.model`/`opinion_details.model` 标记；
4. **总述形容词铁律**：评价性修饰必须可溯源到输入字段原文，溯源不到只说事实；CRM 字段暂缓接入期间总述不写客户评价；
5. **总述与结论分布一致性**：`opinions` 中存在 `action=reject` 时，总述 SHALL 退化为中性陈述（只列事实+"评审意见存在分歧"类客观描述），SHALL NOT 出现"整体认可""一致看好"等正面定性。

#### Scenario: 悬空引用的总述被丢弃
- **WHEN** 模型返回的总述 `source_refs` 指向输入中不存在的路径
- **THEN** 系统 SHALL 丢弃该总述，输出 `review_summary.text=null`
- **AND** `degraded_sections` SHALL 包含 `review_summary.model`
- **AND** `key_concerns` 与 `opinion_details` 装配内容 SHALL 正常返回

#### Scenario: 存在不通过意见时总述中性化
- **WHEN** `opinions` 中存在 `action=reject` 的意见
- **THEN** 总述 SHALL NOT 包含正面定性表述
- **AND** 总述 SHALL 仅为事实列举与分歧的客观陈述

### Requirement: 空态矩阵与降级标记
系统 SHALL 按设计文档 §5.1 空态矩阵实现全部空态：`risk_register=[]` 且无 `route_reason` 时重点关注为空并标记 `key_concerns`；仅 `route_reason` 缺、`contract_meta` 部分字段缺、风险项缺 `measure_*` 或缺 `decision_*` 均 SHALL NOT 标记降级；`opinions=[]` 时总述降级为纯事实句、意见详情为空并标记 `opinion_details` 与 `review_summary.opinions`。`degraded_sections[]` SHALL 只含降级模块名，正常请求为空数组。模型调用失败 SHALL 走统一错误码体系：重试耗尽 `20001`、超时 `20002`、格式异常 `20003`，不新增错误码。

#### Scenario: 无风险无提级
- **WHEN** `risk_register=[]` 且未传 `route_reason`
- **THEN** `key_concerns` SHALL 为空数组
- **AND** `degraded_sections` SHALL 包含 `key_concerns`

#### Scenario: 评审意见为空集
- **WHEN** `opinions=[]`
- **THEN** `opinion_details` SHALL 为空数组
- **AND** `degraded_sections` SHALL 包含 `opinion_details` 与 `review_summary.opinions`
- **AND** 总述 SHALL 为不含评审意见概括的纯事实句

#### Scenario: 模型重试耗尽
- **WHEN** 模型调用失败且业务层重试后仍失败
- **THEN** 系统 SHALL 返回 `code=20001`
- **AND** 响应 SHALL NOT 携带部分生成的 `data`

### Requirement: 输入 hash 缓存与模型调用口径
系统 SHALL 对规范化后的请求体计算内容哈希作为缓存键，命中时直接返回既有整包响应；`opinions`/`risk_register` 任何新增变更 SHALL 自动失效缓存，无需合同系统通知。模型调用 SHALL 与现行能力共用 `get_chat_model()` 单例且只消费 `bind()` 返回的新对象，SHALL NOT 修改 `app/models/llm.py`；关闭思考 SHALL 走 `model.bind(extra_body={"chat_template_kwargs": {"enable_thinking": False}})`；SDK 层 `max_retries=0`，业务层仅解析失败重试 1 次。

#### Scenario: 相同输入命中缓存
- **WHEN** 两个逐字段相同的请求先后到达
- **THEN** 第二次请求 SHALL NOT 发起模型调用
- **AND** 两次响应 `data` SHALL 一致

#### Scenario: 意见变更自动失效
- **WHEN** 后续请求在某条 `opinions[].comment` 上有任意改动
- **THEN** 缓存键 SHALL 不同并重新生成
- **AND** 系统 SHALL NOT 返回旧哈希对应的缓存结果

### Requirement: 对既有能力零改动
本能力 SHALL 以独立包 `app/capabilities/review_summary/` 实现，与 `contract_review`、`translate` 零依赖。除 `app/main.py` 新增 router 注册（import + `include_router` 共 2 行）外，SHALL NOT 修改任何既有代码文件；`app/core/` 全部文件、`app/capabilities/contract_review/**`（含 `two_stage/`）、`app/capabilities/translate/**`、`app/models/llm.py`、现有 prompts yaml、现有 config 键与现有测试文件（含 `conftest.py`）SHALL 保持原样。

#### Scenario: 既有接口行为不变
- **WHEN** 新能力注册后调用 `/api/v1/contract-review`（review 与 prefill 两模式）及 `/api/v1/translate`
- **THEN** 请求契约、响应结构与错误码 SHALL 与注册前完全一致

#### Scenario: 回归测试全绿
- **WHEN** 运行 `pytest tests/` 与 `pytest tests/two_stage/`
- **THEN** 现有用例 SHALL 全绿（基线 838 + 490，允许只增不减）
- **AND** 新增 `tests/test_review_summary_*.py` SHALL 全部通过
