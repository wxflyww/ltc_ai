## Why

- B-4 当前没有收到 A-3 提取出的合同正文总价和原文证据，模型会自行推断“合同正文约定的最终含税总价”，导致金额来源不可追溯，甚至产生虚假硬阻断。
- B-4 直接保留模型给出的 `block_level`，使 `PASS` 与“硬阻断”等互相矛盾的结果进入对外响应。

## What Changes

- A-3 在提取合同总价时同时返回能证明该总价的合同正文原文短句。
- B-4 仅以服务端验证过的 A-3 总价及原文证据作为附件金额比对基准；附件金额不一致必须提供当前附件内的原文证据。
- B-4 对金额观察进行服务端校验：缺少正文基准、正文证据、附件证据或数值不匹配时，不生成金额不一致结论。
- B-4 的 `block_level` 由最终 `result` 统一推导，确保 `PASS/通过`、`WARN/提示`、`FAIL/硬阻断`、`NA/不适用` 成对输出。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `contract-review`: 修改 A-3 到 B-4 的金额基准传递、B-4 金额证据校验和 B-4 阻断级别归一规则。

## Impact

- 影响 `prompts/contract_review.yaml`、`app/capabilities/contract_review/response_formats.py`、`app/capabilities/contract_review/service.py` 和合同评审服务测试。
- B-4 金额不一致的 `reason` 改为可追溯的正文和附件引文；无有效证据的推测性金额告警将被抑制。
