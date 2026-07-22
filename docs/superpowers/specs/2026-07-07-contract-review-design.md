# Contract Review Organization Review Design

> 本规格用于实现 LTC403.1-C02 合同组织评审 AI 能力。业务规则以《LTC403_1-C02_解决方案合同组织评审_AI实现方案_v1_3.md》为准；字段契约以《签署地预设值接口规范 - v1.2.md》为准；工程实现细节以《LTC403.1-C02_AI合同审核系统_工程设计文档 - 1.1.md》为准。

## Goal

在组织评审阶段，对销售传入的合同正文 Markdown 和附件文本，按确认后的检查点输出完整的硬阻断项、提示项和通过项。系统不负责 OCR、压缩包解压或原始文件解析，只处理上游已经转换好的文本。

## Scope

当前组织评审阶段实现以下检查项：

- 序号1：合同首页完整性
- 序号2：签章页完整性
- 序号3：签署日期
- 序号4：称谓一致性
- 序号7：总价大小写一致性
- 序号8：货币条款
- 序号9：付款方式
- 序号10：付款阶段
- 序号11：账户信息
- 序号12：合同份数
- 附件检查：数量/标题一致性与附件内容一致性

不属于当前实现范围：

- 序号5 产品/服务描述
- 序号6 数量条款
- 付款方式词库匹配；该能力是后续合同评审阶段预留，当前序号9只做非空校验。

## Architecture

新增能力包：

```text
app/capabilities/contract_review/
  __init__.py
  router.py
  schemas.py
  service.py
  prompts.py
  utils.py
  preset_client.py
  party.py
  checks.py
  attachments.py
```

新增 Prompt：

```text
prompts/contract_review.yaml
```

测试文件：

```text
tests/test_contract_review_api.py
tests/test_contract_review_service.py
tests/test_contract_review_party.py
tests/test_contract_review_checks.py
tests/test_contract_review_attachments.py
tests/test_contract_review_preset_client.py
```

合同审核能力复用现有模型适配层：

```python
from app.models.llm import get_chat_model, invoke_model
```

能力包不得直接创建 `OpenAI` 或 `ChatOpenAI` 客户端，不直接读取或管理模型 `api_key`、`base_url`、`model` 等连接配置。`llm.py` 中 API Key 从 demo 硬编码改为配置项属于模型适配层职责，不阻塞合同审核能力开发。

## Input Contract

Endpoint:

```text
POST /api/v1/contract-review
```

The endpoint requires the same API key authentication as other non-health business endpoints.

API 入参：

```json
{
  "contract_md": "合同正文Markdown文本",
  "attachments": [
    {
      "index": 1,
      "filename": "附件1-报价清单.xlsx",
      "file_type": "xlsx",
      "text": "附件文本内容"
    }
  ]
}
```

`attachments` 表示上游实际传入并已解析出的单独上传附件文本。合同正文中内嵌附件不在该数组中，由 Pipeline A-4 结合 `sections` 定位。

## Output Contract

业务响应放入现有统一响应的 `data` 字段：


```json

{
  "code": 0,
  "message": "ok",
  "data": {
    "overall_result": "PASS | BLOCK",
    "check_time": "2026-06-23T10:00:00",
    "checks": [
      {
        "id": "序号2",
        "name": "签章页完整性",
        "result": "FAIL | WARN | PASS | NA",
        "block_level": "硬阻断 | 提示 | 通过 | 不适用",
        "reason": "具体原因；无问题为null"
      }
    ]
  },
  "traceId": "链路追踪ID",
  "duration_seconds": 0.123
}

```

硬性约束：

- `checks` 必须是列表。
- 同一 `id` 允许出现多条记录。
- 同一检查项同时存在硬阻断和提示时，拆分为两条记录。
- 不允许用 `dict[id] = item` 覆盖聚合。
- 任一记录满足 `result=FAIL` 且 `block_level=硬阻断` 时，`overall_result=BLOCK`。
- `overall_result=BLOCK` 时，WARN/提示项仍必须完整展示。
- 合同审核能力不得绕过现有统一响应机制；业务字段只放在 data 内，不能把 overall_result/checks 提升到顶层。

## Error Contract

合同审核能力沿用现有统一错误码和异常响应机制。

```text
10001 参数校验失败
10002 鉴权失败
20001 模型调用失败重试耗尽
20002 模型调用超时
20003 模型输出格式异常
29999 未知错误
```

错误响应仍使用统一响应壳：

```json
{
  "code": 20003,
  "message": "模型输出格式异常",
  "data": null,
  "traceId": "链路追踪ID",
  "duration_seconds": 0.123
}
```

映射要求：

