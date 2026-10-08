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

系统 SHALL 在 `POST /api/v1/contract-review`（JSON 入口，`mode` 取自请求体）与 `POST /api/v1/contract-review/upload-md`（Markdown 文件入口，`mode` 取自表单字段）**两个入口**上提供智能预填形态，两个入口的 `mode` 语义、字段口径与响应结构 SHALL 完全一致。当 `mode` 为 `prefill` 时，系统 SHALL 只执行预填链路并 SHALL NOT 执行组织评审链路。预填响应 `data` SHALL 包含 `mode`、`prefill_status` 和 `prefill`，且 SHALL NOT 包含 `overall_result`、`check_time`、`checks`、`metrics`。系统 SHALL NOT 在 `mode` 为 `review` 的响应中回显 `mode`。

系统 SHALL 接受可选请求参数 `prefill_scope`，取值 SHALL 仅为 `all`、`d02`、`d03`，未传时 SHALL 按 `all` 处理。`prefill_scope` SHALL 仅在 `mode` 为 `prefill` 时生效，SHALL NOT 影响 `mode` 为 `review` 的响应。`all` SHALL 抽取全部四组；`d02` SHALL 抽取 `contract_info`、`contract_plan` 与 `finance_info`；`d03` SHALL 抽取 `finance_info` 与 `guarantee`。**`finance_info` SHALL 由 `d02` 与 `d03` 两个 scope 共同返回** —— 它承载 `contract_amount` 与 `currency`，按「基础信息」归属，使 `d02` 的消费方在只拿到 `contract_plan[].payment_amount` 比例原文（如 `"50%"`）时，仍能取得合同总额以自行折算，SHALL NOT 要求消费方为此额外调用 `d03`。未被请求的组 SHALL 仍出现在 `data.prefill` 中且 SHALL NOT 省略键，并按未取到规则表达（标量字段为 `null`、数组为空数组）；系统 SHALL NOT 为"未被请求"引入区别于"未取到"的第三种表达。

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

#### Scenario: 文件入口同样支持预填

- WHEN 调用 `POST /api/v1/contract-review/upload-md`
- AND 表单字段 `mode` 为 `prefill`
- THEN 系统 SHALL 只执行预填链路并 SHALL NOT 执行组织评审链路
- AND 响应 `data` SHALL 与 JSON 入口在相同 `mode` 与 `prefill_scope` 下完全一致

#### Scenario: 文件入口不传 mode 时行为不变

- WHEN 调用 `POST /api/v1/contract-review/upload-md`
- AND 表单字段不含 `mode`
- THEN 系统 SHALL 按 `mode=review` 处理
- AND 响应 SHALL 与本次改造前逐字段一致

#### Scenario: 文件入口 mode 取值非法

- WHEN 表单字段 `mode` 取值不是 `review` 或 `prefill`
- THEN 系统 SHALL 返回错误码 `10001`
- AND 系统 SHALL NOT 执行组织评审链路或智能预填链路

#### Scenario: 预填形态下单独上传的附件不参与抽取

- WHEN 调用 `POST /api/v1/contract-review` 且 `mode` 为 `prefill`
- AND 请求体包含 `attachments`
- THEN 系统 SHALL 正常接收该字段
- AND 系统 SHALL NOT 使用附件内容参与字段抽取
- AND 调用 `POST /api/v1/contract-review/upload-md` 时，表单字段 `attachment_files` SHALL 同样被接收并被忽略

#### Scenario: 正文内嵌的附件视同正文参与抽取

- WHEN 合同正文 Markdown 内部含独立的附件章节标题（如 `附件一`）
- AND `mode` 为 `prefill`
- THEN 系统 SHALL 把该章节视同正文一并抽取
- AND 系统 SHALL NOT 为附件切分或剔除正文内容

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

#### Scenario: d02 同时返回合同总额与付款比例

- WHEN 调用 `POST /api/v1/contract-review` 且 `mode` 为 `prefill`、`prefill_scope` 为 `d02`
- THEN 系统 SHALL 抽取 `contract_info`、`contract_plan` 与 `finance_info`
- AND `data.prefill.finance_info` SHALL 包含 `contract_amount` 与 `currency`
- AND `data.prefill.guarantee` SHALL 为空数组
- AND `data.prefill` SHALL 仍包含 `contract_info`、`contract_plan`、`finance_info`、`guarantee` 四组
- AND 系统 SHALL NOT 对 `contract_plan[].payment_amount` 的比例原文做折算

