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
  - **合同类型 SHALL 由合同名称判定，判据从宽**：合同名称（正文最前面的合同标题，通常是一级标题，如「…运维服务合同」）中出现**服务性质词** —— `服务` / `运维` / `运营` / `维护` / `技术支持` / `维保` —— 之一时，SHALL 判为**服务类合同**（⚠️ 2026-10-13 补 `维保`：语义为**维护 + 保养**，符合"持续投入人力或技术为对方提供服务"，属服务性质词）；名称中看不出服务性质、**或根本读不到合同名称**时，SHALL 一律判为**非服务类合同**。⚠️ 以下词 **SHALL NOT 被视为服务性质词**（2026-10-07 按"软件公司的服务类合同"两轮收窄）：`开发` / `咨询` / `设计` / `集成` / `实施` / `监理` / `勘察` / `检测` / `评估` / `外包` / `培训` —— 它们本身不表示"持续投入人力或技术为对方提供服务"，其标的多为**一次性交付成果**、**劳务事项**或属**独立的合同类型**；**单凭**这些词不得判服务类，如「技术开发合同」「技术咨询合同」「设计合同」「系统集成合同」「软件实施合同」「外包合同」「培训合同」SHALL 判为**非服务类**，名称含「技术」二字亦不因此归服务类。⚠️ 但反例词**没有否决权**：名称中只要出现「服务」二字，SHALL 一律判为**服务类**，含「集成」等反例词的复合名亦然 —— 如「集成**服务**合同」「设计**服务**合同」「服务**外包**合同」SHALL 均判为**服务类**。系统 SHALL NOT 依据正文内容改判，SHALL NOT 为此新增响应字段或请求参数（调用方当前亦不传合同类型）。
  - **非服务类合同**：`service_start_date` 与 `service_end_date` 的来源 SHALL 限定在服务 / 售后 / 质保条款内，且只取绝对日期；系统 SHALL NOT 用合同内其他绝对日期（开发完成日、履行期限条款中的日期等）顶替。两个字段 SHALL **各自独立取值**（能取到即取、取不到即 `null`），系统 SHALL NOT 要求两者**同时有值或同时为空**（2026-10-13 第二十四轮：原「必须成对」约束**已废止** —— 该约束源于「起止不成对」这一**诊断启发式**被误当成输出规则）。
  - **服务类合同**：`service_end_date` 在上列条款取不到绝对日期时，SHALL 允许取**合同自身的完成 / 交付截止日**（如「开发内容在【2018】年【11】月【30】日完成」）；`service_start_date` 仍 SHALL 只从上列条款取绝对日期，取不到即 `null`，SHALL NOT 用合同签订日等其他日期顶替。此时 SHALL **允许** `service_start_date` 为 `null` 而 `service_end_date` 有值。
  - **「不得用签订日顶替」的作用域（2026-10-12 第十九轮）**：上一条中「SHALL NOT 用合同签订日等其他日期顶替」的约束 **SHALL 仅作用于 `service_start_date`**，**SHALL NOT 作用于 `service_end_date`**。`service_end_date` 只要在服务 / 售后 / 质保条款内取到**绝对日期**，**即使该日期与合同签订日为同一天，系统 SHALL 返回该日期**（「期限」语义即指截止时点）。系统 SHALL 依据**取值来源是否在服务条款内**判断，**SHALL NOT 因"该值恰等于签订日"而丢弃它**。
  - **日期个数分流（2026-10-12 第十九轮立，2026-10-13 第二十四轮修订）**：服务 / 售后 / 质保条款给出服务期限时，系统 SHALL 以该条款内**绝对日期的个数**为判据分流，**SHALL NOT** 以标题是否含「期限」「有效期至」等字样为判据（**措辞一律不作数**）：
    - **2 个、构成区间**（如「技术服务期限：自2026年09月09日到2027年9月08日」）→ **起点 SHALL 归 `service_start_date`、终点 SHALL 归 `service_end_date`**，**两端均 SHALL 取**；即便标题写「技术服务**期限**」亦然。⚠️ **上例仅为举例、非穷举** —— 区间**前有无引导词**（「技术服务期限：」/ 小节标题「服务周期」/「有效期」/ 无任何引导词）、**系独立小节只写一行、还是嵌于长句**，均 SHALL NOT 影响判定：只要该服务条款（含「服务期限 / 服务周期 / 有效期」等小节）内出现**两个绝对日期构成的区间**（「自 X 到 Y」「X 至 Y」「从 X 起至 Y 止」等），即 SHALL 按区间处理、两端均取。
    - **1 个（单一绝对日期）**→ 系统 SHALL **再读该日期的语义指向**、按方向归位：指向**开始**（如「服务开始日期：X」「服务期自 X 起」）→ 该日期 SHALL 归 `service_start_date`、`service_end_date` SHALL 为 `null`；指向**截止**（如「技术服务期限：X」「有效期至 X」「X 前完成」）→ 该日期 SHALL 归 `service_end_date`、`service_start_date` SHALL 为 `null`（**原第十九轮结论保留，但判据由「带『期限』字样」改为「语义指向截止」**）；**指向不明**（如「服务期：2026年7月」「第二条：2026年5月1日」）→ 两个字段 **SHALL 均为 `null`**（**宁可空、不要错位** —— 错位是静默错误，危害大于空值）。
    - 系统 **SHALL NOT** 因两个日期字段"同在服务条款内"而**对称填充**两个字段。
  - 两类共同：合同以「事件起算 + 期限」表述（如「自初验合格之日起两年」）而未给出绝对日期时，对应字段 SHALL 为 `null`；系统 SHALL NOT 据期限推算绝对日期。
