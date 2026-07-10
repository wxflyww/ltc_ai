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

系统 SHALL 对合同正文声明附件和实际上传附件进行数量/标题检查。

#### Scenario: 合同声明附件数量多于实际上传附件

- WHEN 合同声明附件 3 份
- AND 实际上传附件 2 份
- THEN 系统 SHALL 输出 FAIL

### Requirement: B-1 称谓一致性

系统 SHALL 检查合同正文和附件中各签约方称谓是否一致。

#### Scenario: 称谓不一致

- WHEN 模型发现称谓不一致
- THEN 系统 SHALL 输出 WARN
- AND reason SHALL 说明涉及哪一方、出现了哪些不同称谓、分别出现在哪些位置或上下文中

#### Scenario: 称谓不一致 reason 过于笼统

- WHEN 模型返回“称谓存在不一致”等泛化 reason
- THEN 系统 SHALL 重试一次，要求补充具体主体、称谓和位置

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

## 依赖

- 合同组织评审 SHALL 使用项目级统一响应壳。
- 合同组织评审 SHALL 复用 `app/models/llm.py` 进行模型调用。
- 合同组织评审 SHALL 遵循现有错误码约定，其中模型格式错误使用 `20003`。
