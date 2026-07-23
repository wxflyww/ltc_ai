## ADDED Requirements

### Requirement: B-1 reason 范围前缀使用自然语言

系统 SHALL 在称谓一致性（B-1）输出中使用自然语言前缀描述检查范围，而不是标签式 `【范围】` 前缀。

#### Scenario: 合同正文范围前缀

- **WHEN** B-1 输出合同正文的检查结果
- **THEN** `reason` SHALL 以 `合同正文中：` 开头

#### Scenario: 附件范围前缀

- **WHEN** B-1 输出附件分段的检查结果
- **THEN** `reason` SHALL 以 `<附件范围>中：` 开头

#### Scenario: 兼容旧格式输出

- **WHEN** 模型返回旧格式 `【范围】<scope>...`
- **THEN** 后端 SHALL 规范化为 `<scope>中：...` 再返回给调用方

#### Scenario: reason 去标签化

- **WHEN** B-1 输出 reason
- **THEN** reason SHALL 不包含 `【基准称谓】`、`【发现称谓】`、`【证据】` 等标签式片段

#### Scenario: reason 长度限制

- **WHEN** B-1 生成较长 reason
- **THEN** 后端 SHALL 将 reason 限制在 160 字以内

#### Scenario: 泛化指代词噪声过滤

- **WHEN** 发现称谓为“本合同/本协议/本项目/双方/本条/上述”等泛化指代词
- **THEN** 系统 SHALL 不将该项输出为 WARN/FAIL
