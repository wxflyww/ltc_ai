# review-summary Spec Delta

## ADDED Requirements

### Requirement: 评审智能总结接口
系统 SHALL 提供 JSON-only 的 `POST /api/v1/review-summary`，接收评审环节结构化数据，成功响应的 `data` SHALL 是整包面板 JSON（`review_summary`、`key_concerns[]`、`opinion_details[]`、`degraded_sections[]` 四块齐全）。接口 SHALL 受现有鉴权（`X-API-Key`/`Authorization: Bearer`）、Trace 与耗时中间件保护，沿用统一响应壳 `code`/`message`/`traceId`/`duration_seconds`；SHALL NOT 新增错误码、multipart 入口或响应包装层。命名 SHALL 统一为 review-summary，不引入 approval-summary。

#### Scenario: 合法请求返回整包面板
- **WHEN** 调用方以合法鉴权提交包含 `opinions[]` 的合法请求体
- **THEN** 系统 SHALL 返回 `code=0`
- **AND** `data` SHALL 同时包含 `review_summary`、`key_concerns`、`opinion_details`、`degraded_sections` 四个字段
- **AND** 响应 SHALL 携带 `traceId` 与 `duration_seconds`

#### Scenario: 请求体非法
- **WHEN** 请求体缺失 `opinions` 键，或 `action` 为空串（唯一入口约束，见输入契约），或任一必填字段类型错误
- **THEN** 系统 SHALL 返回 `422` 且 `code=10001`
- **AND** 系统 SHALL NOT 发起任何模型调用

### Requirement: 输入契约四组数据
请求体 SHALL 包含四组数据：`contract_meta`（整组可选，字段全 optional，后续 CRM 客户字段以新增可选字段方式向后兼容扩展）、`route_reason`（可选，传入时 `text` SHALL 为非空的合同系统已生成人话原文，空串属未定义格、按非法请求以 422+10001 拒绝）、`risk_register[]`（只含高风险项，12 字段全部"有就照搬、没有就不传"）、`opinions[]`（必填，可为空数组；每条含 `node_name`/`approver_name`/`role`/`action`/`comment` 必填与 `submitted_at` 建议字段；`action` SHALL 为非空字符串——「传过来是啥就是啥」，不枚举、不翻译、不映射，任意原值照单全收并原样回显，5.4 真实联调后的契约转向见 change design.md D7）。通用约定：缺值给空不省键（`null`/`[]`）；所有文本原样传递，接口只引用不加工；接口对数组顺序与内容零要求，不做过滤、重排或业务正确性判断。

#### Scenario: contract_meta 整组缺省
- **WHEN** 请求未提供 `contract_meta` 或其中任一字段
- **THEN** 系统 SHALL 继续生成
- **AND** 总述 SHALL 只引用已传入的字段，缺位不补不问

#### Scenario: opinions 为空数组
- **WHEN** `opinions=[]`（评审未完成）
- **THEN** 系统 SHALL 接受请求并返回成功
- **AND** 该空态按空态矩阵降级，SHALL NOT 以参数错误拒绝

#### Scenario: 新增可选字段向后兼容
- **WHEN** 请求在 `contract_meta` 中携带本 spec 未列出的新增可选字段
- **THEN** 系统 SHALL NOT 因未知可选字段拒绝请求
- **AND** 已定义字段的行为 SHALL NOT 改变

### Requirement: 装配区按传入数据原文回显
`key_concerns[]` SHALL 为有序列表：`route_reason` 传入时提级原因块（`type=escalation`，`text` 原文照搬）固定置首，此为装配规则而非业务加工；风险项（`type=risk`）按传入数组顺序跟排，`risk_register` 全字段照搬并含「处置参考」`measure` 块（`measure_type`+`measure_desc` 原文）；缺值字段在输出 JSON 中 SHALL 以 `null` 回显（键不省略）、SHALL NOT 以占位文案填充，"对应行不渲染"归前端职责。`opinion_details[]` SHALL 按传入顺序逐条输出 `node_name`/`approver_name`/`role`/`action` 骨架字段原文。`level`、`decision_type` 等展示值原样输出，不做枚举映射。

#### Scenario: 提级块置首与风险项跟排
- **WHEN** 请求同时传入 `route_reason` 与 2 条 `risk_register`
- **THEN** `key_concerns[0].type` SHALL 为 `escalation` 且 `text` 与输入逐字一致
- **AND** `key_concerns[1..2]` SHALL 按传入顺序输出两条 `risk` 块

