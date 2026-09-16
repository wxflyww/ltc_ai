# contract-review 规格变更

## MODIFIED Requirements

### Requirement: Markdown 合同组织评审接口

系统 SHALL 提供合同组织评审接口，接收解析后的合同 Markdown 正文和附件 Markdown 文本，并 SHALL 通过可选请求参数 `mode` 区分本次调用是组织评审还是智能预填。`mode` 取值 SHALL 仅为 `review` 和 `prefill`；未传 `mode` 时 SHALL 按 `review` 处理。

#### Scenario: JSON 请求评审

- WHEN 调用 `POST /api/v1/contract-review`
- AND 请求体包含 `contract_md` 和 `attachments`
- THEN 系统 SHALL 返回统一响应壳
- AND `data.checks` SHALL 包含所有检查结果

#### Scenario: Markdown 文件上传评审

- WHEN 调用 `POST /api/v1/contract-review/upload-md`
- AND 上传合同 Markdown 文件及可选附件 Markdown 文件
- THEN 系统 SHALL 复用合同组织评审流程

#### Scenario: 未传 mode 时按评审处理

- WHEN 调用 `POST /api/v1/contract-review` 且请求体不包含 `mode`
- THEN 系统 SHALL 执行组织评审链路
- AND `data` SHALL 仅包含 `overall_result`、`check_time`、`checks`、`metrics`

#### Scenario: 显式传入 mode=review

- WHEN 调用 `POST /api/v1/contract-review` 且 `mode` 为 `review`
- THEN 系统 SHALL 执行组织评审链路
- AND 响应 `data` SHALL 与未传 `mode` 时逐字段一致
- AND 响应 SHALL NOT 因该参数新增任何字段

#### Scenario: mode 取值非法

- WHEN 请求体的 `mode` 取值不是 `review` 或 `prefill`
- THEN 系统 SHALL 返回错误码 `10001`
- AND 系统 SHALL NOT 执行组织评审链路或智能预填链路

## ADDED Requirements

### Requirement: 智能预填调用形态

系统 SHALL 在同一入口 `POST /api/v1/contract-review` 上提供智能预填形态：当 `mode` 为 `prefill` 时，系统 SHALL 只执行预填链路并 SHALL NOT 执行组织评审链路。预填响应 `data` SHALL 包含 `mode`、`prefill_status` 和 `prefill`，且 SHALL NOT 包含 `overall_result`、`check_time`、`checks`、`metrics`。系统 SHALL NOT 在 `mode` 为 `review` 的响应中回显 `mode`。

系统 SHALL 接受可选请求参数 `prefill_scope`，取值 SHALL 仅为 `all`、`d02`、`d03`，未传时 SHALL 按 `all` 处理。`prefill_scope` SHALL 仅在 `mode` 为 `prefill` 时生效，SHALL NOT 影响 `mode` 为 `review` 的响应。`all` SHALL 抽取全部四组；`d02` SHALL 只抽取 `contract_info` 与 `contract_plan`；`d03` SHALL 只抽取 `finance_info` 与 `guarantee`。未被请求的组 SHALL 仍出现在 `data.prefill` 中且 SHALL NOT 省略键，并按未取到规则表达（标量字段为 `null`、数组为空数组）；系统 SHALL NOT 为"未被请求"引入区别于"未取到"的第三种表达。

#### Scenario: 预填调用返回预填数据体

- WHEN 调用 `POST /api/v1/contract-review` 且 `mode` 为 `prefill`
- AND 请求体包含 `contract_md`
- THEN 系统 SHALL 返回统一响应壳
- AND `data` SHALL 包含 `mode`、`prefill_status`、`prefill`
- AND `data.mode` SHALL 为 `prefill`

#### Scenario: 预填不产出评审结论

- WHEN 调用 `POST /api/v1/contract-review` 且 `mode` 为 `prefill`
- THEN `data` SHALL NOT 包含 `overall_result`、`check_time`、`checks`、`metrics`
- AND 系统 SHALL NOT 在预填链路上计算任何检查点结论

#### Scenario: 预填形态下附件不参与抽取

- WHEN 调用 `POST /api/v1/contract-review` 且 `mode` 为 `prefill`
- AND 请求体包含 `attachments`
- THEN 系统 SHALL 正常接收该字段
- AND 系统 SHALL NOT 使用附件内容参与字段抽取

