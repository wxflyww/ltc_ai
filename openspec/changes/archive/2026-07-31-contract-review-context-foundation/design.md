## Context

当前 `POST /api/v1/contract-review` 在一次请求中完成 Markdown 拆分、模型提取、预设查询、业务判断和结果汇总。旧请求没有合同版本、稳定文档身份和上下文摘要，不能作为两阶段 prepare/evaluate 之间的数据契约。

本变更是四个升级变更中的第一个，只建立纯领域基础。合同系统仍负责 Markdown 和未来 `ReviewContext` 的持久化；本项目保持无业务数据库。旧流水线仅作回归基线，新模块不得导入或调用旧 `service.py`。

## Goals / Non-Goals

**Goals:**

- 建立版本化、可序列化、可追溯的 `ReviewContext` 基础模型。
- 区分上传附件与正文内嵌附件的不同身份字段。
- 固化跨平台可复现的文本、文件名和 JSON 规范化算法。
- 能够发现不支持的 Schema、摘要被修改、文档集合被修改及合同版本不一致。
- 为后续 prepare/evaluate 变更提供稳定且无副作用的复用模块。

**Non-Goals:**

- 不新增 `/prepare` 或 `/evaluate` 路由。
- 不提取真实合同事实，不调用模型、预设值接口或旧流水线。
- 不实现附件重复判定；本变更只提供后续判定需要的稳定身份和内容摘要。
- 不定义各检查点的最终事实字段和判断规则。
- 不迁移附件金额候选检查，不修改任何旧流程已知偏差。

## Decisions

### 1. 公共信封强类型，事实内容渐进细化

`ReviewContext` 的版本、来源快照、事实域状态、证据定位、准备元数据和摘要采用 Pydantic 强类型。`FactDomain.data` 暂时只约束为 JSON 对象或数组，`EvidenceRef.attributes` 暂时为 JSON 对象；其递归值只允许标准 JSON 类型和有限数值，保留业务数据中的显式 `null`，拒绝 Python 对象、集合、NaN 和 Infinity。后续 prepare 变更根据全检查点迁移矩阵细化各领域结构。

这样能够先稳定跨阶段信封，又不会在尚未设计全部检查点事实时制造大量投机字段。备选方案是本次一次性定义所有检查点事实模型，但会把后续三个变更的业务设计提前塞入基础变更，范围过大。

### 2. 上传附件和内嵌附件使用判别联合

`UploadedAttachmentSnapshot` 固定 `source_kind=UPLOADED` 并要求 `attachment_id`、`filename`；`EmbeddedAttachmentSnapshot` 固定 `source_kind=EMBEDDED` 并要求 `source_main_document_id`、`source_locator`、`title`。Pydantic 以 `source_kind` 判别，禁止用互相可空的字段表达两种来源。

`document_key` 在单个 `source_snapshot` 内必须唯一，且不得与主文档固定键 `main` 冲突；内嵌附件的 `source_main_document_id` 必须等于当前主文档 `document_id`。本变更不强制从业务 ID 反推 `document_key`，生成规则由 prepare 变更负责。

### 3. 摘要算法完全确定性

Markdown 规范化依次执行：移除字符串开头 BOM、Unicode NFC、CRLF/CR 转 LF；保留空格、空行和 Markdown 标记。摘要统一为 `sha256:` 加 64 位小写十六进制。

用于文档集合摘要的文件名规范化仅移除路径、执行 Unicode NFC 并去掉首尾空白，保留大小写、扩展名和标点，避免把合法不同文件过度合并。主文档固定排第一，附件按 `document_key` 排序；内嵌附件以 `title` 作为文件名槽位。

确定性 JSON 使用 UTF-8、键排序、紧凑分隔符、保留 Unicode 字符并拒绝 NaN。`context_digest` 对排除自身后的完整上下文计算；Schema 声明的可选空字段在摘要和对外 payload 中省略，动态 JSON 数据中的显式 `null` 保留。完整 JSON 映射必须先规范化为 `ReviewContext`，保证对象和映射使用同一摘要路径。

`compute_document_set_hash` 既接受完整 `SourceSnapshot`，也接受尚未组装快照的主文档模型和附件列表，避免 prepare 首次生成摘要时填入虚假占位值。

### 4. 模型校验与跨字段完整性校验分离

Pydantic 模型负责字段类型、SHA-256 格式、事实状态和附件联合类型。`validate_review_context` 负责运行期跨字段检查：

- `schema_version` 必须是 `review-context/v1`；
- 重算的 `document_set_hash` 必须一致；
- 重算的 `context_digest` 必须一致；
- 每条证据的 `document_key` 必须存在于当前来源快照；
- 调用方提供合同时，外层 `contract_id/revision_id` 必须与快照一致。

失败分别抛出 `ContextSchemaUnsupportedError`、`ContextIntegrityError` 和 `DocumentRevisionMismatchError`。本变更不映射现有 HTTP 错误码，映射由 evaluate API 变更定义。

### 5. 新旧路径物理隔离

新模块只依赖标准库和 Pydantic，不导入旧 `router.py`、`service.py`、Prompt 或模型适配层。`pyproject.toml` 仅增加新子包，不注册路由。测试放在 `tests/two_stage/`，旧测试期望保持不变。

## Risks / Trade-offs

- [事实 `data` 暂未完全强类型] → 后续 prepare 变更必须依据全检查点迁移矩阵细化，不能长期保留任意 JSON。
- [文件名规范化规则以后变化会改变 `document_set_hash`] → 将其作为契约测试固化；语义变化时升级 `schema_version` 或流水线版本。
- [摘要只能发现意外变化，不能提供身份认证] → 明确不把 SHA-256 描述成签名或加密；传输鉴权沿用系统安全边界。
- [旧流程与新规则结果不同] → 旧流程只作已知回归基线，新模块不调用旧规则。

## Migration Plan

1. 合并本基础模块时不注册任何 API，因此部署后外部行为不变。
2. 后续 `contract-review-prepare-api` 复用模型和哈希函数生成上下文。
3. 后续 `contract-review-evaluate-api` 在业务检查前调用统一校验函数。
4. 若本变更需要回退，只需移除未被生产路由引用的新子包和测试，不影响旧接口。

## Open Questions

无阻塞问题。事实域内部字段、prepare 请求去重和 evaluate 对外错误码分别留给后续对应 OpenSpec。