#### Scenario: 风险项缺决策字段
- **WHEN** 某风险项未传 `decision_type`/`decision_by`/`decision_note`
- **THEN** 该风险块对应字段 SHALL 以 `null` 值回显（键不省略，与输入"缺值给空不省键"对称），SHALL NOT 填充任何占位文案
- **AND** `degraded_sections` SHALL NOT 因此标记降级（非降级场景）

### Requirement: AI 生成仅限总述主题与意见摘要两处
响应中 AI 生成的文本 SHALL 只有总述的 `overall` 与 `themes[].text`（对外仍表现为 `review_summary.text` 的组成部分）以及 `opinion_details[].summary`（压缩对应 `comment` 原文、保留其主张与条件）。`comment` 为空的意见 SHALL NOT 参与摘要生成（不进批量输入），其 `summary` 为 `null` 且 SHALL NOT 计入丢弃或触发 `opinion_details.model` 降级标记——真实面板多数评审人只表态不写字，误计将连带缓存旁路失效（change design.md D7）。模型对 `comment` 近空（如"同意。"）的意见**按 prompt 契约显式返回 `summary: null`** 时同样 SHALL NOT 计入丢弃：`opinion_details.model` 只在模型**漏交该 index**（未按逐条对应覆盖输入）时出现（change design.md D14）。其余全部字段 SHALL 为输入原文装配，零 AI 改写：`route_reason` 照搬、`risk_register` 全字段照搬、「处置参考」一律引用清单应对措施原文，AI 对动作、数字、条款与决策零生成，不输出「建议通过/建议驳回」类决策建议。

**总述契约（2026-10-09 契约级重构，change design.md D16/D16.1/D16.2）**：`review_summary.text` SHALL 由服务端按固定句式拼接为 `①合同要素句。②结论分布句。overall。主题1（节点名…）；主题2（节点名…）……`。①② 两句本就确定性，SHALL 由服务端从请求体装配、SHALL NOT 交给模型写作：① 与兜底稿的要素句同源，② 与注入 prompt 的「结论分布」注记**共用同一事实句**（面板、prompt、兜底稿三处不许出现第三份措辞）。主题句后的节点名 SHALL 由服务端从该主题的 `opinion_refs` 反查 `opinions[i].node_name` 去重保序派生（该名字若已被主题句逐字点过则不再重复附），SHALL NOT 由模型自报——归属因此结构性不可能错。模型 SHALL 只提交 `{"overall": str|null, "themes": [{"text": "主题句", "opinion_refs": ["opinions[i]"]}]}`：`themes` 最多 4 条、每条 `opinion_refs` 最多 3 个且只能是指向有字意见的 `opinions[i]` 整下标路径；`overall` 为一句 ≤40 字的态势判断，无话可说时输出 `null`、SHALL NOT 硬凑、SHALL NOT 出现任何节点名。主题句点名**可选**，点则 SHALL 逐字且只能点本主题自己 `opinion_refs` 里的节点。主题句 SHALL NOT 把单条 `comment` 的多个细项用顿号逐条串入（细项完整展开归「各节点意见详情」，change design.md D13 反罗列禁令保留）。归并范围：`comment` 有实质内容的意见（含动作为「通过」但写了关键事实者）在容量内优先全覆盖，超出容量（≤4 主题 × ≤3 refs）时按关键性取舍，未纳入者由 `opinion_details` 逐条承载——主题是**关键性视图**而非全集视图（change design.md D16.2-R5，据此修订 D12 的"凡…即纳入"）。全部意见均无实质内容时 SHALL NOT 硬凑分歧或关注点。