- 未取到的标量字段 SHALL 为 `null`，系统 SHALL NOT 以空字符串占位；`contract_plan` 与 `guarantee` 未取到时 SHALL 为空数组。
- `payment_method` SHALL 抽取**支付手段本体**（如电汇、银行转账、转账、汇票、支票、承兑）—— **只取手段本体**，SHALL NOT 连同围绕它的**介词**（通过 / 以 / 用 / 经由）、**支付动词**（转入 / 支付 / 汇入 / 划付）或**「的方式 / 方式」等结构修饰**一并取入；`payment_terms` SHALL 抽取**完整的付款触发条件句**；两者仅有同一处原文时系统 SHALL NOT 整段重复，支付手段词归 `payment_method`、其余归 `payment_terms`。
- **付款触发条件句的口径（2026-10-12 第十八轮）**：`payment_terms` 的取值 SHALL 是**付款触发条件句**，其结构为【起算锚点】+【期限】+【付款动作】，**起算锚点 SHALL 一并取到**（SHALL NOT 只取"何时付款"的主句而丢弃锚点）。起算锚点 SHALL 可为**时间**（如"合同生效后"）、**交付**（如"交付验收后"）、**验收**（如"终验合格后"）或**发票**（如"收到增值税专用发票后"），四类锚点 SHALL 同等对待 —— **发票锚点与验收锚点语法同构，系统 SHALL NOT 存在"是否包含发票条款"这一区分维度**。判定含发票的文字是否属触发条件，系统 SHALL **只看其前置或后置**：**前置型**（「收到发票后 … 日内付款」）SHALL 视为锚点并取入；**后置型**（「收到付款后开票」）SHALL 视为付款之后的义务、**SHALL NOT** 取入。同一章内**不属于触发条件**的内容系统 SHALL NOT 取入本字段 —— 后置开票义务、银行账号 / 开户行、支付手段词（由 `payment_method` 承接）。

- **第二十轮字段口径修订（2026-10-12）** —— 下列各项由业务方（吴钢 / 王晓丽）或用户逐条定案：
  - **`service_valid_months` 的来源与边界（Q4① / Q7；2026-10-13 第三轮补正 —— 由「字面」改为「语义」）**：本字段 SHALL **按语义**判定来源，SHALL NOT 只认「服务期 / 服务期限」六个字面。语义上即「本合同 / 本次服务的有效期限（服务要持续多久）」的表述 SHALL 取入（原文写法、去 `【】` 标记、保留量纲，SHALL NOT 折算），**含「合同（的）有效期」/「本合同有效期为 N 年」** —— 🔴 **服务类合同**下「本合同有效期为两年」语义即服务期限，本字段 SHALL 为 `"两年"`，系统 SHALL NOT 因字面为「有效期」而返回 `null`。⚠️ 同时给出「服务期」与「合同有效期」时，SHALL 以「服务期 / 服务期限」为准。⚠️ **质保期 / 保修期 / 缺陷责任期 / 保密期 SHALL NOT 视作本字段来源**（属售后质量责任期 / 保密义务期，与"服务持续多久"无关；原文仅写「质保期 2 年」时，本字段 SHALL 为 `null`，SHALL NOT 做该语义映射）。⚠️ 服务期以**起止日期区间**给出（如「2026年1月1日至2026年12月31日」）时，本字段 **SHALL 为 `null`**，系统 **SHALL NOT** 由区间推算月数 / 年数 —— **即使该区间恰好是整年**（如 1 月 1 日至 12 月 31 日），亦 SHALL NOT 返回 `"1年"` 或 `"12个月"`。⚠️ 字段名中的 `months` SHALL NOT 被理解为「须折算为月数」—— 本字段返回**原文写法**（`"两年"` / `"1年"` / `"13.5个月"`）；**反向亦然**：原文写作「13.5个月」时 SHALL 返回 `"13.5个月"`，SHALL NOT 改写为「1年」等其它形式（换算在**两个方向**上均被禁止，原文用什么单位就返回什么单位）。
  - **`inspection_count` 接受频次表述且整句保留（Q4②）**：原文以**频次**形式给出巡检 / 检查要求时（如「例行维护：每周1次系统运行情况检查；每月1次系统安全隐患及故障大排查」），本字段 SHALL 返回**该要求的原文整句**（含频次与事项）；系统 **SHALL NOT** 只截取其中一项，亦 SHALL NOT 只返回数字。
  - **金额 / 比例数值 SHALL 逐字照抄本合同原文（A1）**：三个金额型字段的数值 SHALL 逐字照抄**本合同原文该处**出现的数字；系统 **SHALL NOT** 沿用任何示例值，亦 **SHALL NOT** 套用行业惯例值（如「履约保证金常见 5%」）。原文写「合同总金额的50%」时 SHALL 返回 `"50%"`。
  - **`payment_terms` 的取句与拼接（A2 / Q6 / Q10）**：① 取句 SHALL 保留**完整主语**、SHALL NOT 截断（原文「甲方在合同生效并收到…后…向乙方支付…」SHALL 连同开头「甲方在」一并照抄）；② 合同有**多个付款阶段**时，SHALL **全部取入并按原文顺序拼接**，SHALL NOT 只取首阶段或漏取某阶段；③ 与主付款安排**并列**、但直接约束「是否付款 / 能否拒付」的条款（如「乙方未提交发票的，甲方有权暂不支付合同款且不承担逾期付款违约责任」），SHALL **一并取入本字段**（续在主句之后拼接）。
  - **`payment_method` SHALL 取原文的支付手段本体（Q9；2026-10-13 第二十四轮修订）**：本字段 SHALL 取原文中"钱通过什么付"的**手段本体表述**，SHALL **去掉**包着它的框架词 —— **介词**（通过 / 以 / 用 / 经由）、**支付动词**（转入 / 支付 / 汇入 / 划付）、**「的方式 / 方式」等结构修饰** 一律 SHALL NOT 取入（原文「通过银行转账的方式」SHALL 返回 `"银行转账"`，SHALL NOT 返回 `"通过银行转账的方式"`；原文「甲方以转账方式转入乙方指定账户」SHALL 返回 `"转账"`）。⚠️ **唯一例外**：原文「付款方式：**甲方自带汇票/电汇/支票**」SHALL 返回 `"甲方自带汇票/电汇/支票"` —— 此处「甲方自带」已是该条**唯一**完整表述，去掉会只剩手段词、丢失"由谁以何形式提供"的信息。🔴 本字段 SHALL NOT 被理解为「逐字照抄整句」，亦 SHALL NOT 反向过度简化成与原文无关的词。与 `payment_terms` 同出一处原文时，本字段只取**手段本体**的那一小段，其余归 `payment_terms`，系统 SHALL NOT 整段重复。