#### Scenario: prefill_scope 取值非法

- WHEN 请求体的 `prefill_scope` 取值不是 `all`、`d02` 或 `d03`
- THEN 系统 SHALL 返回错误码 `10001`
- AND 系统 SHALL NOT 执行智能预填链路

#### Scenario: prefill_scope 不影响评审链路

- WHEN 请求体的 `mode` 为 `review` 且携带 `prefill_scope`
- THEN 响应 `data` SHALL 与未携带该参数时逐字段一致
- AND 系统 SHALL NOT 因该参数改变评审链路行为或新增任何字段

### Requirement: 预填字段数据契约

系统 SHALL 在 `data.prefill` 中返回四组结构，共 26 个返回字段：`contract_info`（对象，9 个字段）、`contract_plan`（数组，每项 8 个字段）、`finance_info`（对象，2 个字段）、`guarantee`（数组，每项 7 个字段）。**26 为去重后的字段总数** —— 其中 `finance_info` SHALL 由 `d02` 与 `d03` 两个 `prefill_scope` 共同返回（见「智能预填调用形态」），字段集合与取值口径不因归属调整而变化。系统 SHALL NOT 在预填响应中省略任何键。

- `contract_info` SHALL 包含 `payment_terms`、`payment_method`、`service_content`、`service_valid_months`、`service_sla`、`service_start_date`、`service_end_date`、`onsite_service_count`、`inspection_count`。
- `finance_info` SHALL 包含 `contract_amount`、`currency`。
- **除 `milestone_seq` 外的全部业务字段 SHALL 为字符串**，`milestone_seq` SHALL 为整数，且 SHALL 是响应中唯一的非字符串业务字段。
- **默认口径（适用于绝大多数字段）：内容 SHALL 为合同原文的原样摘录** —— 系统 SHALL NOT 归一日期格式、SHALL NOT 补齐或截断小数位、SHALL NOT 增删任何字符。**下列字段为例外，按其各自的专项规则取值**：三个金额型字段（见下条）、`finance_info.currency`（见下条）、`milestone_name` / `milestone_code`（按 13 名标准清单映射，见「合同计划抽取与里程碑归一」）。**除这些例外外，系统 SHALL NOT 剥离任何符号。**
- **金额型字段的取值例外（2026-10-03 第十五轮）**：`contract_plan[].payment_amount`、`finance_info.contract_amount`、`guarantee[].amount` 三个字段 SHALL 剥离货币符号（`¥` `￥` `$` `€` `£`）、币种词（`元` `人民币` `RMB`）与千分位分隔符；**除这三个字段外，系统 SHALL NOT 剥离任何符号**。
- 上述三个字段剥离后 SHALL 保留 `%`、小数点及其后原样小数位、数量级单位（`万` `亿`）。系统 SHALL NOT 做任何换算 —— SHALL NOT 把 `万` 折算为 ×10000、SHALL NOT 把比例折算为金额、SHALL NOT 把中文大写数字转为阿拉伯数字。
- 金额 SHALL 优先取原文中的阿拉伯数字写法；合同仅以中文大写书写金额时，该字段 SHALL 返回该大写原文。
- 合同以 `【】` 等填空标记书写量值时，取值 SHALL 去掉标记本身、并保留其前后紧邻的单位、货币符号与量纲；系统 SHALL NOT 返回缺少单位或量纲的裸数字 / 裸量词（如 SHALL NOT 把「…之日起【两】年」返回为 `"两"`）。本条与金额型例外**串联适用、不互相抵消** —— 金额型字段先去标记并保留紧邻符号，**再**按金额型例外剥离符号（如 `¥：【763200】元` → 去标记得 `¥763200元` → 剥符号得 `"763200"`，与本条"保留货币符号"不矛盾）。
- `finance_info.currency` SHALL 为 ISO 4217 三位大写字母代码（如 `CNY` / `USD` / `JPY`），按合同原文的币种判定后归一；系统 SHALL NOT 返回原文的币种表述（如 `"人民币"`），也 SHALL NOT 固定为某一取值。
- 取值口径由合同系统自行消化：系统 SHALL NOT 代替调用方决定金额是否折算、日期是否转绝对时间。
- `plan_finish_date` 与 `plan_payment_date` SHALL 为字符串，其值 SHALL NOT 被假定为可解析日期 —— 可能是绝对日期、相对表述或**事件起算**（如 `"自合同签订之日起120天（自然日）内"`）。系统 SHALL NOT 为其做任何日期计算或推算。
- `service_start_date` 与 `service_end_date` 亦 SHALL 为字符串，但取值规则**比一般日期字段更严**：每个字段**只有在符合其来源规则且原文给出绝对日期时才有值**；以事件起算或相对表述给出的，该字段 SHALL 为 `null`（系统 SHALL NOT 照抄该表述）。系统 SHALL NOT 为其做任何日期计算或推算。
- 上述两个字段的取值 SHALL **先按合同类型分路**（2026-10-05 第十六轮）：
  - **合同类型 SHALL 由合同名称判定，判据从宽**：合同名称（正文最前面的合同标题，通常是一级标题，如「…运维服务合同」）中出现**服务性质词** —— `服务` / `运维` / `运营` / `维护` / `技术支持` —— 之一时，SHALL 判为**服务类合同**；名称中看不出服务性质、**或根本读不到合同名称**时，SHALL 一律判为**非服务类合同**。⚠️ 以下词 **SHALL NOT 被视为服务性质词**（2026-10-07 按"软件公司的服务类合同"两轮收窄）：`开发` / `咨询` / `设计` / `集成` / `实施` / `监理` / `勘察` / `检测` / `评估` / `外包` / `培训` —— 它们本身不表示"持续投入人力或技术为对方提供服务"，其标的多为**一次性交付成果**、**劳务事项**或属**独立的合同类型**；**单凭**这些词不得判服务类，如「技术开发合同」「技术咨询合同」「设计合同」「系统集成合同」「软件实施合同」「外包合同」「培训合同」SHALL 判为**非服务类**，名称含「技术」二字亦不因此归服务类。⚠️ 但反例词**没有否决权**：名称中只要出现「服务」二字，SHALL 一律判为**服务类**，含「集成」等反例词的复合名亦然 —— 如「集成**服务**合同」「设计**服务**合同」「服务**外包**合同」SHALL 均判为**服务类**。系统 SHALL NOT 依据正文内容改判，SHALL NOT 为此新增响应字段或请求参数（调用方当前亦不传合同类型）。
  - **非服务类合同**：`service_start_date` 与 `service_end_date` 的来源 SHALL 限定在服务 / 售后 / 质保条款内，且只取绝对日期；系统 SHALL NOT 用合同内其他绝对日期（开发完成日、履行期限条款中的日期等）顶替。此时两者 SHALL 同为 `null` 或同为有值。
  - **服务类合同**：`service_end_date` 在上列条款取不到绝对日期时，SHALL 允许取**合同自身的完成 / 交付截止日**（如「开发内容在【2018】年【11】月【30】日完成」）；`service_start_date` 仍 SHALL 只从上列条款取绝对日期，取不到即 `null`，SHALL NOT 用合同签订日等其他日期顶替。此时 SHALL **允许** `service_start_date` 为 `null` 而 `service_end_date` 有值。
  - 两类共同：合同以「事件起算 + 期限」表述（如「自初验合格之日起两年」）而未给出绝对日期时，对应字段 SHALL 为 `null`；系统 SHALL NOT 据期限推算绝对日期。
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