- Pydantic 入参校验失败：`10001`。
- API Key 鉴权失败：`10002`。
- LLM 调用在 service 层重试耗尽：`20001`。
- LLM 超时：`20002`。
- LLM 返回空内容、非 JSON、缺少必填字段或 JSON 解析失败：`20003`。
- 未捕获异常：`29999`。

长度问题业务化返回：

- 检测到输入上下文超长（如 `tokens_limit_reached`、`context length`）时，系统返回业务检查项：
  - `id=name=模型上下文长度`
  - `result=FAIL`
  - `block_level=硬阻断`
- 检测到模型输出长度截断（如 `LengthFinishReasonError`、`length limit was reached`）时，系统返回业务检查项：
  - `id=name=模型输出长度`
  - `result=FAIL`
  - `block_level=硬阻断`
- 两类长度问题都视为阻断项，`overall_result` 应为 `BLOCK`。

## Framework Integration

合同审核能力作为独立 capability 接入现有薄分层架构：

```text
API Router → contract_review service → app.models.llm → app.core
```

接入要求：

- 在 `app/capabilities/contract_review/router.py` 定义 FastAPI router，prefix 使用 `/api/v1`。
- 在 `app/main.py:create_app()` 中通过 `app.include_router(contract_review_router)` 注册路由。
- 路由函数返回 `ApiResponse(data=data).to_dict()`，保持 `traceId` 和 `duration_seconds` 由中间件注入。
- 不新增独立响应壳，不绕过 `app.core.response.ApiResponse`。
- 不在能力包中注册新的全局中间件。

## Prompt Management

Prompt 模板存放在：

```text
prompts/contract_review.yaml
```

加载逻辑放在：

```text
app/capabilities/contract_review/prompts.py
```

要求：

- `service.py` 不硬编码大段 Prompt 文本。
- Prompt 构造函数返回 LangChain message 列表，供 `invoke_model()` 调用。
- Prompt JSON 输出必须由 service 层解析和校验；格式异常映射为 `ModelFormatError` / `20003`。

## LLM Retry Policy

合同审核 service 遵循现有模型调用与重试约束：

- 模型实例由 `get_chat_model()` 提供。
- 单次模型调用由 `invoke_model()` 执行。
- 重试逻辑只在 service 层实现。
- 最多 3 次尝试：1 次初始调用 + 2 次重试。
- 可重试错误：超时、HTTP 5xx、HTTP 429。
- 不可重试错误：模型输出格式异常、JSON 解析失败、字段校验失败。
- 重试退避使用指数退避 + 抖动，保持与现有 translate 能力一致。
- 单元测试必须 mock `invoke_model()`，CI 不依赖真实私有化 LLM；本地联调和样本验收可以接入私有化 LLM 运行。

## Pipeline 0: Text Preprocessing

Pipeline 0 由代码实现，不调用 LLM。

职责：

- 归一化标点。
- 暴露 `full_text` 给后续代码和 Prompt。
- 按 Markdown 标题生成 `sections`。
- 标准化附件输入。

输出：

```text
full_text: str
sections: list[{title, content}]
attachments: list[{index, filename, file_type, text}]
```

## Pipeline A-1a: Party Extraction

A-1a 调用 LLM 从全文中提取：

```json
{
  "header_info": {
    "contract_name": "合同名称",
    "contract_number": "合同编号或null",
    "signing_location": "签订地点；无效地名以错误：前缀标注",
    "signing_date": "首部签订日期或null",
    "parties": [
      {"role": "甲方", "name": "签约方全称"}
    ]
  },
  "signature_info": {
    "signature_parties": [
      {"role": "甲方", "name": "签章区块签约方名称或null"}
    ]
  }
}
```

多方合同下，A-1a 不得要求模型猜测谁是我方。

## Our Party Identification

从 `header_info.parties` 中生成候选我方签署主体。

客户侧角色不查询签署地预设接口：

```text
甲方、买方、采购方、需方、委托方、发包方、建设方、出租方、授权方、许可方
```

供应/服务侧角色优先查询：

```text
乙方、卖方、供应方、供方、服务方、服务提供方、受托方、承包方、施工方、承租方、被授权方、被许可方、受让方
```

中性/未知角色补充查询：

```text
合作方一、合作方二、第一方、第二方、第三方、参与方、签约方、合同方，以及未命中分类清单的其他角色
```

查询顺序：

1. 供应/服务侧角色；
2. 中性/未知角色；
3. 同一类内按合同出现顺序。

任一候选主体命中签署地预设接口后，即认定为我方签署主体并停止查询。一份合同只允许识别一个我方签署主体。

## Signing Entity Preset Interface

调用《签署地预设值接口规范 - v1.2.md》。

请求：