- **第三轮复核定案（2026-10-13）** —— 由业务方答复：
  - **里程碑命名口径（Q3 / B7）**：`milestone_name` SHALL **先看该付款条件里有没有约定「成果物」** —— **没有**约定成果物（如「合同生效后 7 个工作日内一次性付清」「合同签订生效之日起 N 个月后付款」）时，该笔 SHALL 视为**预付款**，`milestone_name` SHALL 取 **`启动(begin)`**；**有**约定成果物时 SHALL 按成果物内容取 **`交付(deliver)`** 或 **`验收`**（初验 `preaccept` / 终验 `finalaccept`，按成果物对应的验收环节选）。`contract_plan` SHALL 只从付款条件拆 —— 合同有几个付款阶段即 SHALL 产出几项，系统 **SHALL NOT** 自行追加无付款金额的「收尾 / 验收」里程碑。
  - **保函 `type` 判别（B-1；2026-10-14 收敛）**：按「履约保证金多笔抽取」条的**保函性质判别（2026-10-13 按保函种类表强化；2026-10-14 收敛为「负向参考」）**执行 —— `type` SHALL **只**输出 `履约保函` / `履约保证金` **两类**，其余各类 SHALL **仅作负向参考**（命中即排除、该条不输出）；⚠️ 系统 SHALL NOT 默认归入 `履约保函`。

- **字段级口径补齐（2026-10-14 第四轮 —— 4 个此前只有「原文」二字、无字段级规则的字段）**：
  - **`service_content`（服务内容及方式）**：本字段 SHALL 取原文中**服务内容 / 服务方式**那段的**整段原文**（可含「服务方式 / 服务范围 / 服务要求」）；SHALL 去掉 `【】` 等填空标记；系统 **SHALL NOT 概括、SHALL NOT 只写关键词**；原文没有 → `null`。
  - **`service_sla`（服务级别 / SLA）**：本字段 SHALL 取原文中对**服务级别 / 响应时限 / 可用性（SLA）**的约定**原文**（如「7×24 小时响应」「故障 2 小时内到场」）；SHALL 为原文写法、**SHALL NOT 概括**；原文没有 → `null`。
  - **`onsite_service_count`（现场服务次数）**：本字段 SHALL **只取"次数"** —— 原文以**次数 / 频次**表述现场服务（如「现场服务12次」「每月 1 次」）时 SHALL 返回**原文写法**；原文只写**时长 / 服务时段 / 驻场方式**而**没有次数含义**时（如「5*8小时现场驻场」「7×24小时的响应」），本字段 **SHALL 为 `null`**，系统 SHALL NOT 把时长当作次数；全文无现场服务次数 → `null`。
  - **`milestone_text`（里程碑原文描述）**：本字段 SHALL 为**该付款阶段的原文描述**，SHALL **完整照抄（整句 / 整段）**；系统 **SHALL NOT 概括成短语** —— 把原文一整句概括成「预付款」「尾款」这类词**即为违规**；原文本身即短语时 SHALL 照抄该短语；取不到 → `null`。