#### Scenario: 未传 prefill_scope 时抽取全部字段

- WHEN 调用 `POST /api/v1/contract-review` 且 `mode` 为 `prefill`
- AND 请求体不包含 `prefill_scope`
- THEN 系统 SHALL 按 `all` 抽取
- AND `data.prefill` SHALL 包含 `contract_info`、`contract_plan`、`finance_info`、`guarantee` 四组

#### Scenario: 按场景只抽取一半

- WHEN 调用 `POST /api/v1/contract-review` 且 `mode` 为 `prefill`、`prefill_scope` 为 `d03`
- THEN 系统 SHALL 只抽取 `finance_info` 与 `guarantee`
- AND `data.prefill` SHALL 仍包含 `contract_info`、`contract_plan`、`finance_info`、`guarantee` 四组
- AND `contract_info` 的各标量字段 SHALL 为 `null`
- AND `contract_plan` SHALL 为空数组

#### Scenario: prefill_scope 取值非法

- WHEN 请求体的 `prefill_scope` 取值不是 `all`、`d02` 或 `d03`
- THEN 系统 SHALL 返回错误码 `10001`
- AND 系统 SHALL NOT 执行智能预填链路

#### Scenario: prefill_scope 不影响评审链路

- WHEN 请求体的 `mode` 为 `review` 且携带 `prefill_scope`
- THEN 响应 `data` SHALL 与未携带该参数时逐字段一致
- AND 系统 SHALL NOT 因该参数改变评审链路行为或新增任何字段

### Requirement: 预填字段数据契约

系统 SHALL 在 `data.prefill` 中返回四组结构，共 26 个返回字段：`contract_info`（对象，9 个字段）、`contract_plan`（数组，每项 8 个字段）、`finance_info`（对象，2 个字段）、`guarantee`（数组，每项 7 个字段）。系统 SHALL NOT 在预填响应中省略任何键。

- `contract_info` SHALL 包含 `payment_terms`、`payment_method`、`service_content`、`service_valid_months`、`service_sla`、`service_start_date`、`service_end_date`、`onsite_service_count`、`inspection_count`。
- `finance_info` SHALL 包含 `contract_amount`、`currency`。
- 日期类字段 SHALL 序列化为 `YYYY-MM-DD` 字符串；金额类字段 SHALL 序列化为含税、两位小数的数字。
- 未取到的标量字段 SHALL 为 `null`，系统 SHALL NOT 以空字符串占位；`contract_plan` 与 `guarantee` 未取到时 SHALL 为空数组。
- `payment_method` SHALL 抽取支付手段（如电汇、转账、汇票、承兑），`payment_terms` SHALL 抽取分期与条件条款的整段原文；两者仅有同一处原文时系统 SHALL NOT 整段重复，支付手段词归 `payment_method`、其余归 `payment_terms`。

#### Scenario: 字段完整返回

- WHEN 合同正文中同时存在可抽取的合同信息、合同计划、财务信息和履约保证金
- THEN `data.prefill` SHALL 包含 `contract_info`、`contract_plan`、`finance_info`、`guarantee` 四组
- AND `contract_info` SHALL 包含上列 9 个键
- AND `finance_info` SHALL 包含上列 2 个键

#### Scenario: 字段未取到的表达

- WHEN 合同正文中不存在某一标量字段的可用事实
- THEN 该字段 SHALL 为 `null`
- AND 该字段 SHALL NOT 为空字符串占位
- AND 该键 SHALL 仍然出现在响应中

#### Scenario: 数组类字段无内容

- WHEN 合同正文中不存在付款阶段或履约保证金
- THEN `contract_plan` SHALL 为空数组
- AND `guarantee` SHALL 为空数组

#### Scenario: 付款方式与付款条件的边界

- WHEN 合同正文中只有一处章节同时描述支付手段与分期条款
- THEN `payment_method` SHALL 只包含支付手段词
- AND `payment_terms` SHALL 包含分期与条件条款的整段原文
- AND 系统 SHALL NOT 将同一整段原文同时填入两个字段

#### Scenario: 日期与金额的序列化

