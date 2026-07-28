# contract-review 规格说明

## Purpose

在组织评审阶段，对销售上传的合同 Markdown 正文及附件 Markdown 内容，根据检查点进行自动检查，输出硬阻断项和提示项。
## Requirements
### Requirement: Markdown 合同组织评审接口

系统 SHALL 提供合同组织评审接口，接收解析后的合同 Markdown 正文和附件 Markdown 文本。

#### Scenario: JSON 请求评审

- WHEN 调用 `POST /api/v1/contract-review`
- AND 请求体包含 `contract_md` 和 `attachments`
- THEN 系统 SHALL 返回统一响应壳
- AND `data.checks` SHALL 包含所有检查结果

#### Scenario: Markdown 文件上传评审

- WHEN 调用 `POST /api/v1/contract-review/upload-md`
- AND 上传合同 Markdown 文件及可选附件 Markdown 文件
- THEN 系统 SHALL 复用合同组织评审流程

### Requirement: 序号1 合同首页完整性

系统 SHALL 检查合同首页中的合同名称、合同编号、签订地点、签订日期和我方签署主体。

#### Scenario: 合同名称缺失

- WHEN 合同名称缺失
- AND 首页不存在可作为合同名称兜底的项目名称
- THEN 系统 SHALL 输出序号1 FAIL

#### Scenario: 合同标题为泛化标题但存在项目名称

- WHEN 合同名称为“合同”等泛化标题
- AND 首页存在项目名称
- THEN 系统 SHALL 不因合同名称缺失输出 FAIL

#### Scenario: 合同编号缺失且无项目编号

- WHEN 合同编号为空
- AND 项目编号为空
- THEN 系统 SHALL 输出序号1 WARN，提示合同编号缺失

#### Scenario: 合同编号缺失但存在项目编号

- WHEN 合同编号为空
- AND 项目编号存在
- THEN 系统 SHALL 输出序号1 WARN，提示合同编号缺失且首页存在项目编号，需要人工确认

#### Scenario: 合同编号疑似使用项目编号

- WHEN 合同编号与项目编号完全相同
- THEN 系统 SHALL 输出序号1 WARN，提示合同编号疑似使用项目编号

### Requirement: 签署地预设值匹配

系统 SHALL 根据合同首部签约方识别我方签署主体，并查询签署地预设值。

#### Scenario: 候选主体命中预设值

- WHEN 非客户侧签约方命中签署地预设值
- THEN 系统 SHALL 将该签约方作为我方签署主体

#### Scenario: 候选主体未命中预设值

- WHEN 已提取我方候选主体
- AND 签署地预设值接口未命中
- THEN 系统 SHALL 输出序号1 FAIL，并展示候选主体名称

### Requirement: 序号2/11 签章页完整性与预设值一致性

系统 SHALL 对我方签章页中的九项字段与签署地预设值进行检查。

#### Scenario: 字段为空

- WHEN 九项字段中任一字段在合同中缺失或有字段但无值
- THEN 系统 SHALL 输出 WARN

#### Scenario: 字段非空且与预设值不一致

- WHEN 字段存在实际值
- AND 与签署地预设值不一致
- THEN 系统 SHALL 输出 FAIL

#### Scenario: 法定代表人或授权人姓名通过

- WHEN 签署人姓名等于预设法定代表人
- OR 签署人姓名属于授权人列表
- THEN 系统 SHALL 认为姓名匹配通过

### Requirement: 身份证号关联校验

系统 SHALL 在合同正文或附件出现身份证号时进行必要提示或校验。

#### Scenario: 同时出现姓名和身份证号

- WHEN 合同正文或附件中同时出现法定代表人/授权人姓名和身份证号
- THEN 系统 SHALL 根据预设值校验姓名与身份证号对应关系

#### Scenario: 只有身份证号没有姓名

- WHEN 合同正文或附件中只有身份证号
- AND 没有关联的法定代表人/授权人姓名
- THEN 系统 SHALL 输出 WARN，提示身份证号无从验证

#### Scenario: 只有姓名没有身份证号

- WHEN 只出现法定代表人/授权人姓名
- AND 未出现身份证号
- THEN 系统 SHALL 不触发身份证号关联校验

### Requirement: 序号3 我方签署日期

系统 SHALL 只检查我方签署日期。

#### Scenario: 我方签署日期为空

- WHEN 我方签署日期为空
- THEN 系统 SHALL 通过该项检查

#### Scenario: 我方签署日期早于合同签订日期

- WHEN 我方签署日期早于合同签订日期
- THEN 系统 SHALL 输出 FAIL

### Requirement: 金额和付款条款检查

系统 SHALL 检查币种、金额大小写一致性、付款方式和付款阶段。

#### Scenario: 付款阶段不明确

- WHEN 付款阶段为空或不明确
- THEN 系统 SHALL 输出 WARN，不硬阻断

### Requirement: 附件数量和标题一致性

系统 SHALL 对合同正文声明附件和实际上传附件进行数量/标题检查，并以确定性规范化和私有化模型语义判断建立附件标题关联。

#### Scenario: 合同声明附件数量多于实际上传附件

- WHEN 合同声明附件 3 份
- AND 实际上传附件 2 份
- THEN 系统 SHALL 输出 FAIL