```json
{
  "entity_name": "候选我方签署主体全称"
}
```

成功返回：

```json
{
  "entity_name": "签署主体全称",
  "legal_rep_name": "法定代表人姓名",
  "legal_rep_id_number": "法定代表人身份证号",
  "authorized_reps": [
    {"name": "授权人姓名", "id_number": "授权人身份证号"}
  ],
  "bank_name": "开户银行名称",
  "bank_account": "银行账号",
  "account_holder": "开户名称",
  "address": "通讯地址",
  "phone": "联系电话",
  "fax": "传真号或空字符串",
  "website": "网址或空字符串",
  "postal_code": "邮政编码"
}
```

查不到返回 `{}`。单次调用超过 1 秒，按当前候选未命中处理。

## Pipeline A-1b: Our Signature Info Extraction

我方识别完成后，A-1b 调用 LLM 提取我方签章区块字段：

```json
{
  "role": "我方签署主体角色",
  "name": "我方签署主体名称",
  "legal_rep_name": "我方法定代表人或授权人姓名或null",
  "signer_id_number": "我方法定代表人/授权人身份证号或null",
  "signing_date": "我方签署日期或null",
  "bank_name": "开户银行或null",
  "bank_account": "银行账号或null",
  "account_holder": "开户名称或null",
  "address": "通讯地址或null",
  "phone": "电话或null",
  "fax": "传真或null",
  "website": "网址或null",
  "postal_code": "邮政编码或null"
}
```

两方快路径可在一次 LLM 调用中同时完成 A-1a 和 A-1b，但逻辑上仍以“先识别我方，再使用我方专属字段”为准。

## Check Rules

### 序号1：合同首页完整性

- 合同名称、签约方列表、签订地点缺失：FAIL。
- 我方主体识别失败或预设不可用：FAIL。
- 我方主体名称与 `system_preset.entity_name` 不一致：FAIL。
- 签订地点以 `错误：` 开头：FAIL。
- 合同编号缺失：WARN。
- 首页签订日期缺失：WARN。

### 序号2：签章页完整性

- 任一首部签约方在签章区同 `role` 名称缺失：WARN。
- 签章区同 `role` 名称与首部不一致：FAIL。
- 9 项字段为空：WARN。
- 9 项字段非空且与预设不一致：FAIL。
- `legal_rep_name` 等于 `system_preset.legal_rep_name` 或任一 `system_preset.authorized_reps[].name` 即通过人员姓名校验。

9 项字段：

```text
legal_rep_name, bank_name, bank_account, account_holder,
address, phone, fax, website, postal_code
```

### 身份证号关联校验

- 同时出现姓名和身份证号：按预设姓名—身份证号对应关系校验。
- 只有姓名、没有身份证号：不提示、不阻断。
- 只有身份证号、没有姓名：WARN，不做关联校验。
- 找不到人员、预设身份证号为空、身份证号不一致：FAIL。

### 序号3：签署日期

- 只检查我方签署日期。
- 我方识别失败：FAIL。
- 我方签署日期为空：PASS，跳过。
- 日期格式无法解析：FAIL。
- 与首页日期不一致：FAIL。
- 早于系统日期：FAIL。

### 序号7：总价大小写一致性

- 总价数字或大写缺失：FAIL。
- 大小写金额不一致：FAIL。

### 序号8：货币条款

- 计价货币缺失：FAIL。

### 序号9：付款方式

- 付款方式缺失：FAIL。
- 非空即通过。
- 付款方式词库匹配不属于当前组织评审阶段。

### 序号10：付款阶段

- 付款阶段为空：WARN，跳过后续比例、金额、大写金额校验。
- 阶段非空时，比例之和不等于 100%：FAIL。
- 阶段金额与比例不一致：FAIL。
- 阶段大写金额不一致：FAIL。

### 序号11：账户信息

复用序号2的 `bank_name`、`bank_account`、`account_holder` 提取和比对结果。

- 任一字段为空：WARN。
- 任一非空字段与预设不一致：FAIL。
- 预设不可用：FAIL。
- 不受序号2中法人、地址、电话等其他字段影响。

### 序号12：合同份数

```json
{
  "copies": {
    "total_copies": 6,
    "party_copies": [
      {"role": "甲方", "copies": 1},
      {"role": "乙方", "copies": 5}
    ],
    "raw_text": "原文"
  }
}
```

- 总份数缺失：FAIL。
- 任一签约方份数缺失：FAIL。
- 各方份数之和不等于总份数：FAIL。

## Attachment Handling

附件实际来源包括：

- 内嵌在正文；
- 单独上传；
- 缺失。

实际附件总数：

```text
已定位内嵌附件数 + 单独上传附件数
```