**结构校验与处置阶梯（判据一律为服务端确定性比对，SHALL NOT 采信模型自报）**：
- **G1** 每条主题的 refs 逐条剔除引用清单外的路径（顺序保持、去重），剩 ≥1 条即照常采信该主题，**剩 0 才判违规**（归属变窄不变假，change design.md D16.1-R3）；
- **G2** refs SHALL NOT 指向 `comment` 为空的意见——这是张冠李戴在结构层的等价物（index 唯一，无子串与近形名歧义）；
- **G3** 主题句中出现的节点名（最大匹配扫描，避免短名嵌在长名内误判）SHALL 被该主题自身 refs 反查出的节点名集合**背书**；未背书即违规（结构层为主、文本负向校验为辅，change design.md D16.1-R2/D16.2-R6）。`overall` 没有 refs 可背书，因此适用平禁令：含任何节点名即违规；
- **G4** 有字意见未被任何主题引用 → **只观测**：产出 `uncovered_refs` 与 `covered/total` 计数日志，SHALL NOT 判违规、SHALL NOT 独立触发重试、SHALL NOT 旁路缓存（容量上限下"全覆盖"是结构上不可满足的承诺，服务端 SHALL NOT 惩罚模型遵守契约；change design.md D16.1-R1/D16.2-R5）；
- **代答闸**（正面定性短语在任何一条 `comment` 里都找不到逐字出处，即判"替未填写意见的节点断言立场"，change design.md D16.4）与**数字闸**（逐主题与 `overall`，语料口径见 change design.md D9；判据取全量输入，代答闸只取 `comment`）与 **reject 正面定性闸**（铁律 5 有档）SHALL 保留，且三者同属**内容违规**：丢弃该主题、记日志，但 SHALL NOT 触发重试（重试只会让模型换个说法再写一遍）；
- **结构违规**（输出形状失守即缺 `themes` 键或类型不符、G1 剩 0、G2、G3 未背书）时 SHALL 附带可核验事实清单**定向重试一次**（话术形如"主题 2 的 refs 指向空意见 opinions[2]"，与 D15 的假事实风险本质不同）；首稿与重试稿各跑复检，取复检后合法主题数多者、并列取首稿；仍违规的主题 SHALL **整条丢弃**（不删名、不改句、不用真名替换）并标 `review_summary.incomplete`（内容在、是 AI 写的、覆盖缺一角）；
- 0 条合法主题且有实质输入 → 服务端中性兜底稿 + `review_summary.fallback`（整块缺失 ≠ 覆盖不全，SHALL NOT 打 `.incomplete`）；
- 没有任何有字意见 → 总述 SHALL 只有 ①② 两句、`themes=[]`、SHALL NOT 发起模型调用、该空态由输入决定并 SHALL 可缓存；
- `overall` 单独违规 → 只丢这一句，SHALL NOT 打标记、SHALL NOT 触发重试；
- **同源合并**（change design.md D17）：`opinion_refs` 集合**完全相同**的多条主题 SHALL 由服务端拼接为一条，位置取首次出现处（不重排、不判关键性），连接符 SHALL 用非句末标点以保证合并后的主题在整句裁尾下仍是**原子单位**；SHALL NOT 改写或删去模型写的任何一个字。合并发生在逐主题复检与两稿取优**之后**，故被丢弃的主题不会因同源被救回；合并对四道闸封闭（不引入数字、不跨句拼出正面定性短语、节点名后缀集合不变），因此 SHALL NOT 触发重试、SHALL NOT 打任何降级标记、SHALL NOT 旁路缓存。合并后仍多于 4 条时 SHALL NOT 丢弃任何主题，只产出 `review-summary 容量观测`（记录合并前后条数）；
- 300 字红线 SHALL 作用于**拼接后的全文**（服务端装配部分一并计入）：超长时按整句（一条主题即一句）从尾部裁，裁后仍含完整句子即照常返回、不打标记、照常落缓存；只有裁到不再含任何 AI 成稿（或首两句即放不下）才走兜底稿（change design.md D13/D16.1-I5）。

`review_summary` SHALL 新增响应字段 `themes[] = {text, opinion_refs}`，与 `text` 里的主题片段对应；兜底稿与空态 SHALL 为 `[]` 而非省键（缺值给空不省键）。`source_refs[]` SHALL 改由服务端汇总（要素字段 + 分布聚合路径 `opinions` + 各幸存主题的 refs 去重），SHALL NOT 再采信模型自报的总述引用清单。

#### Scenario: 风险块内容零生成
- **WHEN** 请求包含带 `description`/`standard_clause`/`potential_impact`/`measure_desc` 的风险项
- **THEN** 输出的对应字段 SHALL 与输入逐字一致
- **AND** 系统 SHALL NOT 生成或改写任何应对措施或决策文本

