## ADDED Requirements

### Requirement: ReviewContext 基础信封
系统 SHALL 提供版本化的 `ReviewContext` 领域模型，至少包含 `schema_version`、`source_snapshot`、`shared_facts`、`evidence_index`、`preparation_issues`、`preparation_meta` 和 `context_digest`。该模型 SHALL 可序列化为不包含值为 `null` 的可选字段的 JSON payload。

#### Scenario: 构造完整上下文
- **WHEN** 调用方提供合法的来源快照、公共事实、证据索引、准备元数据和摘要
- **THEN** 系统 SHALL 构造 `ReviewContext`
- **AND** 序列化 payload SHALL 保留 `schema_version=review-context/v1`
- **AND** 未提供的 `source_file_sha256` 和 `parser_meta` SHALL 被省略而不是输出 `null`

### Requirement: 文档来源快照使用明确身份
系统 SHALL 将主文档固定表示为 `document_key=main`，并以 `source_kind` 判别联合分别表示上传附件和正文内嵌附件。上传附件 SHALL 要求 `attachment_id` 和 `filename`；内嵌附件 SHALL 要求 `source_main_document_id`、`source_locator` 和 `title`。同一来源快照中的 `document_key` SHALL 唯一。

#### Scenario: 上传附件和内嵌附件共存
- **WHEN** 来源快照同时包含一个 `UPLOADED` 附件和一个 `EMBEDDED` 附件
- **THEN** 系统 SHALL 按各自类型校验不同的必填身份字段
- **AND** 不要求内嵌附件虚构 `attachment_id`
- **AND** 不要求上传附件虚构 `source_locator`

#### Scenario: 文档键重复
- **WHEN** 两个附件具有相同 `document_key` 或附件使用主文档键 `main`
- **THEN** 系统 SHALL 拒绝该来源快照

#### Scenario: 内嵌附件指向其他主文档
- **WHEN** 内嵌附件的 `source_main_document_id` 与当前快照主文档的 `document_id` 不一致
- **THEN** 系统 SHALL 拒绝该来源快照

### Requirement: 公共事实状态表达完整性
每个公共事实域 SHALL 使用 `COMPLETE`、`PARTIAL` 或 `UNAVAILABLE` 表达准备状态。`PARTIAL` 和 `UNAVAILABLE` SHALL 至少包含一条 `issues` 说明缺口；`COMPLETE` SHALL 不包含缺口说明。

#### Scenario: 部分事实缺少问题说明
- **WHEN** 事实域状态为 `PARTIAL` 且 `issues` 为空
- **THEN** 系统 SHALL 拒绝该事实域

#### Scenario: 不可用事实带有原因
- **WHEN** 事实域状态为 `UNAVAILABLE` 且包含缺口原因
- **THEN** 系统 SHALL 保留该状态和原因，不得静默转换为完整或通过状态

#### Scenario: 事实数据仅接受标准 JSON 值
- **WHEN** `FactDomain.data` 的递归值包含 Python 对象、集合、NaN 或 Infinity
- **THEN** 系统 SHALL 拒绝该事实域
- **AND** 合法 JSON 中的显式 `null` SHALL 被保留

### Requirement: 证据引用可追溯到来源
证据索引中的每条证据 SHALL 至少包含 `document_key`、`source_locator` 和原文 `quote`，并可携带结构化 `attributes`。基础证据索引 SHALL 分别容纳签约方、签署人、金额和附件关系证据。

#### Scenario: 证据缺少来源定位
- **WHEN** 任一证据缺少 `document_key`、`source_locator` 或原文引文
- **THEN** 系统 SHALL 拒绝该证据记录

#### Scenario: 证据指向当前快照之外的文档
- **WHEN** 任一证据的 `document_key` 不存在于当前 `source_snapshot` 的主文档或附件中
- **THEN** 上下文校验 SHALL 抛出 `ContextIntegrityError`

#### Scenario: 证据属性仅接受标准 JSON 值
- **WHEN** `EvidenceRef.attributes` 的递归值包含 Python 对象、集合、NaN 或 Infinity
- **THEN** 系统 SHALL 拒绝该证据记录