#### Scenario: 日期与金额按原文原样返回

- WHEN 合同原文以 `2025年3月1日` 写服务开始时间、以 `¥10,492,500.00` 写合同额
- THEN `service_start_date` SHALL 为 `"2025年3月1日"`
- AND `contract_amount` SHALL 为 `"10492500.00"`（金额型字段按其例外剥离符号，数字与小数位不变）
- AND 系统 SHALL NOT 将日期归一成 `2025-03-01`
- AND 系统 SHALL NOT 改变 `contract_amount` 的数字部分与小数位

#### Scenario: 数值类字段一律字符串

- WHEN 合同原文写 `13.5个月`、`1年` 或 `¥ 4690000元`
- THEN 对应字段 SHALL 返回字符串
- AND `service_valid_months` SHALL 为 `"13.5个月"` / `"1年"`（非金额型，原文原样）
- AND `contract_amount` SHALL 为 `"4690000"`（金额型，剥离符号与币种词）
- AND 上述字段 SHALL NOT 为 JSON number 类型
- AND 系统 SHALL NOT 因原文写的是小数（如 `13.5`）而报错或降级

#### Scenario: 计划类日期字段未必是可解析日期

- WHEN 合同原文以相对表述或事件起算写计划完成时间（如 `"自合同签订之日起120天（自然日）内"`）
- THEN `plan_finish_date` SHALL 原样返回该表述
- AND 系统 SHALL NOT 将其归一成绝对日期，也 SHALL NOT 因其不可解析而置为 `null`
- AND 本条 SHALL NOT 适用于 `service_start_date` / `service_end_date` —— 后两者见「非服务类合同的服务日期来源」与「服务类合同的服务结束时间可取自合同完成日」