#### Scenario: 字段完整返回

- WHEN 合同正文中同时存在可抽取的合同信息、合同计划、财务信息和履约类保函 / 保证金记录
- THEN `data.prefill` SHALL 包含 `contract_info`、`contract_plan`、`finance_info`、`guarantee` 四组
- AND `contract_info` SHALL 包含上列 9 个键
- AND `finance_info` SHALL 包含上列 2 个键

#### Scenario: 字段未取到的表达

- WHEN 合同正文中不存在某一标量字段的可用事实
- THEN 该字段 SHALL 为 `null`
- AND 该字段 SHALL NOT 为空字符串占位
- AND 该键 SHALL 仍然出现在响应中

#### Scenario: 数组类字段无内容

- WHEN 合同正文中不存在付款阶段或履约类保函 / 保证金记录
- THEN `contract_plan` SHALL 为空数组
- AND `guarantee` SHALL 为空数组

#### Scenario: 付款方式与付款条件的边界

- WHEN 合同正文中只有一处章节同时描述支付手段与分期条款
- THEN `payment_method` SHALL 取原文中描述支付手段的**手段本体**（去掉包着它的介词 / 支付动词 / 「的方式」等框架词）
- AND `payment_terms` SHALL 包含**完整的付款触发条件句（含起算锚点）**
- AND 系统 SHALL NOT 将同一整段原文同时填入两个字段

#### Scenario: 付款方式只取手段本体、去掉框架词

- WHEN 原文以**介词框架**给出支付手段（如「甲方…在 30 个工作日内**通过银行转账的方式**向乙方…支付…」）
- THEN `payment_method` SHALL 返回 `"银行转账"`（**只取手段本体**）
- AND 系统 SHALL NOT 返回 `"通过银行转账的方式"`（介词「通过」与「的方式」SHALL NOT 取入），亦 SHALL NOT 只留与原文无关的其它词
- AND 原文「…甲方**以转账方式**转入乙方指定账户…」→ `payment_method` SHALL 返回 `"转账"`
- AND 原文为**独立条款式**表述且该表述无框架词可去时（如「付款方式：甲方自带汇票/电汇/支票」）SHALL 返回 `"甲方自带汇票/电汇/支票"`（该表述已是**唯一**完整表述，SHALL NOT 精简为 `"汇票/电汇/支票"`）
- AND 原文全文**没有任何支付手段字样**时，`payment_method` SHALL 为 `null`，SHALL NOT 凭常识或示例编造

#### Scenario: 付款触发条件的锚点必须一并取到

- WHEN 合同付款条款为「甲方收到乙方开具的增值税专用发票后 30 日内付款」
- THEN `payment_terms` SHALL 包含完整触发条件句（含「收到增值税专用发票」这一**发票锚点**）
- AND 系统 SHALL NOT 只返回「30 日内付款」而丢弃起算锚点
- AND 该类**前置型**发票锚点 SHALL 与「终验合格后 60 日内付款」的验收锚点同等对待，SHALL NOT 因涉发票而区别处理

#### Scenario: 后置型开票义务不进付款条件

- WHEN 合同付款条款为「合同生效后 7 个工作日内一次性付款」且其后另有一句「乙方收到甲方相应付款后开具等额的增值税发票」
- THEN `payment_terms` SHALL 只含付款触发条件句（「合同生效后 7 个工作日内一次性付款」）
- AND 系统 SHALL NOT 把**后置型**开票义务取入 `payment_terms`（该开票发生在付款之后，不构成付款的起算锚点）
- AND 系统 SHALL NOT 把同一章内的银行账号 / 开户行信息取入 `payment_terms`

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
- AND 两个字段 SHALL **各自独立取值** —— 本例两者均为 `null` 的原因是**该条款未给绝对日期**，而非"必须成对"；系统 SHALL NOT 为满足"成对"而丢弃本来能取到的一端（2026-10-13 第二十四轮：原「必须成对」约束**已废止**）

#### Scenario: 服务类合同的服务结束时间可取自合同完成日

- WHEN 合同名称含服务性质词（如「…运维服务合同」「…平台建设及技术**服务**合同」）→ 判为**服务类**合同
- AND 服务 / 售后 / 质保条款均未给出绝对日期，而合同另有明确的完成 / 交付截止日（如合同中写明的「本项目应于 2020 年 6 月 30 日前完成」）
- THEN `service_end_date` SHALL 为该完成日（如 `"2020年6月30日"`）
- AND `service_start_date` SHALL 仍只从服务 / 售后 / 质保条款取绝对日期，取不到即为 `null`
- AND 此时 SHALL **允许** `service_start_date` 为 `null` 而 `service_end_date` 有值

#### Scenario: 服务条款内的绝对日期与签订日相同时仍取作服务结束时间

