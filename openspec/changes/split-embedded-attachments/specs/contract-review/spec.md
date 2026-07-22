## ADDED Requirements

### Requirement: 从合同 Markdown 中拆分内嵌附件

系统 SHALL 在接收到合同 Markdown 后，识别合同正文中独立成行的内嵌附件标题，将对应附件内容拆分为独立附件文本，并从主合同正文中移除。

#### Scenario: 所有附件都内嵌在合同正文中

- 当合同 Markdown 包含 3 个内嵌附件段落时
- 且未提供上传附件时
- 则系统 SHALL 为后续检查创建 3 个附件文本
- 且主合同正文 SHALL 排除这些内嵌附件段落

#### Scenario: 不存在内嵌附件且存在上传附件

- 当合同 Markdown 不包含内嵌附件段落时
- 且提供 2 个上传附件时
- 则系统 SHALL 保留这 2 个上传附件供后续检查使用
- 且主合同正文 SHALL 保持不变

#### Scenario: 既有内嵌附件又有上传附件

- 当合同 Markdown 包含 1 个内嵌附件段落时
- 且提供 2 个上传附件时
- 则系统 SHALL 创建 1 个拆分出的附件文本
- 且将其与这 2 个上传附件合并
- 且后续检查 SHALL 接收到 3 个附件文本

#### Scenario: 内嵌附件从主合同正文中移除

- 当合同 Markdown 包含内嵌附件段落时
- 则系统 SHALL 在后续正文抽取前将该内嵌附件段落从主合同正文中移除
- 且拆分出的附件内容 SHALL 仍然保留在附件列表中

#### Scenario: 忽略非标题型附件引用

- 当合同 Markdown 中包含“详见附件一”或“附件一式三份”等行内引用文本时
- 则系统 SHALL 不将该行内文本拆分为内嵌附件

### Requirement: B-1 称谓一致性按正文和附件分段检查

系统 SHALL 在 B-1 称谓一致性检查中分别检查拆分后的合同正文和每个附件文本，不得将合同正文与全部附件重新拼接为一次模型输入。

#### Scenario: 合同正文和附件分别送入 B-1

- 当合同 Markdown 中拆分出 1 个内嵌附件
- 且请求中另有 1 个上传附件时
- 则系统 SHALL 对合同正文执行 1 次 B-1 检查
- 且系统 SHALL 对 2 个附件分别执行 B-1 检查
- 且每次 B-1 检查的输入 SHALL 只包含当前检查范围文本和签约方基准信息

#### Scenario: B-1 单个分段超过模型上下文

- 当 B-1 的合同正文或某个附件分段超过模型单次处理长度限制时
- 或模型返回 `tokens_limit_reached` 等上下文超长错误时
- 则系统 SHALL 在评审结果中返回一个 `FAIL` 且 `block_level` 为 `硬阻断` 的检查项
- 且该检查项 SHALL 返回给调用方用于阻断后续流程
- 且该检查项 reason SHALL 明确指出超长的检查范围
- 且评审结果 overall_result SHALL 为 `BLOCK`

#### Scenario: 模型输出达到长度上限

- 当模型调用返回 `LengthFinishReasonError` 或 `length limit was reached` 等输出截断错误时
- 则系统 SHALL 在评审结果中返回一个 `FAIL` 且 `block_level` 为 `硬阻断` 的检查项
- 且该检查项 id SHALL 为 `模型输出长度`
- 且该检查项 reason SHALL 明确提示“模型输出达到长度上限，结果被截断”
- 且系统 SHALL 不得将该错误误标为输入上下文超长

### Requirement: B-1 输出结果可追溯且去重

系统 SHALL 为 B-1 每条结果提供分段可追溯信息，并避免重复语义告警干扰调用方。

#### Scenario: B-1 结果携带检查范围

- 当系统完成任一 B-1 分段检查时
- 则该分段输出项 name SHALL 包含分段范围信息（如 `称谓一致性-合同正文`、`称谓一致性-附件1...`）
- 且该分段输出项 reason SHALL 包含范围前缀（如 `【范围】合同正文`）

#### Scenario: B-1 重复与噪声告警过滤

- 当同一分段中出现语义重复的 B-1 告警时
- 则系统 SHALL 在输出前进行去重，避免重复记录
- 且当告警内容不属于称谓一致性问题时，系统 SHALL 过滤该噪声告警

### Requirement: 模型调用异常审计可区分长度问题类型

系统 SHALL 在 LLM 审计事件中记录调用异常，并标注长度问题类型，便于排查输入超限与输出截断。

#### Scenario: 审计记录调用异常与长度分类

- 当任一模型调用抛出异常时
- 则系统 SHALL 记录模型调用异常审计事件
- 且当异常属于长度问题时，审计事件 SHALL 包含 `length_issue=input|output` 分类信息

### Requirement: 合同组织评审输出模型调用统计

系统 SHALL 在合同组织评审响应 data 中输出 metrics 字段，用于展示各模型调用步骤的耗时和 token 消耗。

#### Scenario: 响应包含步骤级 metrics

- 当合同组织评审成功返回时
- 则 data.metrics SHALL 包含每个模型调用步骤的 id、name、duration_seconds 和 token_usage
- 且 token_usage SHALL 包含 prompt_tokens、completion_tokens 和 total_tokens

#### Scenario: B-1 输出分段 metrics

- 当 B-1 按合同正文和附件分段检查时
- 则 data.metrics 中 B-1 统计项 SHALL 汇总所有 B-1 分段的耗时和 token
- 且 B-1 统计项 SHALL 在 segments 中保留每个分段的耗时和 token