### Requirement: Markdown 内容摘要算法确定
系统 SHALL 对实际收到的 Markdown 执行固定规范化后计算 `parsed_content_sha256`：仅移除开头 BOM、执行 Unicode NFC、将 CRLF 和 CR 转换为 LF，并保留其他字符。结果 SHALL 为 `sha256:` 加 64 位小写十六进制。

#### Scenario: 等价换行和 Unicode 形式产生相同摘要
- **WHEN** 两个 Markdown 仅在 BOM、CRLF/CR/LF 或 Unicode 组合形式上不同
- **THEN** 系统 SHALL 生成相同的 `parsed_content_sha256`

#### Scenario: 空格或 Markdown 标记变化
- **WHEN** Markdown 的空格、空行或标记发生变化
- **THEN** 系统 SHALL 不删除这些差异
- **AND** 摘要 SHALL 随规范化后内容变化

### Requirement: 文档集合摘要稳定
系统 SHALL 以主文档固定第一、附件按 `document_key` 排序的稳定清单计算 `document_set_hash`。每项 SHALL 只包含 `document_key`、规范化名称和 `parsed_content_sha256`；上传文档使用文件名，内嵌附件使用标题。名称规范化 SHALL 移除路径、执行 Unicode NFC 和首尾空白清理，同时保留大小写、扩展名和标点。

#### Scenario: 附件输入顺序不同
- **WHEN** 两个来源快照包含相同主文档和附件，但附件数组顺序不同
- **THEN** 系统 SHALL 生成相同的 `document_set_hash`

#### Scenario: 来源快照组装前计算摘要
- **WHEN** prepare 已形成主文档模型和附件模型但尚未组装 `SourceSnapshot`
- **THEN** 系统 SHALL 能够直接根据这些文档模型计算 `document_set_hash`
- **AND** 不得要求调用方先填入虚假摘要占位值

#### Scenario: 文档身份或内容摘要变化
- **WHEN** 任一 `document_key`、规范化名称或 `parsed_content_sha256` 变化
- **THEN** 系统 SHALL 生成不同的 `document_set_hash`

### Requirement: ReviewContext 摘要和版本校验
系统 SHALL 使用确定性 JSON 对排除 `context_digest` 自身后的完整上下文计算摘要，并在正式消费前校验 Schema、文档集合摘要、上下文摘要和外层合同版本。

#### Scenario: JSON 键顺序不同
- **WHEN** 两个上下文的 JSON 对象键顺序不同但字段和值相同
- **THEN** 系统 SHALL 计算相同的 `context_digest`

#### Scenario: 模型和 JSON 映射使用同一摘要语义
- **WHEN** 同一完整上下文分别以 `ReviewContext` 对象和 JSON 映射传入摘要函数
- **THEN** 系统 SHALL 计算相同的 `context_digest`
- **AND** 动态 JSON 中的显式 `null` SHALL 与字段缺失产生不同摘要

#### Scenario: 上下文被修改
- **WHEN** 上下文任一受摘要保护的字段在生成摘要后被修改
- **THEN** 校验 SHALL 抛出 `ContextIntegrityError`

#### Scenario: 不支持的 Schema
- **WHEN** `schema_version` 不是 `review-context/v1`
- **THEN** 校验 SHALL 抛出 `ContextSchemaUnsupportedError`

#### Scenario: 合同版本不一致
- **WHEN** 外层 `contract_id` 或 `revision_id` 与 `source_snapshot` 不一致
- **THEN** 校验 SHALL 抛出 `DocumentRevisionMismatchError`

### Requirement: 基础模块不改变旧流程
本基础变更 SHALL 保持无状态且不注册新 API，不得调用旧合同评审流水线、LLM 或签署地预设值服务。

#### Scenario: 导入基础模块
- **WHEN** 应用或测试导入两阶段基础模块
- **THEN** 系统 SHALL 只加载领域模型和纯函数
- **AND** 现有 `/api/v1/contract-review` 和 `/api/v1/contract-review/upload-md` 行为 SHALL 保持不变