#### Scenario: 总述按主题归并各方关注点
- **WHEN** `opinions` 中存在带实质内容 `comment` 的意见（含动作为「通过」者）
- **THEN** 模型 SHALL 把它们归并成最多 4 个主题，每主题一句、诉求用词沿用 `comment` 原文、数字照抄，并给出该主题的 `opinion_refs`
- **AND** 拼接后的总述 SHALL 在每个主题句后附上由该主题 refs 反查出的节点名，SHALL NOT 采信模型自报的点名
- **AND** 「有条件通过」与「不通过」的诉求 SHALL 出现在归并结果里，SHALL NOT 只写"存在分歧"类笼统句
- **AND** 该主题归并 SHALL NOT 因铁律 2 被判违规（约束对象是风险事实的数字与条款，不含观点）

#### Scenario: 无实质意见内容时不编造关注点
- **WHEN** `opinions` 全部 `comment` 为空，或只写"同意/无异议"类无实质内容的话
- **THEN** 系统 SHALL NOT 为凑内容而编造分歧或关注点
- **AND** 总述 SHALL 只有服务端装配的 ①合同要素 + ②结论分布两句、`themes=[]`，且该请求 SHALL NOT 发起任何模型调用

#### Scenario: 主题引用空意见或点名未背书时先定向重试再整条丢弃
- **WHEN** 某主题的 `opinion_refs` 指向 `comment` 为空的意见（G2），或主题句点名的节点不在该主题 refs 反查出的节点名集合内（G3 未背书），或 refs 剔除清单外路径后剩 0（G1），或输出形状失守
- **THEN** 系统 SHALL 发起**一次**定向重试，重试输入 SHALL 逐条列出可核验的结构事实（哪条主题、哪个引用、哪个名未背书）
- **AND** 首稿与重试稿 SHALL 各跑复检并取合法主题数多者（并列取首稿），SHALL NOT 无条件采信重试稿
- **AND** 仍违规的主题 SHALL 整条丢弃（不删名、不改句、不用真名替换），其余合法主题照常拼接
- **AND** 确有主题被丢弃时 `degraded_sections` SHALL 包含 `review_summary.incomplete`，该响应 SHALL NOT 写入缓存
- **AND** 0 条合法主题时 SHALL NOT 打 `.incomplete`，改走服务端中性兜底稿 + `review_summary.fallback`

#### Scenario: 有字意见未被归并只观测不扳闸
- **WHEN** 某条写了实质内容的意见没有被任何主题的 `opinion_refs` 引用（超出主题容量或模型取舍）
- **THEN** 系统 SHALL 只记录 `uncovered_refs` 与 `covered/total` 观测日志，SHALL NOT 判违规、SHALL NOT 因此触发重试或打降级标记
- **AND** 该意见的内容 SHALL 仍能在 `opinion_details[].summary` 逐条查到，面板不丢信息
- **AND** 模型按契约对"只写同意/无异议"的意见不单独成主题时，SHALL NOT 被服务端判为违约

#### Scenario: overall 单独违规只丢这一句
- **WHEN** 模型返回的 `overall` 含节点名、含语料外数字或在存在「不通过」意见时含正面定性
- **THEN** 系统 SHALL 只丢弃 `overall` 这一句，主题句照常保留与拼接
- **AND** `degraded_sections` SHALL NOT 因此出现任何标记，且 SHALL NOT 触发定向重试

#### Scenario: 超长总述按整句裁尾而不是整段弃用
- **WHEN** 服务端拼接后的总述全文通过全部校验，但字数超过红线 300 字
- **THEN** 系统 SHALL 从尾部按**整句**（一条主题即一句）丢弃直到 ≤300 字，SHALL NOT 输出半句，并照常返回裁后的 AI 文本
- **AND** `degraded_sections` SHALL NOT 出现 `review_summary.model` 或 `review_summary.fallback`，幸存主题 SHALL 照常写缓存
- **AND** 仅当切不出两句、或裁到最后不再含任何 AI 成稿时，才按 AI 稿不可用走兜底稿

#### Scenario: 同一条意见被拆成多条主题时由服务端合并
- **WHEN** 模型返回的主题中有两条或更多条的 `opinion_refs` 集合完全相同（同源拆条）
- **THEN** 系统 SHALL 把它们拼接成一条、位置取首次出现处，全文里每个节点名后缀 SHALL 只出现一次
- **AND** 模型写下的每一句主题文本 SHALL 完整出现在 `review_summary.text` 与幸存的 `themes[].text` 里——一字不删、不改写、不重排、不判关键性
- **AND** 系统 SHALL NOT 因合并打任何降级标记或旁路缓存；合并后仍多于 4 条时 SHALL 照常全部出稿，只产出 `review-summary 容量观测` 日志（含合并前后条数）

