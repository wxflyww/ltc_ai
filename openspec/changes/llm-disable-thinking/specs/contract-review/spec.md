# contract-review 规格变更

## ADDED Requirements

### Requirement: 模型调用关闭思考模式

系统 SHALL 在合同评审能力的模型调用中关闭思考模式：当配置开关 `llm.disable_thinking` 为真（默认）时，评审链路与预填链路的模型调用 SHALL 随请求体向模型透传 `enable_thinking=false`。该开关作用域 SHALL 限于合同评审能力自身的调用点，SHALL NOT 通过模型工厂的全局构造生效。

关闭思考模式 SHALL NOT 影响结构化输出、必填键校验与格式错重试的既有行为，三者 SHALL 同时成立。

系统 SHALL 提供配置开关（环境变量 `LTC__LLM__DISABLE_THINKING`，默认 `true`）。开关为假时，评审链路 SHALL 退回不携带该参数的调用形态，用于后端不支持 `chat_template_kwargs` 时的一键退避。

#### Scenario: 评审链路关闭思考模式

- WHEN 以 `mode=review` 调用组织评审接口并触发模型调用
- THEN 该次调用 SHALL 携带 `chat_template_kwargs.enable_thinking=false`
- AND 模型返回值 SHALL NOT 混入思考文本
- AND `data` 的键集合、字段类型与 `checks` / `metrics` 的结构 SHALL 与本变更前一致

#### Scenario: 预填链路关闭思考模式

- WHEN 以 `mode=prefill` 调用并触发模型调用
- THEN 该次调用 SHALL 携带 `chat_template_kwargs.enable_thinking=false`
- AND 预填 SHALL 仍携带结构化输出与必填键校验

#### Scenario: 关闭思考与结构化输出共存

- WHEN 一次模型调用同时要求关闭思考模式与结构化输出
- THEN 两者 SHALL 同时生效
- AND 系统 SHALL NOT 为其中一项而放弃另一项

#### Scenario: 后端不支持该参数时可退避

- WHEN 配置开关 `llm.disable_thinking` 为假
- THEN 评审链路与预填链路的模型调用 SHALL 不携带 `chat_template_kwargs.enable_thinking`
- AND 系统 SHALL 按本变更前的既有形态调用模型

#### Scenario: 两阶段链路不受影响

- WHEN 调用两阶段 prepare 链路并触发模型调用
- THEN 该次调用形态 SHALL 与本变更前逐项一致
- AND 系统 SHALL NOT 因本变更改动 `two_stage` 目录下的任何文件

#### Scenario: 评审链路除关思考外无其他变化

- WHEN 本变更生效后以 `mode=review` 调用组织评审接口
- THEN 系统 SHALL NOT 改动现有评审 prompt、响应模型、检查点逻辑与错误码体系
- AND 响应字段集合与类型 SHALL 与本变更前一致，差异 SHALL 仅限模型输出取值层面

#### Scenario: 翻译链路不受影响

- WHEN 调用文本翻译接口并触发模型调用
- THEN 该次调用 SHALL NOT 携带 `chat_template_kwargs.enable_thinking`
- AND 翻译链路的模型调用形态 SHALL 与本变更前逐项一致
