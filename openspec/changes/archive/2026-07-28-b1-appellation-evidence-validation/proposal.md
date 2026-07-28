## Why

- B-1 当前将合同名称、项目名称、正文和附件背景引用与签约主体称谓一并判断，导致角色混淆、跨范围取证和无效告警。
- 需要将合同首部明确的甲乙方定义及其明确简称作为唯一基准，并让每条告警具有可验证的当前范围证据。

## What Changes

- A-1a 只从合同首部明确的甲乙方定义中提取签约方及明确简称；合同名称、项目名称及背景文本不得作为来源。
- B-1 模型输出改为包含角色、基准、发现称谓、证据片段和证据类型的结构化观察结果；服务端只对可验证观察生成告警。
- B-1 忽略合同/项目名称和背景或历史项目引用；附件出现“甲方”或“乙方”但未在附件内明确对应主体时返回 `WARN`；附件内已定义主体时与正文同角色主体及明确简称比对。
- B-1 的 `PASS` 不生成空的范围前缀；告警证据统一采用 `证据“原文”。` 格式。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `contract-review`: 修改 B-1 称谓一致性的基准、证据校验与附件角色简称处理规则。

## Impact

- 影响 `prompts/contract_review.yaml`、`app/capabilities/contract_review/schemas.py`、`app/capabilities/contract_review/response_formats.py`、`app/capabilities/contract_review/service.py` 和合同评审测试。
- `checks[].reason` 的生成方式变化，但字段和既有 `WARN`/`PASS` 结果语义保持兼容。