- WHEN 合同名称含服务性质词 → 判为**服务类**合同
- AND 服务条款（如「乙方应按以下要求完成技术服务工作」）内给出绝对日期（如「2.技术服务期限： 2026年9月4日」）
- AND 该日期**与合同签订日为同一天**
- THEN `service_end_date` SHALL 返回该日期（如 `"2026年9月4日"`）—— 依据是**取值来源在服务条款内**，与它是否等于签订日无关
- AND `service_start_date` SHALL 仍为 `null`（「不得用签订日顶替」这条约束**只作用于 `service_start_date`**）
- AND 该日期系以**单一绝对日期**形态给出（服务条款内**只有 1 个**绝对日期、无配套起始日；
  标题是否写「期限 / 有效期至」**不作判据**）→ 系统 SHALL NOT 把它对称填充进 `service_start_date`
- AND 系统 SHALL NOT 因"该值恰等于签订日"而把 `service_end_date` 也丢成 `null`

#### Scenario: 服务期限以绝对区间给出时两端各归其位

- WHEN 合同名称含服务性质词 → 判为**服务类**合同
- AND 服务条款以**绝对日期区间**给出服务期限（如「2.技术服务期限：自2026年09月09日到2027年9月08日」）
- THEN `service_start_date` SHALL 取区间**起点**（如 `"2026年09月09日"`）
- AND `service_end_date` SHALL 取区间**终点**（如 `"2027年9月08日"`）
- AND 系统 SHALL 以**服务条款内绝对日期的个数**作判据分流（**2 个、构成区间** → 两端各归其位；**1 个** → 按**语义方向**归位，见下一条 Scenario），SHALL NOT 以标题是否含「期限」二字作判据
- AND 即便标题写作「技术服务**期限**」，只要形式是区间，SHALL NOT 只取终点而把起点丢成 `null`
- AND `service_valid_months` SHALL 仍按「起止区间 → `null`」处理 —— **该留空规则只作用于 `service_valid_months`，SHALL NOT 外溢到 `service_start_date` / `service_end_date`**

#### Scenario: 单一绝对日期的归位按语义方向

- WHEN 服务条款只给出 **1 个**绝对日期
- THEN 系统 SHALL 读该日期的**语义指向**归位，SHALL NOT 以标题是否含「期限」字样为判据：
  - 指向**开始**（如「服务开始日期：2026年3月1日」「服务期自 2026年3月1日 起」）→ `service_start_date` SHALL 为 `"2026年3月1日"`，`service_end_date` SHALL 为 `null`
  - 指向**截止**（如「技术服务期限：2026年9月4日」「有效期至 2026年9月4日」）→ `service_end_date` SHALL 为 `"2026年9月4日"`，`service_start_date` SHALL 为 `null`
  - **指向不明**（如「服务期：2026年7月」「第二条：2026年5月1日」）→ 两个字段 SHALL **均为 `null`**（**宁可空、不要错位**）
- AND 上述三种情形均 SHALL NOT 对称填充两个字段

#### Scenario: 合同名称无法判断时按非服务类处理

- WHEN 合同正文无标题结构、读不到合同名称
- THEN 合同 SHALL 判为**非服务类**
- AND 两个服务日期字段 SHALL 按非服务类规则取值
- AND 系统 SHALL NOT 因正文内容看起来像服务而改判为服务类

#### Scenario: 交付型合同按非服务类处理

- WHEN 合同名称为「技术开发合同」/「技术咨询合同」/「设计合同」/「系统集成合同」/「软件实施合同」之一（名称含「开发」「咨询」「设计」「集成」「实施」等词，亦可能含「技术」）
- THEN 合同 SHALL 判为**非服务类**，SHALL NOT 因上述任一字样或「技术」二字判为服务类
- AND 此时合同内的开发完成日等绝对日期 SHALL NOT 被用作 `service_end_date`
- AND 名称含服务性质词时（如「技术服务合同」「运维服务合同」，以及 2026-10-13 补入的「…**维保**合同」）SHALL 判为服务类

#### Scenario: 含「服务」二字的复合名仍按服务类

- WHEN 合同名称为「集成服务合同」/「设计服务合同」/「软件实施服务合同」/「服务外包合同」之一（名称**同时含**反例词与服务性质词）
- THEN 合同 SHALL 判为**服务类**，SHALL NOT 因名称含「集成」「设计」「实施」「外包」等反例词而改判非服务类
- AND 服务类规则 SHALL 生效（`service_end_date` 可取合同自身的完成 / 交付截止日）
- AND 此判定的依据 SHALL 仅为名称中的「服务」二字 —— 反例词**没有否决权**

#### Scenario: 「维保」类合同按服务类处理

- WHEN 合同名称为「…PACS系统**维保**采购项目合同」「…EMR系统**维保**合同」等 —— 名称含「**维保**」但**不含**「服务 / 运维 / 运营 / 维护 / 技术支持」中的任何一个
- THEN 合同 SHALL 判为**服务类**（2026-10-13 补入词表：`维保` = **维护 + 保养**，符合"持续投入人力或技术为对方提供服务"）
- AND 服务类规则 SHALL 生效（`service_end_date` 可取合同自身的完成 / 交付截止日）
- AND 系统 SHALL NOT 因名称未含其余服务性质词、或因其含「采购」二字而判为**非服务类**

