## Why

已归档的 `contract-review-context-foundation` 只提供可校验的 `ReviewContext` 基础信封，尚无调用方可用的材料准备接口，也未将六个事实域收敛为强类型数据契约。两阶段升级必须先让合同系统能够基于当前完整 Markdown 快照生成、保存并审计一份不含正式裁决的 `ReviewContext`，后续 Evaluate 才能只依赖该上下文稳定执行。

## What Changes

- 新增 JSON-only 的 `POST /api/v1/contract-review/prepare`，接收主合同和当前版本全部有效上传附件的完整 Markdown 快照，返回完整 `ReviewContext` 数据体。
- 将 `shared_facts` 固定为 `header`、`parties`、`signature`、`amount_payment`、`copy_terms` 和 `attachment_manifest` 六个强类型事实域，并统一字段状态、逐文档覆盖、结构化准备问题和稳定引用键。
- 将基础版分类证据容器收敛为具有全局唯一 `evidence_id` 的统一证据注册表；所有事实只通过 `evidence_ids` 引用经后端定位验证的原文证据。
- 在任何模型调用前完成输入校验、Markdown 摘要、内嵌附件识别和单次请求明确重复附件拒绝；疑似重复保留并形成准备问题，不静默合并。
- 建立独立的 Prepare 编排、强类型模型输出、确定性规范化、证据装配、覆盖聚合、稳定排序和 `context_digest` 生成流程，不调用或混用旧 `run_review_pipeline`。
- 对可靠识别为需求说明书、技术规范书、工作说明书、质量标准四类之一的标准附件，首期只做完整清单处理和全文确定性安全扫描；扫描命中相关事实候选时仅展开可定位局部范围，未命中时不做全文 LLM 语义展开。目录外或类型/边界不可靠的附件继续执行普通完整提取，不允许运行时自动学习或仅凭文件名/宽泛关键词扩充目录。
- 明确技术/模型/Schema/装配失败使整个请求失败；`PARTIAL/UNAVAILABLE` 只表达可定位的来源提取或证据覆盖不足，Prepare 不输出 `PASS/WARN/FAIL`、不读取签署地预设主数据、不持久化业务数据。
- 保持现有 `/api/v1/contract-review` 和 `/api/v1/contract-review/upload-md` 的请求、结果及测试期望不变。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `contract-review`：增加第一阶段材料准备 API、六个强类型事实域、统一证据与覆盖契约，以及输入重复控制和失败语义；不改变旧评审入口的现有行为。

## Impact

- API：新增 `/api/v1/contract-review/prepare` 的请求、成功数据体和错误映射；继续使用项目统一响应壳、鉴权、Trace 和耗时字段。
- 代码：扩展 `app/capabilities/contract_review/two_stage/` 的 Schema、领域校验、准备编排、模型提取和路由注册；复用现有模型适配层但不复用旧评审流水线。
- 配置与 Prompt：新增 Prepare 专用 Prompt/输出 Schema 及可审计的 `pipeline_version`、`prompt_bundle_hash` 和模型部署标记；不新增规则数据库或持久化组件。
- 测试：在 `tests/two_stage/` 增加 API 契约、六域结构、证据/覆盖、重复附件、失败路径和确定性测试，并运行受影响的旧合同评审回归。
- 调用方：合同系统负责仅在“已全部上传”且全部有效文档解析完成后发送完整快照，并保存返回的不可变 `ReviewContext`；同一文件快照因 Prepare 兼容升级可自动重新准备。