#### Scenario: 近空意见的显式 null 摘要不计丢弃- **WHEN** 某意见 `comment` 只有"同意。"这类近空内容，模型按 prompt 契约返回该条 `summary=null`
- **THEN** 该条 SHALL 保持 `summary=null` 且 SHALL NOT 计入丢弃，`degraded_sections` SHALL NOT 出现 `opinion_details.model`
- **AND** 该响应 SHALL 正常落缓存；只有模型漏交该 `index`（未逐条覆盖输入）才算真丢弃

#### Scenario: 沉默短名嵌在有字长名内不再被误判为张冠李戴
- **WHEN** 主题句点名 `二级行业商务评审`（名下有字、且该主题 refs 指向它），而数据里另有一个名字是它子串的沉默节点 `行业商务评审`
- **THEN** 系统 SHALL 以最大匹配扫描取长名，并判定该点名**已被本主题 refs 背书**，SHALL NOT 判违规、SHALL NOT 触发重试
- **AND** 渲染时 SHALL NOT 在主题句后再重复附上同一个名字（缺陷 F 的结构性死循环因此消失）

### Requirement: 防幻觉五条铁律
五条铁律的强制层级：规则 1（限阿拉伯数字 token）、规则 3、规则 5 SHALL 有服务端校验兜底；规则 2、规则 4 为 Prompt 层约束，服务端不强制。规则本身如下：
1. **数字零生成**：金额、比例、期限等一律原文引用，不解析、不换算、不四舍五入、不润色；服务端对两处 AI 生成文本做阿拉伯数字 token 抽验（总述按 `overall` 与每条 `themes[].text` **逐条**抽验）：输出中出现的每个数字 SHALL 在输入原文中逐字存在，否则判该条结论生成失败、按规则 3 的丢弃/降级路径处理；总述侧的数字违规属**内容违规**——丢弃该主题但不触发重试。输入原文 = 规范化请求体 JSON **+ 服务端注入 Prompt 的派生文本**（目前唯一含数字的派生文本是「结论分布」注记里的条数）：模型照抄服务端自己给的数字属于溯源成功，SHALL NOT 判为编造（change design.md D9）；中文数字表述与单位换算改写不在抽验射程（change design.md D6），仅由 Prompt 约束；
2. **事实单点归属**：两处 AI 生成文本对**风险事实**只做话题级引用，不重复展开装配区已有的数字、条款与影响；约束对象是事实而非观点——意见摘要照写人的主张，总述的主题归并与诉求复述同样属观点，SHALL NOT 因本条被判违规（本条与"总述必须点出诉求"是互补而非冲突，见 change design.md D11）；
3. **source_refs 溯源**：每条 AI 结论 SHALL 携带指向输入字段路径的来源引用；服务端校验按结论分档：**总述主题**逐条剔除清单外引用（`opinion_refs` 顺序保持、去重），剩余 ≥1 条合法引用即 SHALL 采信该主题文本；剔除后为空则该主题违规（G1）。引用指向空 `comment` 同样判该主题违规（G2）。幸存主题的 refs 与合同要素字段、`opinions` 聚合路径一起，由**服务端汇总**成 `review_summary.source_refs`，模型自报的总述级引用不再作为校验对象。**意见摘要**仍逐条判定，无引用或引用悬空即丢弃该条（`summary=null`），并标 `opinion_details.model`。两者 SHALL NOT 阻塞装配区返回。总述主题整块不可用（形状失守、重试后 0 条合法主题、裁尾后不含任何 AI 成稿）时 SHALL NOT 输出空白：系统 SHALL 用**服务端中性兜底稿**（只由请求体字段原文与服务端确定性统计拼成，天然通过全部铁律校验；组成为合同要素、意见条数分布、"哪些节点写了字"，SHALL NOT 提风险项——风险由 `key_concerns` 单点承载，change design.md D16.1-I2）填充 `review_summary.text` 并标 `review_summary.fallback`；仅当连兜底素材都不存在（请求除装配区已展示的字段外无可引用事实）时才 `review_summary.text=null` 并标 `review_summary.model`；没有任何有字意见时 SHALL NOT 发起模型调用，只装配 ①② 两句、属空态矩阵、不额外打 `.model`/`.fallback` 标记。喂给模型的输入块 SHALL NOT 注入引用清单之外的派生键——模型只会逐字引用输入里出现过的路径，注入即诱导悬空误杀（change design.md D7）；
4. **总述形容词铁律**：评价性修饰必须可溯源到输入字段原文，溯源不到只说事实；CRM 字段暂缓接入期间总述不写客户评价；
5. **总述与结论分布一致性**：`opinions` 中存在 `action` 逐字为「不通过」的意见时，总述 SHALL 退化为中性陈述，SHALL NOT 出现"整体认可""一致看好"等正面定性；"中性"仅禁正面评价，SHALL NOT 因此省略对否决与附条件诉求的复述——第 ③ 段主题归并照常写，只把评价性用词换成 `comment` 原文的事实说法。扳机词仅「不通过」一词：action 已废除枚举、无翻译层，词表外动作词（如"驳回"）SHALL NOT 触发本闸（fail-open，此口径 SHALL 登记于接口调用文档，见 change design.md D7）。正面定性另有**无出处代答档**（change design.md D16.4，与结论分布无关、常驻生效）：主题句或 `overall` 出现的正面定性短语若在**任何一条 `comment` 原文**中都逐字找不到，SHALL 判该条内容违规——空 `comment` 只证明未填写意见，SHALL NOT 被转述为"无异议/一致认可"，提及未表态节点的合法写法只有"其余节点未填写意见"。两档互不替换：reject 档不管出处、代答档不管分布；判据 SHALL NOT 依赖模型自报，也 SHALL NOT 为此新增输入侧词表（复用第 5 条既有禁用语表）。