#### Scenario: 阶段序号是唯一的整数字段

- WHEN 返回 `contract_plan`
- THEN `milestone_seq` SHALL 为整数
- AND 该字段 SHALL 为 `data.prefill` 中唯一的非字符串业务字段

#### Scenario: 现场服务只有时长时不取值

- WHEN 原文只以**时长 / 服务时段**描述现场服务（如「提供 5*8 小时现场驻场服务」「7×24 小时的响应」），全文并无「现场服务次数」
- THEN `onsite_service_count` SHALL 为 `null`
- AND 系统 SHALL NOT 把 `5*8` / `7×24` 这类时长当作服务次数返回

#### Scenario: 现场服务以频次给出时取原文

- WHEN 原文以次数 / 频次表述现场服务（如「现场服务次数：每月 1 次」）
- THEN `onsite_service_count` SHALL 返回 `"每月 1 次"`（原文写法）
- AND 系统 SHALL NOT 折算成数字或归一为别的写法

#### Scenario: 服务内容以整段原文返回

- WHEN 原文以「服务内容及要求」「服务方式」等段落给出服务内容
- THEN `service_content` SHALL 返回该段落的**整段原文**
- AND 系统 SHALL NOT 概括成短语或只返回关键词

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

#### Scenario: 无成果物约定的付款里程碑取启动

- WHEN 付款条件为「合同生效后 7（七）个工作日内，一次性支付全部费用」（**未约定任何成果物**）
- THEN 该付款阶段对应的 `milestone_name` SHALL 为 `启动`
- AND 其 `milestone_code` SHALL 为 `begin`

#### Scenario: 里程碑数量与付款阶段数一致

- WHEN 合同付款条件共给出 N 个付款阶段
- THEN `contract_plan` SHALL 恰好包含 N 项
- AND 系统 SHALL NOT 自行追加无付款金额的「收尾 / 验收」里程碑（付款共 3 阶段时，SHALL NOT 出现第 4 项）

#### Scenario: 里程碑描述必须照抄完整原文

- WHEN 付款条件以**一整句**描述该阶段（如「第一次付款：签订合同、提交实施方案后 10 个工作日内支付合同款总额的 50%」）
- THEN `milestone_text` SHALL 返回该**整句原文**
- AND 系统 SHALL NOT 概括成「签订及预付款」这类短语（概括即为违规）

### Requirement: 履约保证金多笔抽取

系统 SHALL 从合同正文中抽出**履约保函 / 履约保证金**记录，数量不设上限；每条记录 SHALL 包含 `type`、`amount`、`payee`、`bank_name`、`bank_account`、`return_clause`、`evidence`。🔴 `type` SHALL **只**取 `履约保函` 或 `履约保证金`（2026-10-14 定案）；合同中的其余担保类型（预付款 / 投标 / 质量·质保 / 支付）**SHALL NOT 输出**。合同正文中不存在履约类记录时 `guarantee` SHALL 为空数组。🔴 **`guarantee` 的默认输出 SHALL 为 `[]`**（2026-10-14）。

🔴 **准入闸门（2026-10-14 实跑定案 —— 先过这道闸，再谈类别）**：**只有**当合同里存在**一个「为担保『按约完成合同 / 按期保质交付』而设的、独立的担保条款」**时，本数组 SHALL 输出记录。下列情形**SHALL 一律不过闸门 → 该处 SHALL NOT 输出**：保函 / 保证金**写在「付款」条款里**（作为付款 / 预付款前提或条件）→ 属**预付款**性质；**写在「质保 / 售后」条款里** → 属**质量 / 质保**性质；**写在「招标 / 投标」条款里** → 属**投标**性质。📌 该闸门为**形态判据**（看条款所在章节，不看保函名字），以此保证**可复现**。

**保函性质判别（2026-10-12 Q8；2026-10-13 按业务方「保函种类表」强化；2026-10-14 收敛为「负向参考」）**：`type` SHALL 按**担保标的**判别。下列「保函种类表」三列判据中，**只有履约类可作输出**，其余 **SHALL 仅作负向参考**（命中即排除）：

**【正向 —— 唯一允许输出】**

- **`履约保函` / `履约保证金`**：担保时间段 =「开工至竣工验收（或合同履行期）」；核心保障 =「按期保质完成（施工 / 交付）」；常见金额 =「合同价 5%~10%」—— 即保障**按约完成**的**独立**担保。合同用「履约保证金 / 履约担保金」写法、担保标的同为按期履约时 SHALL 取 `履约保证金`；用「保函」字面则取 `履约保函`。

**【负向参考 —— 命中任一即排除，该条 SHALL NOT 输出】**

