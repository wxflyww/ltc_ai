## ADDED Requirements

### Requirement: B-4 金额基准可追溯

系统 SHALL 仅以 A-3 从合同正文提取且经服务端验证的总价数值和对应正文原文作为 B-4 附件金额比对基准。B-4 金额不一致结论 SHALL 同时包含该正文原文和当前附件原文证据。

#### Scenario: 已验证的附件总价不一致

- **WHEN** A-3 的总价数值及含该数值的正文证据均存在于合同正文，且当前附件包含不同的总价和含该数值的当前附件证据
- **THEN** 系统 SHALL 输出 B-4 `FAIL`，并在 `reason` 中引用正文基准数值、正文证据、附件数值和附件证据

#### Scenario: 缺少可验证的正文或附件金额证据

- **WHEN** A-3 总价缺少正文证据、正文证据不属于合同正文、附件证据不属于当前附件，或证据未包含所述金额
- **THEN** 系统 SHALL 不输出该金额不一致结论，不得以推测的“合同正文总价”形成 B-4 硬阻断

### Requirement: B-4 结果与阻断级别一致

系统 SHALL 根据 B-4 的最终 `result` 设置 `block_level`，不得保留模型提供的矛盾级别。

#### Scenario: B-4 通过项的模型级别矛盾

- **WHEN** B-4 模型输出 `result=PASS` 和 `block_level=硬阻断`
- **THEN** 系统 SHALL 输出 `result=PASS` 和 `block_level=通过`

#### Scenario: B-4 金额不一致的模型级别缺失或矛盾

- **WHEN** B-4 金额观察被服务端验证为 `FAIL`，但模型级别缺失或不是“硬阻断”
- **THEN** 系统 SHALL 输出 `block_level=硬阻断`
