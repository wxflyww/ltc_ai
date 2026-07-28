## Why

合同正文声明的附件标题通常是纯标题，而上传文件名常包含附件编号、扩展名、版本号或项目上下文。当前实现直接比较完整文件名与声明标题，容易把同一附件误判为标题未匹配；仅靠字符串规则又无法安全判断语义修饰是否改变文件性质。

## What Changes

- 对附件标题先执行最小、确定性的格式规范化；规范化后唯一完全相同的标题直接匹配。
- 对仍未匹配的正文声明附件和上传附件，调用现有私有化模型批量判断名称对应关系。
- 只接受后端校验通过的一对一 `MATCH` 映射；模型返回 `UNCERTAIN` 或无效映射时保留提示，不强行建立关联。
- 保持附件数量不足时的硬阻断，以及未匹配附件仍进入 B-4 检查的既有行为。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `contract-review`: 修改附件数量和标题一致性检查的标题关联规则及不确定结果的提示语义。

## Impact

- `app/capabilities/contract_review/attachments.py`：标题规范化、候选构造和模型映射校验。
- `app/capabilities/contract_review/service.py`：仅在存在未匹配候选时调用附件标题匹配提示词。
- `prompts/contract_review.yaml` 与 `app/capabilities/contract_review/response_formats.py`：新增私有化模型的结构化输出契约。
- `tests/test_contract_review_attachments.py`、`tests/test_contract_review_service.py` 与提示词测试：补充回归覆盖。