#### Scenario: 格式差异后的标题唯一完全一致

- WHEN 声明标题和上传文件名去除路径、扩展名、明确附件序号前缀及格式符号后唯一完全一致
- THEN 系统 SHALL 将两者关联
- AND 系统 SHALL 不因该名称差异输出标题未匹配提示

#### Scenario: 私有化模型确认语义同一

- WHEN 规范化后仍存在未匹配的声明附件和上传附件
- AND 私有化模型返回经后端校验的一对一 `MATCH` 映射
- THEN 系统 SHALL 将该映射关联为同一附件

#### Scenario: 语义判断无法唯一确认

- WHEN 私有化模型返回 `UNCERTAIN`、`MISMATCH` 或无效的一对一映射
- THEN 系统 SHALL 不建立该附件标题关联
- AND 系统 SHALL 输出提示，请业务确认附件对应关系

#### Scenario: 未匹配附件仍参与内容检查

- WHEN 实际附件未匹配到合同声明附件
- THEN 系统 SHALL 仍将该附件进入 B-4 内容检查

### Requirement: B-1 称谓一致性

系统 SHALL 以合同首部明确的甲乙方定义及其中明确声明的简称为基准，检查合同正文和附件中各签约方称谓是否一致。合同名称、项目名称、背景或历史项目引用不得单独作为签约方定义或称谓不一致证据。系统 SHALL 仅对当前检查分段内可验证且属于签约方称谓语境的观察结果输出 `WARN`；无法验证或不属于签约方称谓的内容不得输出推测性告警。

#### Scenario: 实际称谓不一致

- **WHEN** 首页将乙方定义为“供应商（乙方）”且正文当前分段在签约方称谓语境中使用“卖方”
- **THEN** 系统 SHALL 输出包含当前分段、乙方、发现称谓、首页基准称谓和当前分段证据的 `WARN`

#### Scenario: 合同或项目名称不参与 B-1 比对

- **WHEN** 合同名称或项目名称中出现公司名称，但该处未明确将其定义为甲方、乙方或其简称
- **THEN** 系统 SHALL 不将该名称作为 B-1 的签约方基准、发现称谓或告警证据

#### Scenario: 附件角色未定义主体

- **WHEN** 附件出现“甲方”或“乙方”但未在附件内明确该角色对应的主体
- **THEN** 系统 SHALL 对该角色输出 `WARN`，提示附件未明确对应主体，无法核验其是否与合同正文同角色主体一致

#### Scenario: 附件角色主体定义与正文一致

- **WHEN** 附件明确将甲方或乙方定义为某主体
- **THEN** 系统 SHALL 将该主体与合同正文同角色的法定全称及明确简称比对；匹配时不输出 B-1 告警，不匹配时输出 `WARN`
#### Scenario: 背景项目引用不跨范围取证

- **WHEN** 附件中的背景或鉴于条款引用包含公司名称的项目名称，且未将该公司名称作为签约方称谓使用
- **THEN** 系统 SHALL 不输出 B-1 告警，且不得引用合同正文或其他附件作为该附件的证据

#### Scenario: 未声明简称不作为合法称谓

- **WHEN** 当前分段在签约方称谓语境中使用的公司名称不属于首页定义的全称或明确简称
- **THEN** 系统 SHALL 输出 `WARN` 并要求业务确认是否为同一主体

#### Scenario: B-1 通过项不保留空原因前缀

- **WHEN** B-1 检查结论为 `PASS`，包括兼容旧模型自由文本输出的路径
- **THEN** 系统 SHALL 输出 `reason: null`，不得输出仅含“合同正文中：”或“附件中：”的前缀

#### Scenario: B-1 告警证据采用引文格式

- **WHEN** B-1 对可验证的称谓问题输出 `WARN`
- **THEN** 结论 SHALL 将原文证据表示为 `证据“原文”。`，不得以“证据：”连接原文

### Requirement: B-4 附件内容一致性

系统 SHALL 对附件内容与合同正文关键信息进行一致性检查。

#### Scenario: 实际附件未匹配到声明附件

- WHEN 实际附件未匹配到合同声明附件
- THEN 系统 SHALL 仍将该附件进入 B-4 内容检查

### Requirement: 结构化模型输出

系统 SHALL 对合同审核相关 LLM 调用使用 JSON Schema response_format。

#### Scenario: A-1a 输出缺少顶层字段

- WHEN A-1a 输出缺少 `header`、`signature_parties` 或 `sections`
- THEN 系统 SHALL 重试一次
- AND 重试后仍不符合结构时返回 `20003`

### Requirement: 统一响应壳

系统 SHALL 返回统一响应结构。

#### Scenario: 成功响应

- THEN 响应 SHALL 包含 `code`、`message`、`data`、`traceId`、`duration_seconds`

#### Scenario: 模型输出格式异常

- WHEN 模型输出无法解析或结构不符合要求
- THEN 系统 SHALL 返回错误码 `20003`

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

## 依赖

- 合同组织评审 SHALL 使用项目级统一响应壳。
- 合同组织评审 SHALL 复用 `app/models/llm.py` 进行模型调用。
- 合同组织评审 SHALL 遵循现有错误码约定，其中模型格式错误使用 `20003`。
