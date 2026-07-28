## Why

- B-1 检查技术协议时，模型将"吉利座舱中心""吉利"等部门、品牌或普通业务文本误判为甲方称谓，为每处出现生成一条 WARN，导致 checks 数组无限增长。
- 诊断 trace（tmp/llm-trace-audit/20260727-212950）证实：completion_tokens=4817、content_chars=13573、total_tokens=16384、finish_reason=length，根因是可见 JSON 中 checks 数组无边界扩张，而非 reasoning_content 膨胀。
- 当前 B-1/B-4 的 JSON Schema 中 checks 数组无 maxItems，字符串字段无 maxLength，模型在误判场景下持续生成结构化观察直至触发 LengthFinishReasonError。

## What Changes

- 在 B-1、B-4 的 structured-output JSON Schema 中，对 checks 添加 maxItems=3，将 result 枚举收紧为 WARN/FAIL。
- 对模型可生成的 evidence_quote、reason、found_appellation、baseline_appellation 等字段设置合理 maxLength。
- Prompt 同步要求最多 3 条、只输出 WARN/FAIL、按严重程度和证据强度排序、去重；B-1 明确排除部门、品牌、项目团队、产品、系统等非签约主体称谓。
- 服务端增加确定性防御：排序、去重后保留前 3 条，确保即使模型未严格执行 Schema 也不会无边界进入最终结果。
- 审计其他模型调用（A-1a、A-3、A-4、attachment_title_matching），确认不机械套用 maxItems=3。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `contract-review`: 为 B-1/B-4 审查发现项增加输出预算治理（Schema + Prompt + 服务端三层约束）。

## Impact

- 影响 `app/capabilities/contract_review/response_formats.py`、`prompts/contract_review.yaml`、`app/capabilities/contract_review/service.py` 和合同评审测试。
- B-1/B-4 每个检查范围最多输出 3 个不同且证据最强的问题；无问题时模型返回空 checks，服务端生成 PASS。
- 不影响提取类调用（A-1a、A-3、A-4）和逐项映射调用（attachment_title_matching）的现有行为。