规则：

- 正文声明附件数 `total_declared` 大于实际附件总数：FAIL。
- 实际数量足够但标题无法可靠匹配：WARN。
- 多余上传附件没有正文标注来源：FAIL。
- 所有实际上传附件，即使标题未匹配，也必须进入 B-4 内容一致性检查。
- 合同正文未声明附件且未上传附件：NA。

## Pipeline B-1: Appellation Consistency

B-1 按检查范围分段执行，不将正文和附件拼接为一次大输入。

输入与执行方式：

```text
1) 合同正文（scope=合同正文）
2) 每份已解析附件（scope=附件标题或上传文件名）
```

- 每个分段独立调用一次 LLM，输出 `checks` 列表。
- 后端为每条 B-1 结果补充可追溯范围：
  - `name` 统一为 `称谓一致性-<scope>`。
  - `reason` 前缀统一为 `【范围】<scope>`。
- 后端会过滤非称谓噪声告警，并对重复语义告警去重。
- 当模型返回“称谓存在不一致”等泛化原因时，后端会触发一次补充说明重试，要求返回具体主体和上下文。

## Pipeline B-4: Attachment Content Consistency

每份已解析附件单独调用一次。

输入包括：

```text
attachment_text
header_info.parties
our_party_context
signature_info.legal_rep_name
signature_info.signer_id_number
system_preset.legal_rep_name
system_preset.legal_rep_id_number
system_preset.authorized_reps
```

规则：

- 附件出现任一签约方名称时，需与合同正文同角色签约方一致。
- 附件出现我方法定代表人或授权人姓名时，需与签章页信息一致。
- 附件同时出现我方人员姓名和身份证号时，按预设映射校验。
- 附件只有身份证号没有姓名：WARN。
- 任一 FAIL violation 使 B-4 结果为 FAIL。
- 只有 WARN violation 时结果为 WARN。
- 无问题时为 PASS。

## Sensitive Information Handling

当前采用 v1.2 短期方案：预设接口仍返回身份证号，但本服务只在单次请求内存中使用。

要求：

- 身份证号明文不落库。
- 身份证号明文不缓存。
- 身份证号明文不写日志、trace、指标标签。
- 最终报告不得展示完整身份证号。
- 如需展示，使用前6后4脱敏：`210102********0011`。
- 能由代码完成的身份证号比对，不把预设身份证号主数据传给 LLM。
- LLM 只负责提取合同/附件中出现的姓名和身份证号。
- 单元测试必须覆盖脱敏函数和 `reason` 脱敏。

## Test Coverage

必须覆盖：

- 甲乙双方合同。
- 买方/卖方合同。
- 采购方/供应方合同。
- 任意多方合同。
- 客户侧角色跳过预设查询。
- 供应/服务侧角色优先查询。
- 中性/未知角色补充查询。
- 首个候选命中后停止查询。
- 全部候选未命中。
- 预设接口 `{}`。
- 预设接口超时。
- 9 项空值 WARN。
- 9 项非空不一致 FAIL。
- 法定代表人身份证号匹配。
- 授权人身份证号匹配。
- 预设身份证号为空时 FAIL。
- 只有身份证号无姓名时 WARN。
- 只有姓名无身份证号时不提示。
- 付款阶段为空 WARN。
- 声明 3 份附件但只获取 2 份时 FAIL。
- 标题未匹配附件仍进入 B-4。
- 同一检查项同时产生 FAIL 和 WARN 时，最终 `checks` 保留两条。
- 输入上下文超长返回 `模型上下文长度` 硬阻断。
- 模型输出被长度截断返回 `模型输出长度` 硬阻断。
- B-1 输出 `name` 包含分段范围，`reason` 包含 `【范围】` 前缀。
- B-1 重复告警会去重，非称谓噪声项会被过滤。
- 模型调用异常审计事件包含 `length_issue=input|output` 分类。

## Implementation Notes

- 单元测试和CI测试应 mock `invoke_model()`，不依赖真实LLM；本地联调和样本验收可接入私有化大模型运行。
- Prompt JSON 解析失败应作为模型格式异常处理，进入现有错误体系。
- 所有字段空值判断统一使用 `None`、空字符串、纯空白、字符串 `"null"` 为空。
- 金额计算使用 `Decimal`，避免浮点误差。
- `bank_account`、`phone`、`fax`、`website`、`postal_code` 比对前做全半角归一化。
- 开启 LLM trace 后，模型调用异常事件使用 `invoke_json_prompt_invoke_error` / `invoke_json_prompt_retry_invoke_error`，并记录长度问题分类。
- 长度问题优先做输入/输出分类，不将输出截断误标为输入超长。