- WHEN 抽取到服务开始时间与合同额
- THEN `service_start_date` SHALL 为 `YYYY-MM-DD` 形式的字符串
- AND `contract_amount` SHALL 为含税、最多两位小数的数字

### Requirement: 合同计划抽取与里程碑归一

系统 SHALL 从付款条件中抽取付款阶段，并为每一阶段返回 `milestone_name`、`milestone_code`、`milestone_text`、`milestone_seq`、`plan_finish_date`、`plan_payment_date`、`payment_amount`、`evidence`。

系统 SHALL 将合同中的任意写法按语义归一为固定里程碑枚举，该枚举 SHALL 为：`begin` 启动、`confirm` 环境确认、`deliver` 交付、`design` 设计、`develop` 开发、`end` 维护期、`finalaccept` 终验、`midmaintain` 阶段维护、`plan` 策划、`preaccept` 初验、`require` 需求、`test` 测试、`testrun` 试运行。系统 SHALL NOT 使用词表硬匹配或句式白名单，也 SHALL NOT 固化合同侧的写法；归一失败的 `milestone_name` 与 `milestone_code` SHALL 为 `null`。

`contract_plan` SHALL 按 `milestone_seq` 升序排列，`milestone_seq` SHALL 表示该阶段在付款条件原文中的顺序，从 1 起。

#### Scenario: 非标准写法归一为标准里程碑

- WHEN 付款条件中的阶段描述为"合同签订及预付款"
- THEN `milestone_name` SHALL 为 13 个标准名之一
- AND `milestone_code` SHALL 为与 `milestone_name` 配对的枚举 code
- AND `milestone_text` SHALL 为该阶段的原文描述

#### Scenario: 无法归一为任何标准里程碑

- WHEN 某阶段的原文描述无法对应到 13 个标准名中的任何一个
- THEN `milestone_name` SHALL 为 `null`
- AND `milestone_code` SHALL 为 `null`
- AND `milestone_text` SHALL 仍保留该阶段原文描述

#### Scenario: 多阶段按原文顺序排列

- WHEN 付款条件包含多个付款阶段
- THEN `contract_plan` SHALL 按 `milestone_seq` 升序排列
- AND `milestone_seq` SHALL 从 1 起连续表示原文中的阶段顺序

#### Scenario: 基于已抽到事实推算而非臆造

- WHEN 付款条件给出比例且合同金额条款给出合同总额
- AND 计算目标需要推导得出回款金额或计划回款时间
- THEN 系统 MAY 基于已抽到的事实推导该字段
- AND 推导不出的字段 SHALL 为 `null`
- AND 系统 SHALL NOT 生成没有原文依据的值

### Requirement: 履约保证金多笔抽取

系统 SHALL 从合同正文中抽出全部履约保证金 / 保函记录，数量不设上限；每条记录 SHALL 包含 `type`、`amount`、`payee`、`bank_name`、`bank_account`、`return_clause`、`evidence`。`type` SHALL 取 `履约保函` 或 `履约保证金` 之一。合同正文中不存在相关记录时 `guarantee` SHALL 为空数组。

#### Scenario: 合同包含多笔履约保证金

- WHEN 合同正文中出现多笔履约保证金或保函约定
- THEN `guarantee` SHALL 包含全部记录
- AND 每条记录 SHALL 包含上列 7 个键
- AND `type` SHALL 为 `履约保函` 或 `履约保证金`

#### Scenario: 合同不含履约保证金

- WHEN 合同正文中没有履约保证金或保函约定
- THEN `guarantee` SHALL 为空数组

### Requirement: 预填原文依据标注章节位置

`contract_plan` 与 `guarantee` 中的**每一行** SHALL 附 `evidence`，其元素结构 SHALL 为 `{ "section": string | null, "quote": string }`。系统 SHALL 按出处各列一条并去重；拿不到任何原文依据时 `evidence` SHALL 为空数组。

`section` SHALL 取该条原文所在章节 / 条款的**顶层标题原文**，SHALL NOT 取子层级标题或正文段落；原文无标题结构时 `section` SHALL 为 `null`。系统 SHALL NOT 预设 `section` 的枚举或标题白名单。`quote` SHALL 为取自该位置的原文片段，长度 SHALL NOT 超过 60 字。