- **`预付款保函`**：担保时间段 =「支付预付款起、至预付款扣完为止」；核心保障 =「预付款可追回」；常见金额 =「**等于预付款额**」—— 即**挂在付款条款中、作为预付款前提或扣回担保、且金额等于该笔预付款额**者（如「收到…合同总金额的50%保函后15个工作日内，支付合同总金额的50%作为预付款」）。🔴 **形态判据（照此直接判、不必推断）**：凡保函**出现在付款条款里、且以「支付预付款」为对应条件**者，**一律 SHALL 判为预付款保函 → 该条 SHALL NOT 输出**（**不看名称、不看比例**）。
- **`投标保函`**：担保**投标行为**（投标人不撤标、中标后按约签约）；出现在**招标 / 投标阶段**。
- **`质量保函` / `质保保函`**：担保**质量保证期（质保期 / 缺陷责任期）内的质量责任**；二者是保函种类表中**说明相同的两种类型**；合同用「质量保证金 / 质保金」写法时属本类。
- **`支付保函`**：担保**付款义务**（发包方 / 买方按合同约定付款），保障**收款方按期收款**。

⚠️ 上列负向判据为**实务常见口径**（按担保标的定位），**SHALL 仅用于排除、SHALL NOT 作为输出取值**；保留它们的用意是把「不是履约类」**固化成可复核的判据**，避免语义不清时产生抖动。**不属于上述任何一类、或判不清时，该条亦 SHALL NOT 输出**（宁可空、不要错位）。

🔴 **`[]` SHALL 是常见且正确的输出**：合同没有明确的履约类担保时，`guarantee` SHALL 为 `[]`。系统 **SHALL NOT** 为了「有输出」而把其它担保改标成 `履约保函` / `履约保证金`。

🔴 **禁止「强行归类」（2026-10-14 实跑暴露）**：系统 **SHALL NOT** 因为「这两类之外都不允许」、或「想给出一个结果」，就把**本属预付款 / 投标 / 质量·质保 / 支付类的**保函**改标成** `履约保函`（或 `履约保证金`）—— 这比留空更严重（值合法、内容错）。判别 **SHALL 只看担保标的**（担保的是「按约完成」还是「别的」），**SHALL NOT 因合同用「保函」字面或写成百分比而归入履约保函**，亦 **SHALL NOT 因「找不到别的类别」就默认归入** `履约保函`。

🔴 **`guarantee` SHALL NOT 由非担保条款生成**：**违约责任 / 违约赔偿 / 违约金**条款中的比例或金额**不属于**保函或保证金；合同正文**没有独立的保函 / 保证金 / 担保条款**时，`guarantee` SHALL 为 `[]`，系统 SHALL NOT 把违约金 / 赔偿金 / 扣款标准当作「履约保证金」而生成记录。

⚠️ **schema 取值集合（2026-10-12 Q8 放宽；2026-10-13 扩至「保函种类表」全量）**：`履约保函` / `履约保证金` / `预付款保函` / `投标保函` / `质量保函` / `质保保函` / `支付保函`。🔴 **枚举 ≠ 可选输出值（2026-10-14 定案）**：d03 **SHALL 只输出前两类**；其余 5 类在 schema 中保留，是作**负向参考**用的（见上）。本项 SHALL NOT 新增字段、SHALL NOT 改名、SHALL NOT 改字段集合、SHALL NOT 改类型（仍为 `string | null`）；业务方「保函种类表」内「质量·质保保函」按**两种类型**（`质量保函` / `质保保函`）纳入，`履约保证金`（表内无此项）按**合同实务常见概念**保留。

#### Scenario: 合同包含多笔履约保证金

- WHEN 合同正文中出现多笔履约保证金或保函约定
- THEN `guarantee` SHALL 包含全部记录
- AND 每条记录 SHALL 包含上列 7 个键
- AND `type` SHALL 为 `履约保函` 或 `履约保证金`（其余类型 SHALL NOT 输出）

#### Scenario: 付款条款中的预付款保函不产生记录

- WHEN 付款条款约定「甲方在合同生效并收到乙方的支付申请、发票及**合同总金额的50%保函**后15个工作日内，向乙方支付合同总金额的50%作为预付款」
- THEN 该保函 SHALL NOT 被抽为 `guarantee` 记录（其性质为**预付款保函**，属负向参考类）
- AND `guarantee` SHALL 为空数组
- AND 该「50%」比例 SHALL 仍出现在 `payment_terms` 的付款条件句中

#### Scenario: 保函种类表内其余类型不产生记录

- WHEN 合同在「质量保证期」条约定由乙方提供**质量保函**作为质保期担保（合同未同时出现履约类担保）
- THEN 该保函 SHALL NOT 被抽为 `guarantee` 记录（命中负向参考类：质量 / 质保保函）
- AND `guarantee` SHALL 为空数组
- AND 系统 SHALL NOT 因此把该保函归入 `履约保函`

#### Scenario: 合同不含履约保证金

- WHEN 合同正文中没有履约保证金或保函约定
- THEN `guarantee` SHALL 为空数组

#### Scenario: 违约责任条款不产生 guarantee 记录

- WHEN 合同**无任何保函 / 保证金 / 担保条款**，仅在「违约责任」条写有「乙方…并支付合同总金额【30%】的违约金」
- THEN `guarantee` SHALL 为空数组
- AND 系统 SHALL NOT 因该处出现比例 / 金额而生成 `{"type": "履约保证金", "amount": "30%"}` 记录

### Requirement: 预填原文依据标注章节位置

