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
}
```

硬性约束：

- `checks` 必须是列表。
- 同一 `id` 允许出现多条记录。
- 同一检查项同时存在硬阻断和提示时，拆分为两条记录。
- 不允许用 `dict[id] = item` 覆盖聚合。
- 任一记录满足 `result=FAIL` 且 `block_level=硬阻断` 时，`overall_result=BLOCK`。
- `overall_result=BLOCK` 时，WARN/提示项仍必须完整展示。

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
- 声明 3 份附件但只获取 2 份：FAIL。
- 实际数量足够但标题无法可靠匹配：WARN。
- 多余上传附件没有正文标注来源：FAIL。
- 所有实际上传附件，即使标题未匹配，也必须进入 B-4 内容一致性检查。
- 合同正文未声明附件且未上传附件：NA。

## Pipeline B-1: Appellation Consistency

输入为：

```text
full_text + all attachment texts
```

LLM 直接输出 `PASS` 或 `FAIL`。后端不做二次语义判断。

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

## Implementation Notes

- LLM 调用在测试中 mock `invoke_model()`。
- Prompt JSON 解析失败应作为模型格式异常处理，进入现有错误体系。
- 所有字段空值判断统一使用 `None`、空字符串、纯空白、字符串 `"null"` 为空。
- 金额计算使用 `Decimal`，避免浮点误差。
- `bank_account`、`phone`、`fax`、`website`、`postal_code` 比对前做全半角归一化。
