## Why

旧合同评审流水线无法证明检查结果对应哪一个不可变文档集合，也没有可复用的事实、证据和摘要契约。两阶段升级需要先建立独立、可验证的 `ReviewContext` 基础，后续 prepare 和 evaluate 才能在不复用旧请求状态的前提下分别演进。

## What Changes

- 在 `app/capabilities/contract_review/two_stage/` 新增与旧流水线隔离的 `ReviewContext` 领域模型。
- 定义主文档、上传附件和正文内嵌附件三类来源快照，其中两类附件使用明确的联合类型，不用一组可空字段混合表达。
- 定义公共事实域状态、证据索引、准备问题和准备元数据的基础结构；具体检查点事实字段留给后续 prepare 变更细化。
- 固化 Markdown 规范化、`parsed_content_sha256`、`document_set_hash`、确定性 JSON 和 `context_digest` 算法。
- 提供上下文 Schema、摘要、文档集合和合同版本一致性校验，使用内部领域异常表达失败原因。
- 更新 Python 打包清单并增加独立的两阶段契约测试，不修改旧接口、旧流水线或旧测试期望。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `contract-review`：新增两阶段 `ReviewContext` 基础数据契约、确定性摘要和一致性校验要求，不改变现有评审接口行为。

## Impact

- 新增代码：`app/capabilities/contract_review/two_stage/` 下的 Schema、哈希和校验模块。
- 新增测试：`tests/two_stage/`，与旧合同评审测试分开组织。
- 修改打包配置：`pyproject.toml` 显式包含新子包。
- 本变更不新增 API、不调用 LLM 或签署地预设值服务、不持久化业务数据，也不切换生产调用。