`contract_plan` 与 `guarantee` 中的**每一行** SHALL 附 `evidence`，其元素结构 SHALL 为 `{ "section": string | null, "quote": string | null }`（2026-10-14 方案 A：`quote` 可空与 JSON schema / 对外接口文档对齐，模型合法输出 `null` 时该条为 `null`，系统 SHALL NOT 因此让整次预填降级）。`contract_plan` 每行的 `evidence` SHALL **固定包含 3 条**，分别对应：① 付款条件、② 合同计划章节或交付 / 验收条款、③ 合同金额条款。

`section` SHALL 为原文**顶层条款标题的逐字原文**（2026-10-12 第二十轮 Q2）—— **SHALL 含原文中的空格与标点**（原文标题以全角冒号「：」结尾时 SHALL 带上冒号；原文「第四条甲方…」中间无空格时 SHALL NOT 加空格）。系统 **SHALL NOT** 对标题做任何规范化：SHALL NOT 增删空格、SHALL NOT 增删句末标点、SHALL NOT 改用其他分隔符或省略序数。

#### Scenario: section 与原文标题逐字一致

- WHEN 原文顶层标题为 `第四条甲方向乙方支付技术服务报酬及支付方式：`（「第四条」与标题正文间**无空格**、以**全角冒号**结尾）
- THEN `evidence[].section` SHALL 返回 `"第四条甲方向乙方支付技术服务报酬及支付方式："`
- AND 系统 SHALL NOT 返回 `"第四条 甲方向乙方支付技术服务报酬及支付方式"`（SHALL NOT 插空格、SHALL NOT 丢冒号）

#### Scenario: 服务期为起止区间时 service_valid_months 为 null

- WHEN 原文「服务周期」以起止日期区间给出（如 `2026年1月1日至2026年12月31日`）
- THEN `contract_info.service_valid_months` SHALL 为 `null`
- AND 系统 SHALL NOT 由该区间推算月数 / 年数（**即使区间恰好是整年**，亦 SHALL NOT 返回 `"12个月"` 或 `"1年"`）

#### Scenario: 服务类合同的「合同有效期」计入服务有效期限

- WHEN 服务类合同写「本合同有效期为两年」作为服务期限，全文无「服务期 / 服务期限」字样
- THEN `contract_info.service_valid_months` SHALL 为 `"两年"`
- AND 系统 SHALL NOT 因该处字面为「有效期」而返回 `null`
- AND 本字段 SHALL NOT 被折算为 `"24"` / `"24个月"`

#### Scenario: 质保期不计入服务有效期限

- WHEN 全文只有「质保期 2 年」这类**质保期**表述、无「服务期 / 服务期限」自身的期限表述
- THEN `contract_info.service_valid_months` SHALL 为 `null`
- AND 系统 SHALL NOT 把质保期映射进本字段

#### Scenario: 巡检频次以原文整句返回

- WHEN 原文写「例行维护：每周1次系统运行情况检查；每月1次系统安全隐患及故障大排查」
- THEN `contract_info.inspection_count` SHALL 返回该要求的**原文整句**（含频次与事项）
- AND 系统 SHALL NOT 只返回数字、SHALL NOT 只截取其中一项

#### Scenario: 多阶段付款全部拼接进 payment_terms

- WHEN 付款条款含两个阶段（如预付款 + 尾款）各自完整的触发条件句
- THEN `contract_info.payment_terms` SHALL **按原文顺序拼接全部阶段的触发条件句**
- AND 每句 SHALL 保留完整主语（原文「甲方在…」SHALL 连同「甲方在」一并照抄）
- AND 系统 SHALL NOT 只取首阶段或漏取某阶段

#### Scenario: 约束付款的并列条款并入 payment_terms

- WHEN 与主付款安排**并列**的条款直接约束「是否付款 / 能否拒付」（如「乙方未提交发票的，甲方有权暂不支付合同款且不承担逾期付款违约责任」）
- THEN 该条款 SHALL **一并取入** `contract_info.payment_terms`（续在主句之后拼接）

#### Scenario: payment_method 的唯一例外（「甲方自带…」保留）

- WHEN 原文付款方式为「甲方自带汇票/电汇/支票」（该表述**无可去的框架词**，是原文对该条支付方式的**唯一**完整表述）
- THEN `contract_info.payment_method` SHALL 返回 `"甲方自带汇票/电汇/支票"`
- AND 系统 SHALL NOT 精简为 `"汇票/电汇/支票"`（去掉「甲方自带」会丢失"由谁以何形式提供"的信息）
- AND 该例外 SHALL NOT 被推广 —— 原文以介词框架给出手段时（如「通过银行转账的方式」）仍 SHALL 只取手段本体、去掉框架词

#### Scenario: 金额比例照抄原文而非套用惯例值

- WHEN 原文写「履约保证金为合同金额的 12.5%」（属履约类、该条会被输出）
- THEN `guarantee[].amount` SHALL 返回 `"12.5%"`
- AND 系统 SHALL NOT 返回 `"5%"`、SHALL NOT 套用「履约保证金常见 5% / 10%」等行业惯例值

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
