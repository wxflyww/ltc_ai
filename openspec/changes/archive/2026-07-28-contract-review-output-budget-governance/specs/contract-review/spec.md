# contract-review 规格说明（变更增量）

## ADDED Requirements

### Requirement: B-1/B-4 审查发现项输出预算

系统 SHALL 对 B-1 称谓一致性和 B-4 附件内容一致性的模型输出实施三层预算约束。

#### Scenario: 每个检查范围最多输出 3 个发现项

- WHEN 模型对单个检查范围返回超过 3 条 WARN/FAIL 观察
- THEN 系统 SHALL 按 FAIL 优先于 WARN 排序
- AND 去重后保留前 3 条
- AND 丢弃第 4 条及以后

#### Scenario: 无问题时模型返回空 checks

- WHEN 检查范围内未发现称谓不一致或附件内容不一致
- THEN 模型 SHALL 返回 `{"checks": []}`
- AND 服务端 SHALL 生成一个 PASS 检查项，reason 为 null

#### Scenario: 只输出 WARN/FAIL

- WHEN 模型生成 B-1/B-4 结构化输出
- THEN checks 数组中 SHALL 只包含 result 为 WARN 或 FAIL 的项
- AND PASS 由服务端在空 checks 时统一生成

#### Scenario: 部门/品牌/项目团队/产品/系统不触发 B-1

- WHEN 文本中出现包含签约主体名称片段的部门、业务中心、品牌、项目团队、产品、系统、车型或项目名称
- AND 该名称未被用来指代承担合同权利义务的签约方
- THEN 系统 SHALL 不输出称谓不一致 WARN/FAIL

#### Scenario: 重复发现不占用名额

- WHEN 模型输出多条相同问题或相同证据的观察
- THEN 系统 SHALL 去重后只保留首条
- AND 去重不得减少不同问题的名额

#### Scenario: 提取类和映射类调用不受 checks 限制影响

- WHEN 执行 A-1a、A-3、A-4 提取或 attachment_title_matching 映射
- THEN 系统 SHALL 保持现有行为
- AND 不对提取数组设置 maxItems=3
- AND attachment_title_matching 仍为每个 uploaded_id 返回 decision