#### Scenario: 主题的部分悬空引用被剔除后该主题仍采信
- **WHEN** 某主题的 `opinion_refs` 中既有清单内路径、也有输入中不存在的路径（越界下标或非法形状）
- **THEN** 系统 SHALL 只剔除清单外的那几条，剩余 ≥1 条即 SHALL NOT 弃用该主题
- **AND** 拼接与派生节点名 SHALL 只用剔除后的合法 refs
- **AND** `degraded_sections` SHALL NOT 因此出现 `review_summary.incomplete`/`.fallback`/`.model`

#### Scenario: 主题整块不可用时总述走服务端兜底稿
- **WHEN** 模型输出形状失守（缺 `themes` 键或类型不符），或定向重试后仍没有任何主题通过结构校验
- **THEN** 系统 SHALL 弃用该 AI 稿，改输出服务端中性兜底稿：`review_summary.text` 由请求体字段原文与服务端确定性统计拼成（合同要素、意见条数分布、"哪些节点写了字"）、`source_refs` 指向这些事实、`themes=[]`，SHALL NOT 提风险项
- **AND** `degraded_sections` SHALL 包含 `review_summary.fallback` 且 SHALL NOT 包含 `review_summary.incomplete`
- **AND** 该响应 SHALL NOT 写入缓存，同一输入下次请求 SHALL 重新给模型生成机会
- **AND** `key_concerns` 与 `opinion_details` 装配内容 SHALL 正常返回

#### Scenario: 含编造数字的 AI 结论被弃用
- **WHEN** 模型返回的某条主题/`overall` 或某条意见摘要含有未在输入原文（规范化请求体 JSON + 注入 Prompt 的派生文本）中逐字出现的阿拉伯数字 token（编造或抄错）
- **THEN** 系统 SHALL 判该条结论生成失败：总述侧 → 丢弃该条主题或 `overall`（属内容违规，SHALL NOT 因此触发重试；其余合法主题照常拼接），若因此再没有合法主题则输出服务端中性兜底稿且 `degraded_sections` 含 `review_summary.fallback`；意见摘要 → 该条 `summary=null` 且 `degraded_sections` 含 `opinion_details.model`
- **AND** 装配区内容 SHALL 正常返回，走了兜底稿的响应 SHALL NOT 写入缓存
- **AND** 降级日志 SHALL 只列出缺失的数字 token（而非输出中的全部数字），便于联调定位

#### Scenario: 照抄结论分布注记的条数不算编造
- **WHEN** 主题句或 `overall` 照抄「结论分布」注记中由服务端计算的条数（如"共 11 条意见：通过 9 条"），而该数字未出现在请求体任何字段中
- **THEN** 系统 SHALL 判定抽验通过，总述正常返回，SHALL NOT 触发 `review_summary.model`/`review_summary.fallback` 降级
- **AND** ②结论分布句由服务端装配、与注记同源，因此这一段天然不含语料外数字