#### Scenario: 一行字段横跨多处原文

- WHEN 某付款阶段的计划完成时间来自交付条款、回款金额来自合同金额条款与付款条件
- THEN 该行 `evidence` SHALL 按出处各列一条
- AND 每条 SHALL 同时包含 `section` 与 `quote` 两个键
- AND 同一出处 SHALL NOT 重复出现

#### Scenario: 标注原文顶层标题

- WHEN 某条原文位于形如 `# 第四条 付款方式及条件` 的顶层条款标题之下
- THEN 该条 `section` SHALL 取该顶层标题原文
- AND 该条 `section` SHALL NOT 取形如 `## 1.1 分阶段支付合同款…` 的子层级内容

#### Scenario: 原文无标题结构

- WHEN 合同正文经换行归一化后仍无标题结构
- THEN 相关出处条目的 `section` SHALL 为 `null`
- AND 该条 `quote` SHALL 仍为可核对的原文片段

#### Scenario: 未找到原文依据

- WHEN 某一行字段在合同正文中没有可定位的原文依据
- THEN 该行 `evidence` SHALL 为空数组
- AND 该行其余字段 SHALL 仍按未取到规则表达

### Requirement: 预填输入换行归一化

系统 SHALL 在预填 prompt 边界内对 `contract_md` 做换行归一化，使"整行文本 + 字面量 `\n`"形态的输入恢复为真实换行后的 Markdown 结构，归一化 SHALL NOT 改变合同原文的可见字符内容。该归一化 SHALL 仅作用于预填链路，SHALL NOT 影响 `mode=review` 的现有输入处理。

#### Scenario: 整行加字面量换行的输入

- WHEN `contract_md` 为一整行文本且内部以字面量 `\n` 表示换行
- THEN 系统 SHALL 在预填抽取前将其还原为真实换行
- AND 预填抽取 SHALL 能够识别还原后的 Markdown 标题与表格结构

#### Scenario: 归一化不影响评审链路

- WHEN 以 `mode=review` 调用 `POST /api/v1/contract-review`
- THEN 系统 SHALL 按现有输入处理逻辑使用 `contract_md`
- AND 归一化逻辑 SHALL NOT 作用于评审链路

### Requirement: 预填失败兜底与状态语义

`prefill_status` 取值 SHALL 仅为 `ok` 与 `failed`，SHALL 只表示本次预填调用是否成功：`ok` 表示模型正常返回且结构化输出解析成功；`failed` 表示模型调用失败、超时或输出超长。`prefill_status` SHALL NOT 用于区分"合同中确实没有该字段"与"未抽取到该字段"，系统 SHALL NOT 提供字段级抽取状态或覆盖度。

当 `prefill_status` 为 `failed` 时，系统 SHALL 仍返回 HTTP 成功响应与统一响应壳，且 SHALL 保持 `data.prefill` 的四组结构完整，各标量字段为 `null`、各数组为空数组。模型调用失败 SHALL NOT 使预填调用返回 5xx。

#### Scenario: 模型调用失败时的兜底

- WHEN `mode` 为 `prefill` 且模型调用失败、超时或输出超长
- THEN `prefill_status` SHALL 为 `failed`
- AND `data.prefill` SHALL 仍包含 `contract_info`、`contract_plan`、`finance_info`、`guarantee`
- AND `contract_info` 与 `finance_info` 的标量字段 SHALL 为 `null`
- AND `contract_plan` 与 `guarantee` SHALL 为空数组
- AND 响应 SHALL NOT 为 5xx

#### Scenario: 模型正常返回但部分字段未抽到

- WHEN `mode` 为 `prefill` 且模型正常返回且结构化输出解析成功
- THEN `prefill_status` SHALL 为 `ok`
- AND 未抽到的标量字段 SHALL 为 `null`
- AND 未抽到的数组 SHALL 为空数组
- AND 响应 SHALL NOT 区分该字段是"合同中没有"还是"未被抽到"

#### Scenario: 评审链路异常行为不变

- WHEN `mode` 为 `review` 且模型调用失败
- THEN 系统 SHALL 沿用现有评审链路的异常行为与错误码
- AND 预填兜底逻辑 SHALL NOT 作用于评审链路