#### Scenario: 金额以比例约定时不折算

- WHEN 付款条件只写"支付合同款总额的 50%"而未写具体金额
- THEN `payment_amount` SHALL 为 `"50%"`
- AND 系统 SHALL NOT 按合同额换算出具体数字
- AND 该比例中的 `%` SHALL 保留，SHALL NOT 退化为 `"50"`

#### Scenario: 金额型字段剥离货币符号与千分位

- WHEN 合同原文写 `¥10,492,500.00`、`¥ 4690000元` 或 `¥：【763200】元`
- THEN 三个金额型字段 SHALL 分别返回 `"10492500.00"`、`"4690000"`、`"763200"`
- AND 返回值中 SHALL NOT 出现货币符号、币种词与千分位分隔符
- AND 数字部分与小数位 SHALL NOT 被改变

#### Scenario: 金额字段保留比例小数与数量级

- WHEN 合同原文写 `50%`、`13.5` 或 `46.9万元`
- THEN 对应金额型字段 SHALL 分别返回 `"50%"`、`"13.5"`、`"46.9万"`
- AND 系统 SHALL NOT 把 `"50%"` 退化为 `"50"`
- AND 系统 SHALL NOT 把 `"46.9万"` 换算成 `"469000"` 或 `"46.9"`

#### Scenario: 仅以中文大写书写金额

- WHEN 合同仅以中文大写书写金额（如 `柒拾陆万叁仟贰佰元整`）而未写阿拉伯数字
- THEN 该金额型字段 SHALL 返回该大写原文
- AND 系统 SHALL NOT 将其转换为阿拉伯数字

#### Scenario: 填空标记内的取值自带单位

- WHEN 合同以填空标记书写量值（如「免费质量保证期为从系统初验合格之日起【两】年」）
- THEN `service_valid_months` SHALL 为 `"两年"`
- AND 系统 SHALL NOT 只返回标记内的 `"两"`
- AND 系统 SHALL NOT 返回缺少单位或量纲的值
- AND 本例**仅界定取值边界**（不得丢单位），SHALL NOT 被解读为「质保期」等同「服务有效期」的语义结论 —— 该语义映射属业务口径，不在本规格范围内

#### Scenario: 币种归一为 ISO 4217 代码

- WHEN 合同原文分别以 `人民币`、`美元`、`日元` 书写币种
- THEN `currency` SHALL 分别为 `"CNY"`、`"USD"`、`"JPY"`
- AND `currency` SHALL NOT 为原文的币种表述
- AND `currency` SHALL 随合同币种变化，SHALL NOT 固定为单一取值

#### Scenario: 非服务类合同的服务日期来源