#### Scenario: 存在不通过意见时总述中性化
- **WHEN** `opinions` 中存在 `action` 为「不通过」的意见
- **THEN** 总述 SHALL NOT 包含正面定性表述
- **AND** 总述 SHALL 仅为事实列举与分歧的客观陈述
- **AND** 模型给出的主题句或 `overall` 含正面定性时，系统 SHALL 丢弃该条（属内容违规、不触发重试），SHALL NOT 输出空白总述——一条不剩时改由同样满足本条的服务端兜底稿填充

#### Scenario: 词表外动作词不触发中性化闸（fail-open）
- **WHEN** `opinions` 中存在 `action` 为"驳回"等非「不通过」逐字值的意见、且无「不通过」意见
- **THEN** 系统 SHALL 按正常流程生成，SHALL NOT 要求总述退化，面板正常返回（本 Scenario 只锁 reject 档；该句若无 `comment` 出处仍会被代答档拦下，见 change design.md D16.4）
- **AND** 结论分布注记 SHALL 按传入原值计数（如"驳回 1 条"）

#### Scenario: 替未填写意见的节点断言"无异议"被代答抽验拦截
- **WHEN** 主题句或 `overall` 含正面定性短语（如"其余节点无异议"），而全部 `opinions[].comment` 中没有任何一条逐字含该短语
- **THEN** 系统 SHALL 判该内容违规：主题整条丢弃、`overall` 只丢这一句，两者 SHALL NOT 触发定向重试
- **AND** 真丢弃过主题时 `degraded_sections` SHALL 含 `review_summary.incomplete`；只丢 `overall` 时 SHALL NOT 新增任何标记，且该响应 SHALL 照常写入缓存
- **AND** 判据 SHALL 只取 `comment` 拼接体：该短语即便出现在 `risk_register` 或 `contract_meta` 文本中，SHALL NOT 视为出处
- **AND** 某条 `comment` 原文真含该短语时，逐字转述它的主题与 `overall` SHALL 照常采信，SHALL NOT 打任何降级标记
- **AND** 本闸判据是既有禁用语表的**逐字子串**比对，插字变体（如"其余节点无实质异议"）不在其射程内，属如实登记的已知宽松面：系统 SHALL 以只观测日志记录"集体指代 + 语料无出处"片段（change design.md D16.6），并 SHALL NOT 因此丢句、打降级标记或旁路缓存

### Requirement: 空态矩阵与降级标记
系统 SHALL 按设计文档 §5.1 空态矩阵实现全部空态：`risk_register=[]` 且无 `route_reason` 时重点关注为空并标记 `key_concerns`；仅 `route_reason` 缺、`contract_meta` 部分字段缺、风险项缺 `measure_*` 或缺 `decision_*` 均 SHALL NOT 标记降级；`opinions=[]` 时意见详情为空并标记 `opinion_details` 与 `review_summary.opinions`，总述 SHALL 只含服务端装配的 ①合同要素 + ②结论分布两句、`themes=[]`、SHALL NOT 发起模型调用；`opinions` 非空但所有 `comment` 均为空时同样只装配两句、零模型调用，且因评审已提交而 SHALL NOT 打 `opinion_details`/`review_summary.opinions` 标记。`degraded_sections[]` SHALL 只含降级模块名，正常请求为空数组。标记语义 SHALL 分档且三档互斥可辨：`.model` 结尾 = 该区块内容缺失（如 `opinion_details.model`、无兜底素材时的 `review_summary.model`）；`review_summary.fallback` = 总述内容在、但**不是 AI 写的**而是服务端中性稿；`review_summary.incomplete` = 总述内容在、**仍是 AI 写的**，只是有主题未通过结构校验被整条丢弃（覆盖缺一角）。已废弃的 `review_summary.attribution`（文字层归属闸的产物）SHALL NOT 再出现——该闸随 change design.md D16 整体拆除。模型调用失败 SHALL 走统一错误码体系：重试耗尽 `20001`、超时 `20002`、格式异常 `20003`，不新增错误码。

#### Scenario: 无风险无提级
- **WHEN** `risk_register=[]` 且未传 `route_reason`
- **THEN** `key_concerns` SHALL 为空数组
- **AND** `degraded_sections` SHALL 包含 `key_concerns`

#### Scenario: 评审意见为空集
- **WHEN** `opinions=[]`
- **THEN** `opinion_details` SHALL 为空数组
- **AND** `degraded_sections` SHALL 包含 `opinion_details` 与 `review_summary.opinions`
- **AND** 总述 SHALL 为不含评审意见概括的 ①② 两句、`themes=[]`，且该请求 SHALL NOT 发起模型调用、SHALL 可落缓存

#### Scenario: 模型重试耗尽
- **WHEN** 模型调用失败且业务层重试后仍失败
- **THEN** 系统 SHALL 返回 `code=20001`
- **AND** 响应 SHALL NOT 携带部分生成的 `data`

### Requirement: 输入 hash 缓存与模型调用口径
系统 SHALL 对规范化后的请求体计算内容哈希作为缓存键，命中时直接返回既有整包响应；`opinions`/`risk_register` 任何新增变更 SHALL 自动失效缓存，无需合同系统通知。`degraded_sections` 含 `.model` 标记（AI 结论被丢弃）、`review_summary.fallback` 标记（总述走了服务端兜底稿）或 `review_summary.incomplete` 标记（总述有主题被整条丢弃、覆盖缺一角）的响应 SHALL NOT 写入缓存，同一输入下次请求 SHALL 重新生成；空态降级由输入决定，可安全缓存。每次未命中缓存的请求 SHALL 常规发起 2 次模型调用（总述主题稿 + 意见摘要批量）；没有任何有字意见时 SHALL 发起 0 次；仅当总述主题稿有**结构**违规（形状失守/G1 剩 0/G2/G3 未背书）时 SHALL 追加至多 1 次定向重试（3 次为上限，重试不改变对外契约），内容违规（数字、正面定性）SHALL NOT 消耗重试。模型调用 SHALL 与现行能力共用 `get_chat_model()` 单例且只消费 `bind()` 返回的新对象，SHALL NOT 修改 `app/models/llm.py`；关闭思考 SHALL 走 `model.bind(extra_body={"chat_template_kwargs": {"enable_thinking": False}})`；SDK 层 `max_retries=0`，业务层仅解析失败重试 1 次。

#### Scenario: 相同输入命中缓存
- **WHEN** 两个逐字段相同的请求先后到达
- **THEN** 第二次请求 SHALL NOT 发起模型调用
- **AND** 两次响应 `data` SHALL 一致

#### Scenario: 主题被丢弃的响应不写缓存
- **WHEN** 某次响应的 `degraded_sections` 含 `review_summary.incomplete`，或含 `review_summary.fallback`
- **THEN** 系统 SHALL NOT 把该响应写入缓存
- **AND** 同一输入下次请求 SHALL 重新发起生成，SHALL NOT 复用这份缺角的总述

#### Scenario: 意见变更自动失效
- **WHEN** 后续请求在某条 `opinions[].comment` 上有任意改动
- **THEN** 缓存键 SHALL 不同并重新生成
- **AND** 系统 SHALL NOT 返回旧哈希对应的缓存结果

### Requirement: 对既有能力零改动
本能力 SHALL 以独立包 `app/capabilities/review_summary/` 实现，与 `contract_review`、`translate` 零依赖。除 `app/main.py` 新增 router 注册（import + `include_router` 共 2 行）外，SHALL NOT 修改任何既有代码文件；`app/core/` 全部文件、`app/capabilities/contract_review/**`（含 `two_stage/`）、`app/capabilities/translate/**`、`app/models/llm.py`、现有 prompts yaml、现有 config 键与现有测试文件（含 `conftest.py`）SHALL 保持原样。

#### Scenario: 既有接口行为不变
- **WHEN** 新能力注册后调用 `/api/v1/contract-review`（review 与 prefill 两模式）及 `/api/v1/translate`
- **THEN** 请求契约、响应结构与错误码 SHALL 与注册前完全一致

#### Scenario: 回归测试全绿
- **WHEN** 运行 `pytest tests/` 与 `pytest tests/two_stage/`
- **THEN** 现有用例通过数相对立项基线 SHALL 只增不减，失败总数 SHALL NOT 因本 change 增加（已知环境性失败见 tasks.md §0/§6 登记）
- **AND** 新增 `tests/test_review_summary_*.py` SHALL 全部通过