- WHEN 合同名称中不含服务性质词（或读不到合同名称）→ 判为**非服务类**合同
- AND 合同只在售后 / 质保条款以「事件起算 + 期限」写服务期限（如「免费质量保证期为从系统初验合格之日起两年」），且合同内另有开发完成日等绝对日期
- THEN `service_start_date` SHALL 为 `null`
- AND `service_end_date` SHALL 为 `null`
- AND 系统 SHALL NOT 用该开发完成日顶替 `service_end_date`
- AND 此时 `service_start_date` 与 `service_end_date` SHALL 同为 `null` 或同为有值，SHALL NOT 仅一侧有值

#### Scenario: 服务类合同的服务结束时间可取自合同完成日

- WHEN 合同名称含服务性质词（如「…运维服务合同」「…平台建设及技术**服务**合同」）→ 判为**服务类**合同
- AND 服务 / 售后 / 质保条款均未给出绝对日期，而合同另有明确的完成 / 交付截止日（如合同中写明的「本项目应于 2020 年 6 月 30 日前完成」）
- THEN `service_end_date` SHALL 为该完成日（如 `"2020年6月30日"`）
- AND `service_start_date` SHALL 仍只从服务 / 售后 / 质保条款取绝对日期，取不到即为 `null`
- AND 此时 SHALL **允许** `service_start_date` 为 `null` 而 `service_end_date` 有值

#### Scenario: 合同名称无法判断时按非服务类处理

- WHEN 合同正文无标题结构、读不到合同名称
- THEN 合同 SHALL 判为**非服务类**
- AND 两个服务日期字段 SHALL 按非服务类规则取值
- AND 系统 SHALL NOT 因正文内容看起来像服务而改判为服务类

#### Scenario: 交付型合同按非服务类处理

- WHEN 合同名称为「技术开发合同」/「技术咨询合同」/「设计合同」/「系统集成合同」/「软件实施合同」之一（名称含「开发」「咨询」「设计」「集成」「实施」等词，亦可能含「技术」）
- THEN 合同 SHALL 判为**非服务类**，SHALL NOT 因上述任一字样或「技术」二字判为服务类
- AND 此时合同内的开发完成日等绝对日期 SHALL NOT 被用作 `service_end_date`
- AND 只有名称含「服务」二字（如「技术服务合同」「运维服务合同」）时方 SHALL 判为服务类

#### Scenario: 含「服务」二字的复合名仍按服务类

- WHEN 合同名称为「集成服务合同」/「设计服务合同」/「软件实施服务合同」/「服务外包合同」之一（名称**同时含**反例词与服务性质词）
- THEN 合同 SHALL 判为**服务类**，SHALL NOT 因名称含「集成」「设计」「实施」「外包」等反例词而改判非服务类
- AND 服务类规则 SHALL 生效（`service_end_date` 可取合同自身的完成 / 交付截止日）
- AND 此判定的依据 SHALL 仅为名称中的「服务」二字 —— 反例词**没有否决权**

#### Scenario: 阶段序号是唯一的整数字段

- WHEN 返回 `contract_plan`
- THEN `milestone_seq` SHALL 为整数
- AND 该字段 SHALL 为 `data.prefill` 中唯一的非字符串业务字段

### Requirement: 合同计划抽取与里程碑归一

系统 SHALL 从付款条件中抽取付款阶段，并为每一阶段返回 `milestone_name`、`milestone_code`、`milestone_text`、`milestone_seq`、`plan_finish_date`、`plan_payment_date`、`payment_amount`、`evidence`。

里程碑名称、描述、序号与 `payment_amount` SHALL 只从付款条件中抽取。两个时间字段的来源固定且互斥：`plan_finish_date` SHALL 按「独立『合同计划 / 进度计划』章节 → 交付 / 验收条款 → `null`」的顺序取，取到即止；`plan_payment_date` SHALL 只取自付款条件中该阶段对应的时间表述。系统 SHALL NOT 为这两个字段做任何日期推算。

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

#### Scenario: 计划完成时间的来源

- WHEN 合同正文存在独立的「合同计划 / 进度计划」章节
- THEN `plan_finish_date` SHALL 取自该章节中该阶段的预计完成时间
- WHEN 不存在该章节但存在交付 / 验收相关条款
- THEN `plan_finish_date` SHALL 取自该条款中该阶段的完成时间
- WHEN 两者均不存在
- THEN `plan_finish_date` SHALL 为 `null`

#### Scenario: 计划回款时间的来源

- WHEN 付款条件写有该阶段对应的时间表述（如"初验后15个工作日内"）
- THEN `plan_payment_date` SHALL 为该表述的原文
- WHEN 付款条件未写该阶段的时间表述
- THEN `plan_payment_date` SHALL 为 `null`
- AND 系统 SHALL NOT 用 `plan_finish_date` 加减推算出日期

#### Scenario: 服务端不做日期推算

- WHEN 合同原文以相对表述或事件起算给出时间（如"自合同签订之日起120天（自然日）内"）
- THEN 相应字段 SHALL 原样返回该表述
- AND 系统 SHALL NOT 换算成绝对日期、SHALL NOT 折算自然日或工作日、SHALL NOT 使用合同签订日期做运算
- AND 金额类字段 SHALL NOT 被推导 —— 原文只写比例时 SHALL 原样返回该比例（见「金额以比例约定时不折算」）

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

`contract_plan` 与 `guarantee` 中的**每一行** SHALL 附 `evidence`，其元素结构 SHALL 为 `{ "section": string | null, "quote": string }`。`contract_plan` 每行的 `evidence` SHALL **固定包含 3 条**，分别对应：① 付款条件、② 合同计划章节或交付 / 验收条款、③ 合同金额条款。

当某处出处**在合同正文中不存在**，或**该处章节存在但不含该字段所需事实**时（2026-10-03 第十五轮 —— 如交付 / 验收条款只写验收流程时限、未写该阶段的预计完成时间），该条 SHALL 为 `{"section": null, "quote": "无"}`。`"无"` SHALL 表示"该处出处无可用于该字段的内容"，SHALL NOT 表示"某字段没有取值"；系统 SHALL NOT 因抽取困难、看不清或不确定而填写 `"无"` —— 只有在通读全文确认原文没有该处内容时才允许。调用方 SHALL 以**全等**方式判定该标记。系统 SHALL NOT 在"该处不含所需事实"时改用该处章节的原文片段。

`section` SHALL 取该条原文所在章节 / 条款的**顶层标题原文**，SHALL NOT 取子层级标题或正文段落；原文无标题结构时 `section` SHALL 为 `null`。系统 SHALL NOT 预设 `section` 的枚举或标题白名单。`quote` SHALL 为取自该位置的原文片段，长度 SHALL NOT 超过 300 字；该长度 SHALL 为**上限而非目标** —— `quote` SHALL 取能完整表达该处内容的最短原文片段（通常为一句），SHALL NOT 为逼近上限而扩大摘录范围。

#### Scenario: 一行字段横跨多处原文

- WHEN 某付款阶段的计划完成时间来自交付条款、回款金额来自合同金额条款与付款条件
- THEN 该行 `evidence` SHALL 固定包含 3 条，分别对应付款条件、合同计划章节或交付 / 验收条款、合同金额条款
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

#### Scenario: 出处不存在时声明「无」

- WHEN 合同正文既无「合同计划」章节、也无交付 / 验收条款的时间约定
- THEN 该行 `evidence` 的时间来源条目 SHALL 为 `{"section": null, "quote": "无"}`
- AND 该行 `plan_finish_date` SHALL 为 `null`
- AND 该行 `evidence` SHALL 仍为 3 条，SHALL NOT 因该处出处缺失而减少

#### Scenario: 出处存在时给出原文片段

- WHEN 某处出处在合同正文中存在
- THEN 该条 `quote` SHALL 为该处原文片段
- AND 该条 `quote` SHALL NOT 为 `"无"`

#### Scenario: 出处存在但不含所需事实

- WHEN 合同既无「合同计划 / 进度计划」章节，交付 / 验收条款也只有验收流程时限（如"交付后 5 个工作日内初验"）、未写该阶段的预计完成时间
- THEN 该行 `evidence` 的时间来源条目 SHALL 为 `{"section": null, "quote": "无"}`
- AND 该行 `plan_finish_date` SHALL 为 `null`
- AND 系统 SHALL NOT 改用该交付 / 验收条款的原文片段充当该条 `quote`
- AND 该行 `evidence` SHALL 仍为 3 条

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
