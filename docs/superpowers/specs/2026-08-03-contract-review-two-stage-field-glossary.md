# 合同评审两阶段字段中英文对照表

> 状态：两阶段升级辅助阅读文档，持续更新；Prepare 已进入 OpenSpec，Evaluate 仍处于方案阶段。
>
> 更新日期：2026-08-26
>
> 作用：集中解释两阶段方案中出现的英文字段、类型名和枚举值，减少中文业务含义与英文技术命名之间的理解偏差。
>
> 权威边界：本文不单独定义接口契约。升级业务方案以 [`2026-07-28-contract-review-two-stage-upgrade-draft.md`](./2026-07-28-contract-review-two-stage-upgrade-draft.md) 为设计权威；Prepare 字段契约以当前 `contract-review-prepare-api` OpenSpec 为字段级权威，代码实现完成后再由正式 Schema 落地；Evaluate 字段契约仍待后续 OpenSpec。本文与权威来源不一致时，必须修订本文，不能反向覆盖权威契约。

## 1. 状态标记

| 标记 | 含义 |
|---|---|
| 已实现基础 | 已归档 `contract-review-context-foundation` 中存在的基础信封，但可能在 prepare OpenSpec 中进一步强类型化 |
| OpenSpec 已定稿 | 已进入当前 OpenSpec 的规格或设计，属于实现权威；不表示代码已经完成 |
| 方案已确认 | 已在方案讨论中确认；是否已进入 OpenSpec 必须结合具体条目说明，不再默认等于“尚未写入 OpenSpec” |
| 讨论中 | 业务原则或部分结构已确认，但字段名、类型或完整枚举仍待确认 |
| 尚未展开 | 只确认了责任域，尚未进入字段级讨论 |
| 第二阶段派生 | 不由第一阶段持久化，管理员触发 `evaluate` 时根据事实计算 |

## 2. 流程、接口与文档术语

| 英文术语 | 中文含义 | 状态/说明 |
|---|---|---|
| `OpenSpec` | 工程变更的提案、设计、规格和任务文档体系 | `contract-review-prepare-api` 已创建并完成设计定稿，代码尚未实现 |
| `Brainstorming` | 方案头脑风暴和需求澄清阶段 | Prepare 已完成；Evaluate 及后续治理能力仍可处于此阶段 |
| `Explore` | OpenSpec 立项前的调查和方案探索阶段 | Prepare 已完成；Evaluate 方案仍按需在此阶段收口 |
| `Propose` | 创建 OpenSpec 变更及正式工件的阶段 | `contract-review-prepare-api` 已完成该阶段 |
| `prepare` | 第一阶段“材料准备”：提取事实、证据、来源清单和准备问题 | 不输出正式审核结论 |
| `evaluate` | 第二阶段“正式检查”：由合同管理员触发，基于固定 `ReviewContext` 输出检查结果 | 首期按同步接口设计 |
| `ReviewContext` | 合同评审上下文：某一合同版本的不可变事实与证据快照 | 基础信封已实现；Prepare 强类型字段已由当前 OpenSpec 定稿，代码实现待完成 |
| `JSON` | 接口使用的结构化数据格式 | 新 prepare 首期只接受 JSON |
| `JSON-only` | 只提供 JSON 请求入口 | 不新增 prepare 的 multipart 入口 |
| `multipart` | 同一个 HTTP 请求中上传多段表单或文件的格式 | 仅说明旧接口形态，新 prepare 首期不采用 |
| `Markdown` | 文档解析服务输出、第一阶段实际消费的合同文本格式 | 合同系统负责保存 |
| `P95` | 95% 请求能在该时长内完成的性能分位指标 | 只有实测证明必要时才评估第二阶段异步化 |
| `PASS` | 正式检查通过 | 只允许第二阶段输出 |
| `WARN` | 正式检查提示或需要人工判断 | 只允许第二阶段输出；合同系统自行决定确认、流转、拦截和留痕，Evaluate 不自动升级为 `FAIL` |
| `FAIL` | 正式检查失败或阻断 | 只允许第二阶段输出 |
| `business outcome` | 业务展示结论 | `PASS/WARN/FAIL` 分别固定展示为“通过/提示/硬阻断”，不得相互矛盾 |
| `result producer` | 结果生产方 | Evaluate 返回固定生产方标记，使合同系统或第三方汇总方能够识别该批结果来自本项目；不表示本项目接收第三方结果 |
| `ruleset` | 规则包 | 本项目实际执行的一组检查点；首期只有内置默认规则包，未来可增加合同类型专用规则包 |
| `ruleset version` | 规则包版本 | 不可变地标识本次规则包包含的检查点范围；首期由本项目确定并在结果中返回，不开放调用方在线编辑或回退 |
| `evaluation engine version` | 执行引擎版本 | 标识执行本次规则的代码、Prompt 和处理逻辑版本；与规则包版本分开记录 |
| `ruleset activation compatibility` | 规则包激活兼容门槛 | 规则包所需事实必须已由生产版本 `ReviewContext` 稳定提供；新增规则需要扩展事实域时，先完成 Prepare 数据契约扩展及 Prepare–Evaluate 兼容验证，再启用规则 |
| `context regeneration` | 同一文件快照重建上下文 | Prepare 数据契约或流水线升级时，可用已保存的相同完整 Markdown 快照重新 Prepare；合同版本和文件摘要不变，生成新的不可变 `ReviewContext`，用户无需重新上传 |
| `context refresh required` | 需要刷新审核上下文 | 当前上下文自身真实、完整且合同版本匹配，但不满足已激活规则包的事实兼容要求时，Evaluate 在正式检查前返回的机器可识别控制信号；与正常审核结果和请求失败互斥，不产生正式结果、检查点、明细、问题、证据或结果数量，也不在 Evaluate 内补做 Prepare，并需关联当前文件快照、当前上下文和目标规则包版本 |
| `latest active ruleset on reevaluation` | 重新检查使用最新激活规则包 | 同一合同版本再次检查时以当时已激活的最新规则包为目标；上下文不兼容则先由调用方自动刷新再重试，不允许回退执行历史规则包 |
| `ruleset-scoped completion` | 规则包范围内完成 | “全部检查完成”只证明本项目本次规则包内的检查均已处理，不代表调用方完成第三方结果汇总后的企业级合同审核 |
| `check_key` | 检查点稳定标记 | 在本项目这一固定结果生产方内全局唯一；同一业务检查点职责未发生实质变化时跨规则包版本保持稳定，不使用旧 `SeqN/B-1/B-4` 作为新接口主键 |
| `legacy_ref` | 旧检查标识追溯信息 | 合同系统确有兼容需要时返回旧 `SeqN/B-1/B-4`，不决定新接口结构 |
| `reason_key` | 原因稳定标记 | 在所属 `check_key` 内唯一；同一原因类型不因中文话术、证据数量或严重程度变化而改变，调用方以 `check_key + reason_key` 识别原因类别 |
| `issue_key` | 当前文件快照具体问题稳定标记 | 仅用于 `WARN/FAIL` 的独立具体问题；以 `contract_id/revision_id/document_set_hash` 和检查点、被检查对象、原因类型、业务发生位置或关系共同确定，不以 `context_digest` 为边界；同一文件快照重新 Prepare 且业务坐标未变时保持稳定，具体编码和算法由 Evaluate OpenSpec 定稿 |
| `issue business identity` | 具体问题业务身份 | 管理员会作为同一处问题处理时身份相同；文案、证据数量或顺序及单纯等级变化不改变身份，检查点、对象、原因类型或业务发生位置/关系实质变化时形成新问题 |
| `issue identity vs waiver` | 问题身份与人工放行分离 | `issue_key` 相同只表示同一处具体问题，不代表历史人工放行自动继续有效；放行保存、规则升级后是否重新确认及最终流转均由合同系统决定 |
| `per-issue outcome` | 具体问题等级 | 每个 `issue_key` 分别保留自己的 `WARN/FAIL`；顶层“检查点 × 被检查对象”结果取其中最严重等级 |
| `pass detail` | 通过明细 | 对已经独立核验通过的业务断言逐条保留 `reason_key`、主体/字段/关系等业务坐标、业务说明和对应合同原文证据，不生成 `issue_key`，不依赖数组位置或证据顺序区分 |
| `mixed result details` | 混合结果明细 | 同一“检查点 × 被检查对象”可同时保留通过明细、`WARN/FAIL` 具体问题和不适用明细；顶层等级不覆盖或删减较轻明细 |
| `comparison target` | 一致性检查的待校验对象 | 多来源一致性问题只挂在预先定义的待校验对象下返回一次；其他对象是比较基准和证据，不反向生成重复问题 |
| `partial evaluation` | 部分检查结果 | 仅返回不受阻条件影响的正式结果；受影响检查点为“暂未完成审核”，不生成整份合同总结果 |
| `full evaluation scope` | 全量检查范围 | 每次 Evaluate 执行本次规则包内全部现有有效检查点，不接收调用方指定的局部检查点清单；新旧结果对比由调用方负责 |
| `external result aggregation` | 外部结果汇总 | 本项目不调用、接收或合并第三方法务产品结果；合同系统或第三方调用方在本项目之外完成汇总、去重和企业级总结果 |
| `check applicability` | 检查点适用状态 | 每个检查点先判断是否适用；合同明确没有检查对象或前提时，返回可追溯的“不适用”检查项 |
| `not-applicable check item` | 不适用检查项 | 不是 `PASS/WARN/FAIL` 的第四种正式结论；保留 `check_key`、被检查对象或缺失对象说明、`reason_key` 和业务话术，不计入三档结果数量 |
| `not-applicable detail` | 不适用明细 | 检查点整体适用但具有独立业务意义的可选分支不适用时明确返回；保留原因和业务坐标，无等级、无 `issue_key`，不展开内部底层条件，也不参与顶层等级和数量汇总 |
| `result detail aggregation` | 结果明细汇总 | 至少一条明细适用并完成裁决时，顶层取适用明细中最严重的 `PASS/WARN/FAIL`；全部独立业务明细均不适用时顶层为“不适用”；覆盖不足不得冒充不适用 |
| `incomplete mixed check` | 检查点内部分未完成 | 只要一条适用且必需明细未完成，顶层即为“暂未完成审核”且无 `PASS/WARN/FAIL`；未完成原因保留受影响业务坐标但不生成 `issue_key`，已完成明细及证据继续保留但不纳入整份合同汇总 |
| `result count dimensions` | 结果数量维度 | 区分规则包内不同检查点数量、按被检查对象展开后的顶层结果项数量、`WARN/FAIL` 具体问题数量及已完成顶层结果的三档汇总数量；不适用和暂未完成不计入三档汇总 |
| `sequence-7 amount writing validation` | 序号7金额书写核验 | 消费主合同中所有适用金额对象的数字金额、大写金额和证据，包括付款阶段金额；缺少一侧或大小写不一致均只归序号7，不在序号10重复返回 |
| `sequence-10 payment-stage arithmetic validation` | 序号10付款阶段算术核验 | 只消费付款阶段数字金额、比例、合同整体金额关系及证据，检查比例合计和阶段金额算术关系；不得读取大写金额形成序号10结论 |
| `zero-tolerance payment-stage comparison` | 付款阶段零容差比较 | 阶段数字金额与“合同整体金额 × 阶段比例”的精确十进制计算结果存在任何非零差额即为 `FAIL`；不采用舍入容差、近似相等或自动尾差调整 |
| `derived comparison value` | 派生比较值 | Evaluate 为解释确定性裁决计算出的期望金额、合计或差额；可以随正式原因返回，但不是合同原文事实或证据，不得写回 `ReviewContext` |

## 3. prepare 请求字段

| 英文字段 | 中文含义 | 状态/约束 |
|---|---|---|
| `contract_id` | 合同业务标识 | 由合同系统提供，不得为空 |
| `revision_id` | 当前合同版本标识 | 由合同系统提供，不得为空 |
| `main_document` | 当前版本的主合同文档 | Prepare OpenSpec 已定稿 |
| `document_id` | 主合同文档业务标识 | 由合同系统提供，不得为空 |
| `filename` | 文档解析服务返回的原始源文件名 | 不是解析后 Markdown 的派生文件名 |
| `markdown` | 原始文件对应的完整 Markdown 解析结果 | 主合同或已上传附件存在但为空时拒绝请求 |
| `uploaded_attachments` | 当前版本全部有效的已上传附件快照 | 是完整快照，不是本次上传增量；不受“三条”限制 |
| `attachment_id` | 已上传附件的稳定业务标识 | 同一请求内必须唯一 |
| `source_file_sha256` | 原始 PDF、DOCX 等文件二进制内容的 SHA-256 摘要 | 可选；有现成稳定值才透传 |
| `parser_meta` | 文档解析服务元数据 | 可选；不得由合同系统猜测 |
| `parser_name` | 文档解析服务或引擎名称 | `parser_meta` 的可选字段 |
| `parser_version` | 文档解析服务或引擎版本 | `parser_meta` 的可选字段 |
| `parsed_at` | 文档解析完成时间 | `parser_meta` 的可选字段 |
| 标准附件目录 | 首期允许使用安全扫描路径的附件类型集合 | 仅需求说明书、技术规范书、工作说明书、质量标准及逐项经业务审核并进入版本化目录的同义名称；当前未列明同义名称不得启用 |
| 标准附件可靠识别 | 决定附件能否进入安全扫描路径的保守分类 | 至少要求边界可靠、内部身份有证据、正文结构可交叉印证且无身份冲突；文件名、长度或宽泛关键词不能单独触发 |
| 标准附件安全扫描 | 对可靠识别的四类标准附件全文执行的确定性候选扫描 | 覆盖主体/称谓、签署区、法人或授权人、人员身份证关系、签署日期、账户和公司级联系方式；不是正式免检 |
| 标准附件局部提取 | 安全扫描命中后只对带可验证坐标的局部范围执行事实域提取 | 无候选时相关域可完整覆盖且事实为空；目录外或识别不可靠时执行普通完整提取 |

## 4. ReviewContext 顶层字段

| 英文字段 | 中文含义 | 状态/说明 |
|---|---|---|
| `schema_version` | `ReviewContext` 数据结构版本 | 已实现基础；当前值为 `review-context/v1` |
| `source_snapshot` | 本次评审所依据的文档来源快照 | 已实现基础 |
| `shared_facts` | 第一阶段提取的六个公共事实域 | 基础容器已实现；六域强类型结构已由 Prepare OpenSpec 定稿，代码实现待完成 |
| `evidence_index` | 统一证据注册表 | Prepare OpenSpec 已定稿 |
| `preparation_issues` | 跨域或跨文档的准备问题清单 | 强类型结构已由 Prepare OpenSpec 定稿，代码实现待完成 |
| `preparation_meta` | 本次准备流水线的版本、模型和时间等元数据 | 已实现基础 |
| `context_digest` | 完整 `ReviewContext` 规范化后的内容摘要 | 已实现基础；不是业务幂等键 |
| `review_context_id` | 合同系统为已保存上下文生成的关联标识 | 第二阶段请求字段；AI 服务不根据它反查数据 |
| `review_context` | 第二阶段请求携带的完整 `ReviewContext` 快照 | 不得由前端页面重新拼装 |

## 5. 来源快照字段与来源枚举

| 英文字段/类型 | 中文含义 | 状态/说明 |
|---|---|---|
| `SourceSnapshot` | 文档来源快照类型 | 已实现基础 |
| `document_set_hash` | 当前主合同及全部有效附件集合的确定性摘要 | 已实现基础；只反映文档集合 |
| `document_key` | 当前 `ReviewContext` 内唯一、稳定的文档键 | 例如 `main`、`attachment:ATT-001`、`embedded:main:1` |
| `attachments` | 来源快照中的已上传附件和正文内嵌附件清单 | 已实现基础 |
| `source_kind` | 附件来源类型 | 已实现基础 |
| `UPLOADED` | 合同系统单独上传的附件 | `source_kind` 枚举值 |
| `EMBEDDED` | 从主合同 Markdown 中识别出的内嵌附件 | `source_kind` 枚举值 |
| `source_main_document_id` | 内嵌附件所属主合同的 `document_id` | 只用于 `EMBEDDED` 来源 |
| `source_locator` | 原文位置定位器 | 统一使用 `markdown-chars:{start}-{end}` |
| `title` | 内嵌附件标题 | 只用于内嵌附件来源快照 |
| `parsed_content_sha256` | AI 实际消费的规范化 Markdown 内容摘要 | 由 AI 服务根据收到的 Markdown 计算 |
| `MainDocumentSnapshot` | 主合同来源快照类型 | 已实现基础 |
| `UploadedAttachmentSnapshot` | 已上传附件来源快照类型 | 已实现基础 |
| `EmbeddedAttachmentSnapshot` | 正文内嵌附件来源快照类型 | 已实现基础 |

## 6. 事实域公共结构与状态

| 英文字段/类型 | 中文含义 | 状态/说明 |
|---|---|---|
| `FactDomain[T]` | 某一个事实域的通用外层结构，`T` 表示该域自己的强类型数据 | Prepare OpenSpec 已定稿 |
| `state` | 整个事实域或某文档覆盖的提取状态 | 不代表正式审核是否通过 |
| `coverage` | 各适用文档是否已可靠完成事实提取的覆盖清单 | 用于区分“确实没有事实”和“没有可靠处理” |
| `data` | 当前事实域的强类型业务事实 | 六个事实域均已由 Prepare OpenSpec 定稿 |
| `issues` | 当前事实域或当前文档的提取、证据或覆盖问题 | 不等于第二阶段正式检查结果 |
| `FactIssue` | 事实域内部的结构化覆盖问题 | Prepare OpenSpec 已定稿；包含 `fact_issue_key`、`code`、`message`、非空 `related_document_keys`、非空 `affected_fact_kinds` 和可为空的 `evidence_ids` |
| `PreparationIssue` | 跨域或跨文档的结构化准备问题 | Prepare OpenSpec 已定稿；包含 `preparation_issue_key`、`code`、`message`、非空 `related_document_keys` 和可为空的 `evidence_ids` |
| `fact_issue_keys` | 文档覆盖记录引用的事实问题键列表 | `COMPLETE` 时为空；`PARTIAL/UNAVAILABLE` 时至少引用一个同域 `FactIssue` |
| `affected_fact_kinds` | 当前覆盖或事实问题受影响的事实类别 | `PARTIAL/UNAVAILABLE` 必须明确，不能只给笼统错误说明 |
| `related_document_keys` | 与事实问题或准备问题相关的文档键列表 | Prepare OpenSpec 已定稿且非空，所有引用必须指向来源快照中的现存文档 |

来源截断、乱码、表格丢列或边界破损可能没有可信可定位引文，因此 `FactIssue.evidence_ids` 可以为空；这不允许伪造证据，问题仍必须明确相关文档和受影响事实类别。

### 6.1 事实域状态 `state`

| 枚举值 | 中文含义 |
|---|---|
| `COMPLETE` | 适用范围已经可靠完成提取；不表示合同字段齐全，也不表示审核通过 |
| `PARTIAL` | 只可靠完成了部分提取，必须说明覆盖缺口 |
| `UNAVAILABLE` | 因源文本明显不可读等非技术性来源问题，无法形成该事实域 |

模型超时、格式重试耗尽、组装失败等技术错误不使用上述状态伪装，prepare 整体失败。

### 6.2 字段存在状态 `presence`

| 枚举值 | 中文含义 |
|---|---|
| `ABSENT` | 在适用范围内没有发现该字段 |
| `PRESENT_EMPTY` | 发现明确标签或位置，但内容为空 |
| `PRESENT_VALUE` | 发现了一个或多个一致的实质值 |
| `UNCERTAIN` | 存在不同候选，或字段语义无法可靠确定 |

数量不变量：`ABSENT` 的 `observations=[]`；`PRESENT_EMPTY` 至少保留一条 `raw_text=""` 且带非空 `evidence_ids` 的空位观察；`PRESENT_VALUE` 至少保留一条实质观察；`UNCERTAIN` 保留造成不确定性的候选或来源观察及证据，不得静默选主值。`ABSENT` 和 `PRESENT_EMPTY` 都使用 `normalization_state=NOT_APPLICABLE`，但两者不得合并为同一种结构。

### 6.3 字段规范化状态 `normalization_state`

| 枚举值 | 中文含义 |
|---|---|
| `NOT_APPLICABLE` | 当前没有需要规范化的实质值 |
| `VALID` | 候选值可以按确定规则规范化 |
| `INVALID` | 已有文本，但格式或内容不可用 |
| `UNCERTAIN` | 无法可靠确定规范化结果 |

### 6.4 观察值公共字段

| 英文字段/类型 | 中文含义 | 状态/说明 |
|---|---|---|
| `ObservedField[T]` | 带存在状态、规范化状态和候选观察值的字段类型 | Prepare OpenSpec 已定稿 |
| `observations` | 当前字段的候选观察值清单 | 不同候选不得由模型静默选主值 |
| `raw_text` | 从原文提取的原始文本 | 始终保留；空标签可使用空字符串并引用标签证据 |
| `normalized_value` | 按确定规则形成的规范化值 | 只有能够可靠规范化时输出 |
| `evidence_ids` | 支撑当前事实或观察值的证据键列表 | 必须指向统一证据注册表 |
| `attributes` | 旧过渡版自由扩展属性 | 已从正式 Prepare 公共契约移除，不得输出；新增业务事实必须进入版本化强类型字段 |

## 7. 六个公共事实域

| 英文字段 | 中文含义 | 字段级状态 |
|---|---|---|
| `header` | 主合同首部身份、签订地点和首页签订日期事实 | Prepare OpenSpec 已定稿 |
| `parties` | 主合同签约方基准，以及正文和附件中的签约方称谓与主体关系事实 | Prepare OpenSpec 已定稿 |
| `signature` | 主合同及附件的签章块、签署人、日期、账户和联系字段 | Prepare OpenSpec 已定稿，代码实现待完成 |
| `amount_payment` | 主合同正文中全部有证据的金额对象、币种、税务口径、付款方式和付款阶段关系 | Prepare OpenSpec 已定稿，代码实现待完成 |
| `copy_terms` | 主合同本身“一式几份、各方各执几份”等文本份数事实 | Prepare OpenSpec 已定稿；不包含附件声明或实际来源数量 |
| `attachment_manifest` | 正文附件声明、实际附件来源、逻辑附件候选及中性关联事实 | Prepare OpenSpec 已定稿，代码实现待完成 |

## 8. 统一证据注册表

| 英文字段 | 中文含义 | 状态/说明 |
|---|---|---|
| `evidence_index` | 统一证据注册表对象 | Prepare OpenSpec 已定稿 |
| `items` | 全部证据条目列表 | 一个证据可以被多个事实复用 |
| `evidence_id` | 当前 `ReviewContext` 内全局唯一的证据键 | 事实通过 `evidence_ids` 引用 |
| `document_key` | 证据所属文档键 | 必须存在于 `source_snapshot` |
| `source_locator` | 证据在规范化完整 Markdown 中的位置 | 后端唯一定位和验证 |
| `quote` | 与 `source_locator` 切片完全一致的短引文 | 模型提供候选，后端验证 |
| `markdown-chars:{start}-{end}` | Markdown 字符偏移定位格式 | 从 0 开始，`start` 包含、`end` 不包含，按 Unicode code point 计数 |

## 9. 准备流水线元数据

| 英文字段 | 中文含义 | 状态/说明 |
|---|---|---|
| `pipeline_version` | 事实提取、后处理和证据语义对应的准备流水线版本 | 语义变化时应更新 |
| `prompt_bundle_hash` | 全部 prepare 提示词和输出 Schema 组合的摘要 | 用于追溯模型输入契约版本 |
| `model_deployment` | 本次准备调用的模型部署名称 | Prepare OpenSpec 已定稿 |
| `created_at` | 当前 `ReviewContext` 的创建时间 | 会参与完整上下文摘要，因此 `context_digest` 不是业务幂等键 |

### 9.1 数据保护与运行时隔离术语

| 英文术语 | 中文含义 | 状态/说明 |
|---|---|---|
| `contract-derived review data` | 合同来源审核数据 | 合同正文和附件中实际存在的身份证号、银行账户、联系信息等；可以作为合同事实和证据进入完整 `ReviewContext` |
| `protected preset master data` | 受保护的预设主数据 | 系统预设签署人、身份证号、银行账户和联系信息；不进入 `ReviewContext`、模型、持久化、日志、Trace 或正式结果 |
| `runtime isolation` | 运行时隔离 | 预设值只在当前 `evaluate` 请求的局部调用链中实时读取和使用，请求结束后不保留业务引用；不表示可信执行环境或物理内存清零 |
| `deterministic comparison` | 确定性比较 | 后端按明确顺序比较合同事实与预设值，例如先按姓名定位预设人员，再只比较该人员的身份证号，不由模型直接裁决 |

### 9.2 模型与程序职责术语

| 英文术语 | 中文含义 | 状态/说明 |
|---|---|---|
| `semantic extraction` | 语义事实提取 | LLM 从非固定版式中识别候选事实、主体和人员角色、字段用途、关系、不确定性及证据；不直接产生第一阶段正式检查结果 |
| `deterministic adjudication` | 确定性裁决 | 后端根据已验证事实、实时预设和已确认检查矩阵稳定生成正式 `PASS/WARN/FAIL`、不适用或暂未完成状态；上下文刷新控制信号和请求错误在进入正式裁决前独立处理 |
| `uncertainty handoff` | 不确定性移交 | LLM 以 `UNCERTAIN` 或覆盖缺口显式表达不能可靠判断的部分，程序按已确认规则处理，不让模型自由决定正式等级，也不由程序反向猜测合同语义 |
| `generic rule mechanism` | 通用规则机制 | 统一字段状态、主体关系、证据验证、预设比较和检查矩阵等可复用实现；业务确认项不与专用程序分支一一对应 |

## 10. header 首部事实域

| 英文字段/类型 | 中文含义 | 状态/说明 |
|---|---|---|
| `HeaderFacts` | `header` 域的强类型数据 | Prepare OpenSpec 已定稿 |
| `contract_identity` | 合同名称与合同编号组成的合同身份组 | 必须成组使用，不得与项目身份字段交叉补齐 |
| `project_identity` | 项目名称与项目编号组成的项目身份组 | 合同名称缺失、留空或只有泛化标题，而项目名称具有可靠、唯一的实际识别意义时整体承担身份校验；合同编号不能单独阻止该选择 |
| `name` | 当前身份组中的名称字段 | 合同名称或项目名称 |
| `number` | 当前身份组中的编号字段 | 合同编号或项目编号 |
| `signing_location` | 合同首部明确的签订或订立地点 | 接受“签订地点”“签约地点”“合同签订地”等语义等价栏位；保留栏位存在性、空值状态、完整原文、城市候选和证据，不从其他字段推断 |
| `signing_date` | 合同首部明确的签订或订立日期 | 不从签章、生效、履约或付款日期补齐 |
| `specificity` | 名称是否具有具体识别信息 | 用于区分具体名称和泛化标题 |
| `identity_basis` | 第二阶段实际采用合同身份组还是项目身份组的派生选择 | 不进入第一阶段 `ReviewContext` |
| `name-led identity selection` | 名称主导的身份组选择 | 第二阶段依据名称是否具有实际识别意义选择整组身份；合同编号不能单独强制选择合同组，且任何情况下都禁止跨组拼接 |
| `extractable signing city` | 可提取的签订城市 | 签订地点原文可以同时包含省份、区县或详细地址，只要能够从该栏位实际值中可靠且唯一地提取出城市；城市库仅用于提取和归一化，不是独立检查项 |

### 10.1 名称具体程度 `specificity`

| 枚举值 | 中文含义 |
|---|---|
| `SPECIFIC` | 名称包含具体识别信息，例如具体项目或交易标的 |
| `GENERIC` | 只有“合同”“采购合同”等类型含义，没有具体识别信息 |
| `UNCERTAIN` | 无法可靠判断名称是否具体 |

## 11. parties 签约方事实域

### 11.1 已确认：主合同签约方基准

| 英文字段/类型 | 中文含义 | 状态/说明 |
|---|---|---|
| `PartiesFacts` | `parties` 域的强类型数据 | Prepare OpenSpec 已定稿 |
| `canonical_parties` | 主合同声明的签约方基准清单 | Prepare OpenSpec 已定稿；附件不能反向修改该基准 |
| `CanonicalParty` | 一个主合同签约主体及其全部明确称谓 | 以主体为中心，不是固定甲乙方角色行 |
| `party_key` | 当前 `ReviewContext` 内唯一、稳定的签约方关联键 | 用于跨域和跨来源关联同一主体，不表示相关事实已经合并，不承诺跨合同版本不变 |
| `declared_name` | 合同文本声明的签约主体名称 | 不叫 `legal_name`，因为第一阶段不验证工商法定名称 |
| `declared_designations` | 合同明确赋予该主体的角色称谓和名称简称清单 | Prepare OpenSpec 已定稿 |
| `designation_key` | 当前 `ReviewContext` 内唯一的已声明称谓键 | 可被正文和附件观察引用 |
| `kind` | 已声明称谓的语义类型 | 不是具体角色词枚举 |
| `text` | 已声明称谓的原文或规范化文本 | 例如“甲方”“采购人”“北京移动” |
| `definition_evidence_ids` | 证明该主体是签约方及其称谓关系的证据键列表 | 必须来自主合同签约方定义区 |

### 11.2 已声明称谓类型 `kind`

| 枚举值 | 中文含义 |
|---|---|
| `CONTRACT_ROLE` | 甲方、乙方、采购人、供应商等合同角色称谓 |
| `NAME_ALIAS` | 合同明确声明的主体名称简称 |
| `UNCERTAIN` | 明确存在声明，但无法可靠判断属于角色称谓还是名称简称 |

### 11.3 已确认：跨文档签约方观察

附件必须依靠附件自身证据建立角色与主体的关系；明确不一致由第二阶段 `FAIL`，没有附件本地定义或无法确定时必须人工确认。字段结构和枚举已在方案层面确认。

| 英文字段 | 中文含义 | 状态/说明 |
|---|---|---|
| `party_mentions` | 正文和附件中的签约方称谓及主体关系观察清单 | Prepare OpenSpec 已定稿；这里的 `mentions` 不是普通“提及” |
| `PartyMention` | 一条有当前文档证据支持的签约方观察 | Prepare OpenSpec 已定稿 |
| `mention_key` | 当前观察记录的唯一键 | 当前 `ReviewContext` 内稳定、唯一 |
| `document_key` | 当前观察所属文档键 | 复用来源快照字段 |
| `mention_kind` | 当前观察的语义类型 | Prepare OpenSpec 已定稿 |
| `observed_text` | 原文观察到的角色、名称或称谓 | 必须由证据支持 |
| `referenced_designation_keys` | 可能对应的主合同已声明称谓键 | 可以为空、一个或多个 |
| `explicit_entity_name` | 当前文档明确写出的主体名称 | 没有明确主体值时不输出 |
| `candidate_party_keys` | 当前观察可能对应的主合同签约方键 | 可以为空、一个或多个 |
| `local_definition_state` | 当前附件自身是否建立角色—主体定义 | “本地”指当前附件，不是服务器本地 |
| `comparison_state` | 当前明确主体值与主合同声明集合的比较状态 | 不宣称工商意义上的主体同一性 |

### 11.4 我方识别与客户侧术语

| 英文字段/术语 | 中文含义 | 状态/说明 |
|---|---|---|
| `client-side role` | 客户侧角色 | 主合同中作为本合同服务对象的甲方、买方、采购方、委托方等角色语义；不是合同系统额外传入的业务客户主体，不靠固定词表预先分类全部主体，也不作为查询我方预设前的过滤条件 |
| `all-party preset resolution` | 全体签约方预设识别 | 第二阶段对主合同全部名称明确的 canonical parties 逐一查询预设，不先划分客户侧/非客户侧；角色语义中性或不明确不妨碍通过唯一命中识别我方 |
| `our_party_key` | 我方签约方键 | 第二阶段根据实时预设唯一识别出的我方 `party_key`；不进入第一阶段 `ReviewContext` |
| `unique our-party resolution` | 唯一我方识别 | 全部具名主合同签约方中必须恰好一个预设命中；零命中为序号 1 `FAIL`，多个命中或预设侧无法唯一定位时 `evaluate` 直接报错，不得选择首个结果；唯一命中的我方若被明确声明为客户侧角色，序号 1 `FAIL` |
| `exact preset party-name match` | 我方主体名称完全匹配预设 | 主合同首页我方公司名称必须与预设主体完整法定名称完全一致；简称、品牌名或仅凭语义判断为同一主体都不算一致 |
| `customer-side check boundary` | 客户侧检查边界 | 检查主合同客户侧公司名称存在、主合同客户侧签章块法定代表人或授权人姓名是否填写，以及附件实际填写的客户侧公司或签署人姓名与主合同是否一致；不检查客户侧人员资格、预设、身份证号、日期、账户、联系方式、印章或签字 |
| `out-of-scope contracting party` | 范围外签约方 | 第三方至第 N 方仍作为合同来源事实保留，用于避免误绑到客户侧或我方侧，但不对其公司、自然人、身份证号、日期、账户、联系信息、印章或签字生成正式检查问题 |
| `preset subject miss` | 预设主体未命中 | 合同存在明确候选主体名称，但全部合格候选均未命中预设；表示合同主体与预设不一致，序号 1 `FAIL`，不属于接口错误 |
| `preset non-unique resolution` | 预设无法唯一定位 | 多个候选主体命中，单次查询返回多个无法唯一选择的档案，或预设人员无法唯一定位；依赖预设的检查点暂未完成审核，不受影响检查点可返回正式结果 |
| `preset service error` | 预设服务错误 | 预设服务超时、调用报错或返回结构/内容异常；依赖预设的检查点暂未完成审核，不得用缓存、模型猜测或空值降级 |
| `direct evaluate error` | evaluate 直接错误 | 第二阶段以接口错误结束，不返回一组可被当作已完成审核的正式 `PASS/WARN/FAIL` 检查结果；仅限于合同版本、上下文完整性等前置校验失败或无法安全局部化的服务错误；具体对外错误码和响应结构由后续 OpenSpec 定稿 |

### 11.5 签署人角色判断术语

本节解释已确认的角色判断概念。`signature` 事实域的字段和枚举已由当前 Prepare OpenSpec 定稿，代码实现尚未完成；若本节的概念说明与 OpenSpec 字段契约冲突，以 OpenSpec 为准并同步修订本文。

| 英文术语 | 中文含义 | 状态/说明 |
|---|---|---|
| `legal person` | 法人 | 公司等依法具有民事权利能力和民事行为能力的组织；不得自动等同于自然人角色“法定代表人” |
| `legal representative` | 法定代表人 | 明确属于待核验签署人的自然人角色 |
| `authorized signer` | 授权签署人 | 授权人、授权代表、授权签字人、委托代理人等在对应主体签章块内且上下文表达代其签署权限的人员 |
| `signing-capacity context` | 签署身份语境 | 由原始角色称谓、所在签章/签字栏及代表主体签署的授权语义共同形成，不能只靠固定角色词表判断 |
| `eligible signer` | 待核验签署人 | 根据签署身份语境确定需要在第二阶段与实时预设进行姓名及必要身份证号核验的人员 |
| `irrelevant person` | 明确无关人员 | 证据明确只承担联系、履约或事务办理职责且不代表主体签署的人员；姓名和身份证号整体排除 |
| `uncertain signer role` | 签署人角色不确定 | `代表`、`负责人`、`经办人`等位于正式签字位置但授权关系不足以确认的情况；不得自动排除或自动通过，第二阶段 WARN 并要求人工确认 |
| `signature block` | 签章块 | 一个连续语义签署区域中的局部事实区域；每个块最多绑定一个 `party_key`，只有当前文档证据能够可靠确定主体时才绑定，不按页机械切分，也不把同一主体的全文签署信息合并成一个大块 |
| `signature block party binding` | 签章块主体绑定 | 依靠当前文档中的公司名称、角色、栏位和版面关系确定签章块对应的公司；附件只有角色而没有本地主体定义时不得继承主合同映射，明确角色—公司关系与主合同同一角色不一致时第二阶段 `FAIL` |
| `signer-slot party inheritance` | 签署人栏位沿用签章块主体 | 块内法定代表人、授权人、委托代理人、身份证号和签署日期沿用已经可靠确定的签章块公司归属，不逐字段重新猜测；块归属不确定或字段是否位于该块内不明确时，相应字段归属也保持不确定，不得用姓名或预设值反向认定 |
| `real signature block skeleton` | 真实签章块骨架 | 只为原文中真实存在的连续语义签署区域建立签章块；签署人栏位和签署日期必须归属真实块，不为正文账户条款或主体信息区虚构块 |
| `semantic block boundary` | 签章块语义边界 | 跨页但标题、表格结构和上下文连续时仍为同一块；出现新的主体标题、重新开始的签署区域或明显不连续区域时建立新块 |
| `cross-block aggregation` | 跨签章块汇总 | 同一主体的多个签章块通过 `party_key` 关联，第二阶段可以跨合格块临时汇总完整性事实，但保留块级证据和冲突来源，不覆盖或静默合并不同值 |
| `source-local signature fact` | 来源局部签章事实 | 绑定具体签章块或块外合格来源、主体及统一证据的原始观察；是 `ReviewContext.signature` 的持久化事实，不预先选取主体主值 |
| `block-local observation` | 块内来源局部观察 | 账户或公司级联系字段实际位于真实签章块内，因此保留对应 `signature_block_key`、`document_key`、`party_key`、用途和证据 |
| `block-external observation` | 块外来源局部观察 | 账户或公司级联系字段来自明确绑定主体和用途的正文条款、独立账户表或主体基本信息区；不设置虚假 `signature_block_key`，但仍保留文档、主体、用途和证据 |
| `runtime party signature view` | 运行时主体签署信息视图 | 第二阶段识别 `our_party_key` 后，从全部合格来源局部事实临时派生的检查视图，供序号 2、3、11 和 B-4 共用，不写回 `ReviewContext` |
| `no persisted party summary` | 不持久化主体汇总 | 第一阶段不额外保存与来源事实重复的主体级合并结果；合同系统只需持久化完整 `ReviewContext`，无需保存或回传另一份签署信息汇总 |
| `signature coverage` | 签章事实覆盖 | `signature.coverage[]` 对 `main`、每个上传附件和每个内嵌附件逐文档记录是否已可靠完成签章事实提取 |
| `signature domain state` | 签章域级状态 | `signature.state` 对全部逐文档覆盖状态的粗粒度汇总，只表示事实提取可靠性，不表示签章内容是否完整、正确或通过正式检查 |
| `signature coverage aggregation` | 签章覆盖聚合 | 全部文档覆盖为 `COMPLETE` 时域级为 `COMPLETE`，全部为 `UNAVAILABLE` 时域级为 `UNAVAILABLE`，其余混合情况为 `PARTIAL`；技术错误不进入聚合而使整个 prepare 失败 |
| `per-document coverage decision` | 逐文档覆盖判断 | 第二阶段必须依据每条覆盖记录的文档身份、状态、原因和受影响事实范围决定检查影响，不得仅凭域级 `PARTIAL` 对主合同和附件作统一处理 |
| `signature issue` | 签章覆盖问题 | `signature.issues` 只记录导致签章覆盖降为 `PARTIAL/UNAVAILABLE` 的提取或证据缺口；`signature.state=COMPLETE` 时必须为空 |
| `contract-content ambiguity` | 合同内容歧义 | 规范化原文已被完整可靠取得，但原文本身存在不同候选、角色不清或用途不明；由结构化事实表达，覆盖仍可为 `COMPLETE`，不写入 `signature.issues` |
| `extraction uncertainty` | 提取不确定 | 因解析丢列、内容截断、证据定位失败或边界破损，无法可靠确认原文事实；降低相应文档覆盖并写入 `signature.issues` |
| `reliably absent signature block` | 可靠确认无签章块 | 没有发现签章内容且不存在明确的解析、结构或边界缺口；文档覆盖为 `COMPLETE`，不创建虚假空白签章块，也不要求管理员仅因附件不涉及签章而确认 |
| `signature coverage failure gate` | 签章覆盖失败门槛 | 只有存在具体可说明的解析、结构或附件边界缺口，并且该缺口使系统无法排除原附件中存在签署栏位时，才允许把覆盖降为 `PARTIAL/UNAVAILABLE` |
| `affected signature fact category` | 受影响签章事实类别 | 主合同 `PARTIAL` 覆盖问题实际波及的签署人、身份证号关联、签署日期、账户或联系事实类别；用于确定哪些正式检查无法可靠完成 |
| `dependency-scoped coverage failure` | 按依赖映射覆盖失败 | 只让依赖受影响事实类别的序号 2、3、11 或 B-4 `FAIL`；不受影响且覆盖完整的检查项继续正常判断 |
| `reviewability failure` | 检查可验证性不足 | 因覆盖缺口无法可靠完成某项检查而产生的 `FAIL`；表示需要管理员查看原文，不断言合同内容已经确认错误 |
| `unknown coverage scope` | 覆盖影响范围不明 | 主合同签章事实整体 `UNAVAILABLE`，或无法说明覆盖问题影响哪些事实类别；序号 2、3、11 和 B-4 均 `FAIL` 并交管理员判断 |
| `unassessable attachment signer slot` | 附件签署栏位无法可靠判断 | 已满足签章覆盖失败门槛，导致无法判断是否存在待核验签署人栏位；第二阶段 B-4 `FAIL`，由合同管理员结合原文人工判断，不得按“没有栏位”自动通过 |
| `signer slot` | 签署人栏位 | 签章块中要求填写某位签署人的可辨认位置；每个栏位独立保留原始角色、状态、全部实填人员、主体绑定结果或不确定状态和证据，只有当前文档可靠确定主体时才设置 `party_key` |
| `alternative signer group` | 签署人替代组 | 合同明确表达若干签署身份或栏位任选其一的语义组；不能仅因栏位相邻就推定为替代关系 |
| `slot state` | 栏位状态 | 单个签署人栏位的 `ABSENT`、`PRESENT_EMPTY`、`PRESENT_VALUE` 或 `UNCERTAIN` 事实状态，不直接等同于替代组是否完整 |
| `group completeness` | 替代组实际填写情况 | 组内至少一个栏位有实填姓名时，未使用的空栏不单独产生问题；主合同必查签署人组全部为空时按主合同缺失规则处理，附件非必查签署人组全部为空时不校验 |
| `filled signer set` | 实填签署人集合 | 同一栏位或替代组实际填写的全部人员；第一阶段不得只取第一个，第二阶段分别核验 |
| `verified main signer set` | 主合同已核验签署人集合 | 第二阶段使用实时预设逐人完成序号 2 签署人校验后形成的运行时集合；只有主体、角色、姓名及已填写身份证号均通过相应校验的人员才能进入，不进入第一阶段 `ReviewContext` |
| `dependency-scoped signer short-circuit` | 按依赖局部短路签署人比较 | 没有任何主合同签署人通过序号 2 时，B-4 不用附件人员独立查询预设，签署人分支因无法核验而 `FAIL`；部分人员通过时只使用已通过人员，且不影响其他具有独立有效基准的 B-4 分支 |
| `signer role compatibility` | 签署人角色相容 | 附件明确角色与同名主合同签署人的角色及预设资格相同或语义相容；不是要求物理栏位名称完全相同 |
| `same-party signer match` | 同主体签署人匹配 | 附件我方签署人与主合同签署人必须依靠当前附件证据绑定同一 `party_key`，且姓名属于主合同已核验签署人集合；明确组合栏位或替代组允许在其角色范围内匹配，其他预设授权人不能替代该基准 |
| `direct person-ID association` | 人员—身份证号直接关联 | 同一行、同一单元格组、同一签署人栏位或明确文字直接证明姓名与身份证号属于同一人员 |
| `unique in-block association` | 签章块内唯一配对 | 同一独立且已绑定主体的签章块内，恰好一名待核验签署人和一个相关身份证号，且无其他可能归属或冲突证据时允许的确定性兜底 |
| `uncertain person-ID association` | 人员—身份证号关联不确定 | 多人多号或证据边界不足，无法证明号码归属；不得按顺序、邻近或数组位置强行配对，第二阶段 WARN |
| `name-first ID comparison` | 姓名优先的身份证号比较 | 先以姓名定位唯一预设人员，再只比较该人员的预设身份证号；不得用号码反查姓名或跨人匹配 |
| `signing-location preset` | 签署地预设值 | 现有业务接口和主数据档案名称；按候选我方签署主体全称查询，不等同于合同首部的地理签订地点 `header.signing_location` |
| `signing-location preset profile` | 签署地预设档案 | 唯一识别我方后在第二阶段取得的一份完整运行时档案，包含主体、法定代表人、授权人列表、身份证号、账户和联系预设 |
| `single preset group` | 单组签署地预设 | 一个我方签署地对应一组账户、联系和人员主数据；多名授权人或多名实际签署人不产生多组账户和联系方式 |
| `contract-side preset-comparison facts` | 合同侧预设比较事实 | 合同中实际出现并进入 `ReviewContext` 的人员、账户和联系事实；它们与第二阶段运行时预设档案比较，但不因此变成预设主数据 |
| `signature information section` | 签署信息区/签章块 | 合同中预留给各方填写主体、签署人、账户和联系信息的语义区域；名称不表示已经实际签字或盖章 |
| `pre-filled signer information` | 主合同预填签署人信息 | 主合同签章块中法定代表人/授权人的角色栏位及姓名文本；我方属于序号 2 检查对象，客户侧只检查是否填写。该术语不表示附件相同栏位为必填项 |
| `physical signature mark` | 实际签名痕迹 | 手写签名、签名图片或个人签章等签署动作结果；组织评审不检查其是否存在或真实 |
| `company seal presence` | 公司印章存在性 | 合同是否已有实体章或电子章；首期不做图像识别、存在性或真伪判断，不进入 `signature` 事实 |
| `nine signature-page fields` | 签章页 9 项信息 | 法定代表人/授权人、开户银行、银行账号、账户名称、地址、电话、传真、网址、邮编；签约方名称、身份证号、签署日期、实际印章和签名均不计入 |
| `sequence-2 signer validation` | 序号 2 主合同签署人校验 | 主合同我方签署人姓名必须按实时预设核验；合同已填写身份证号时，按姓名定位同一预设人员后做条件性号码比较。身份证号不计入签章页 9 项，但该主合同校验仍归序号 2 |
| `optional attachment signature field` | 附件非必查签章字段 | 附件签章块中的客户侧和我方侧公司名称、法定代表人及授权人没有栏位或没有实际填写时不校验；实际填写后才与主合同同侧、同角色内容比较 |
| `B-4 attachment signer validation` | B-4 附件签署人校验 | 附件实际填写的客户侧签署人姓名只与主合同客户侧同角色姓名比较；附件实际填写的我方签署人姓名、角色和已关联身份证号按主合同签署人基准及实时预设校验。附件没有可关联的我方签署人姓名时不考虑身份证号，不把附件问题归入序号 2 |
| `required account trio` | 必填账户三项 | 开户银行、银行账号、账户名称；任一项 `ABSENT` 或 `PRESENT_EMPTY` 时第二阶段 `FAIL` |
| `advisory contact fields` | 提示级联系字段 | 地址、电话、传真、网址、邮编；任一项 `ABSENT` 或 `PRESENT_EMPTY` 时第二阶段 `WARN` |
| `field-specific missing severity` | 分字段缺失等级 | 9 项不能使用统一缺失等级：签署人姓名和账户三项缺失为 `FAIL`，五项联系字段缺失为 `WARN` |
| `shared account facts` | 共享账户事实 | 开户银行、银行账号、账户名称在 `signature` 中只保存一份事实和证据，由序号 2、序号 11按各自目的复用 |
| `sequence-2 bank check` | 序号 2 开户银行检查 | 只显示开户银行，同时检查是否存在以及是否与签署地预设一致；缺失、留空或不一致均 `FAIL` |
| `sequence-11 account check` | 序号 11 收款账户检查 | 显示并检查开户银行、银行账号、账户名称三项；任一项缺失、留空或不一致均 `FAIL`，三项齐全且一致才 `PASS` |
| `independent check projection` | 独立检查点投影 | 同一开户银行事实可以分别支撑序号 2 的签章页完整性/正确性和序号 11 的账户准确性，不等于重复提取或重复持久化 |
| `tiered candidate retrieval` | 分层候选检索 | 先查我方签章块，再查明确绑定我方的主体或收款账户区，最后对主合同做标签/格式候选搜索；全文命中不直接等于事实成立 |
| `purpose-bound account evidence` | 账户用途绑定证据 | 证明账户属于我方且用于本合同收款或结算的本地证据；开票、保证金、退款、保函等其他用途不得自动继承 |
| `company-level contact fact` | 公司级联系事实 | 明确属于我方公司的地址、电话、传真、网址或邮编；联系人、项目负责人、收件人等个人或业务联系信息不适用 |
| `candidate-only source` | 仅候选来源 | 可以召回并保留观察，但不足以补足正式字段的来源，例如用途不明的开票账户或附件中的独立账户信息 |
| `attachment non-backfill` | 附件不回填主合同 | 附件账户和联系信息保留为独立观察与一致性证据，但不自动补足主合同序号 2、序号 11 基准 |
| `attachment-main field comparison` | 附件—主合同字段比较 | 仅在主合同已有唯一可用值，且附件以自身证据绑定同一 `party_key`、同一业务用途时，比较当前附件字段与主合同字段；必须保留并引用两侧证据 |
| `attachment account mismatch` | 附件账户不一致 | 上述比较条件满足时，附件开户银行、银行账号或账户名称任一值与主合同不同，由 B-4 判定 `FAIL`；不改变序号 2、序号 11，也不允许附件直接与预设比较后替系统选择合同值 |
| `attachment contact mismatch` | 附件联系字段不一致 | 上述比较条件满足时，附件地址、电话、传真、网址或邮编与主合同同一公司级联系用途的值不同，由 B-4 判定 `WARN` 并要求人工确认 |
| `missing main comparison baseline` | 主合同比较基准缺失 | 主合同字段为 `ABSENT/PRESENT_EMPTY`，但附件以自身证据存在同一主体、同一用途实际值；附件不得回填主合同，也不得直接与预设比较 |
| `invalid main comparison baseline` | 主合同比较基准无效 | 主合同存在实质原文，即 `presence=PRESENT_VALUE`，但在可靠、确定性校验规则下为 `normalization_state=INVALID`；必须保留原始值和证据，不得按缺失处理，也不得用附件回填 |
| `unassessable attachment field comparison` | 附件字段一致性无法核验 | 主合同比较基准缺失、留空或无效，而附件以自身证据存在同一主体、同一用途实际值时，B-4 输出 `WARN` 并要求人工确认；原因必须区分“缺失/留空”与“已填写但无效”，引用两侧证据，不表示附件错误，也不得写成 `PASS`、`NA` 或已确认不一致 |
| `limited format validation` | 有限格式校验 | 仅当字段存在可靠、确定性的格式或规范化规则时才可判为 `INVALID`；电话、邮编、网址等可在规则边界内校验，开户银行、账户名称、地址等自由文本不得仅因写法少见或格式不统一而判为无效 |
| `missing-versus-invalid severity` | 缺失与无效的等级边界 | 开户银行、银行账号、账户名称缺失或无效均为 `FAIL`；公司级联系字段缺失为 `WARN`，但已经填写的实际值无效、无法与实时预设完成有效一致性校验时通常为 `FAIL`。B-4 对两类无基准场景均为 `WARN`，但必须保留不同事实状态和正式原因 |
| `check ownership isolation` | 检查点职责隔离 | 序号 2、序号 11 只判断主合同事实与实时预设；附件与主合同的同主体、同用途差异由 B-4 判断，附件不得污染或回填前两个检查点 |
| `same-purpose account conflict` | 同用途账户冲突 | 同一我方主体、同一收款或结算用途下，开户银行、银行账号或账户名称出现不同值；第一阶段保留全部候选与证据，第二阶段判定 `FAIL`。 |
| `same-purpose contact conflict` | 同用途联系字段冲突 | 同一我方主体、同一公司级联系用途下，地址、电话、传真、网址或邮编规范化后出现多个不同实际值；第一阶段保留全部候选与证据。第二阶段取得唯一且非空预设时，至少一个合同值必然不一致，序号 2 判定 `FAIL`，不得以“无法判断”为由降为 `WARN`。 |
| `empty contact preset field` | 联系字段预设值为空 | 已唯一命中我方签署地预设档案，但对应联系字段为空；序号 2 判定 `FAIL`，原因说明预设主数据缺失、无法校验，不得归因于合同缺失、合同错误或合同与预设不一致。 |
| `unreliable attachment subject binding` | 附件主体绑定不可靠 | 附件只有角色而没有本地主体定义、存在多个候选 `party_key`，或字段所在主体列无法可靠确定；保留候选与证据，不得继承主合同角色映射或用预设反向绑定。 |
| `unreliable attachment field purpose` | 附件字段用途不可靠 | 无法可靠证明账户、地址或联系值属于当前待比较的同一业务用途，例如不能区分收款与保证金账户、公司级电话与个人联系人电话；保留候选与证据，不得猜测用途。 |
| `semantic uncertainty with complete coverage` | 完整覆盖下的语义不确定 | 附件原文和证据已完整、可靠取得，但主体或用途语义本身不明确；相关绑定或用途为 `UNCERTAIN`，覆盖仍可为 `COMPLETE`，第二阶段 `WARN` 人工确认，不进行值比较且不得自动 `PASS`。 |
| `coverage-driven attachment uncertainty` | 覆盖缺口导致的附件不确定 | 截断、乱码、表格列丢失、附件边界或证据定位异常导致原文未被可靠看清；使用 `PARTIAL/UNAVAILABLE` 和结构化 `issues` 表达。若无法排除待核验签署栏位，第二阶段 B-4 `FAIL` 并由合同管理员结合原文判断。 |
| `no preset back-resolution` | 禁止预设反向消歧 | 实时预设只能校验已经依靠附件自身证据可靠绑定我方且用途明确的字段，不得用于猜测附件主体、用途或从多个合同候选中选择“正确值”。 |
| `different-purpose values` | 不同用途值 | 主体相同但业务用途有可靠证据表明不同的多个值，例如收款账户与保证金账户、注册地址与通讯地址；分别保留，不按冲突处理。 |
| `no fact override` | 不覆盖合同事实 | 首期不允许管理员在页面选取候选值后覆盖 `ReviewContext`。账户或联系字段存在已确认的同主体、同用途冲突时，须修订合同、生成新版本并重新 Prepare。 |

### 11.6 签署日期判断术语

| 英文术语 | 中文含义 | 状态/说明 |
|---|---|---|
| `contract signing date` | 合同签订日期 | 只指 `header.signing_date`；允许为空，为空时序号 1 仅提示，不阻断 |
| `signature date` | 签署日期 | 主合同我方签章块中的日期；允许为空，为空时序号 3 跳过且不提示 |
| `current system date` | 当前系统日期 | 管理员触发第二阶段时取得的系统日期；只在合同签订日期为空且签署日期存在时作为兜底比较基准 |
| `date comparison basis` | 日期比较基准 | 首页日期存在时只比较签署日期与合同签订日期是否一致；首页日期为空时才比较签署日期是否早于当前系统日期 |
| `non-signing date` | 非签订日期 | 附件日期、生效日期、履约日期、付款日期和其他主体签章日期等；不得回填或替代 `header.signing_date` |
| `unique signature date` | 唯一签署日期 | 主合同我方全部合格签章块中只有一个有效规范化日期；多处相同值仍视为一个日期并保留全部证据，其他空栏不单独提示或阻断 |
| `conflicting signature dates` | 签署日期冲突 | 主合同我方多个合格位置出现不同的有效规范化日期；第一阶段保留全部候选并标记 `UNCERTAIN`，第二阶段 `FAIL`，不得选择其中一个 |
| `invalid signature date` | 无效签署日期 | 合格位置存在非空日期文本但不完整、不合法或无法可靠规范化；不得视为空或被其他有效日期掩盖，第二阶段 `FAIL` |

### 11.7 观察类型 `mention_kind`

| 枚举值 | 中文含义 |
|---|---|
| `PARTY_DEFINITION` | 当前文档明确建立了角色或称谓与主体的对应关系 |
| `PARTY_APPELLATION` | 当前文档在承担合同权利义务的语境中使用了主体称谓 |
| `ROLE_REFERENCE` | 当前附件使用了角色称谓，但没有明确对应主体 |

### 11.8 附件本地定义状态 `local_definition_state`

| 枚举值 | 中文含义 |
|---|---|
| `PRESENT` | 当前附件存在明确的角色—主体定义 |
| `ABSENT` | 当前附件使用了角色，但没有主体定义 |
| `UNCERTAIN` | 疑似存在定义，但无法可靠解析或定位 |
| `NOT_APPLICABLE` | 当前观察不需要判断附件本地定义 |

### 11.9 主合同声明比较状态 `comparison_state`

| 枚举值 | 中文含义 |
|---|---|
| `MATCHED_DECLARATION` | 当前明确值与主合同声明名称或明确称谓匹配 |
| `OUTSIDE_DECLARED_SET` | 当前明确值不在主合同对应主体的声明集合内 |
| `UNCERTAIN` | 主体绑定、称谓语境或证据不足以可靠判断 |
| `NOT_APPLICABLE` | 当前没有可比较的附件本地主体值 |

## 12. copy_terms 合同文本份数事实域

| 英文术语 | 中文含义 | 状态/说明 |
|---|---|---|
| `CopyTermsFacts` | 主合同文本份数事实 | 只处理主合同“一式几份、各方各执几份”等事实，不包含附件数量 |
| `overall_total_statement_key` | 主合同整体总份数陈述索引 | 可选；只引用 `statements[]` 中已有且由原文明示的 `CopyStatement`，不复制第二份事实，也不根据各方份数之和或附件份数推算 |
| `allocations` | 主合同份数持有或分配事实集合 | 分别保留主体候选、分配语义和证据，并通过 `statement_key` 引用所属陈述 |
| `allocation_semantics` | 份数分配语义 | Prepare OpenSpec 已定稿为 `EACH | COLLECTIVE | UNCERTAIN` |
| `statement_key` / `scope_key` / `allocation_key` | 份数观察、范围和分配的稳定引用键 | Prepare OpenSpec 已定稿；分别位于 `CopyStatement` 和 `CopyAllocation`，并在各自声明集合内唯一 |
| `attachment copy statement` | 附件自身份数声明 | 不得补足或冲突主合同整体总份数，首期不进入合同份数检查 |

## 13. 其他稳定引用键

以下键的“版本内稳定、唯一”原则已确认，但所属事实域尚未逐域展开。

| 英文字段 | 中文含义 | 所属事实域 |
|---|---|---|
| `signature_block_key` | 签章区块键 | `signature` |
| `signer_slot_key` | 签署人栏位键 | `signature` |
| `payment_stage_key` | 付款阶段键 | `amount_payment` |
| `amount_key` | 金额对象键 | `amount_payment`；同一不可变 `ReviewContext` 内唯一，用于保持同值但不同原文位置、不同角色或不同关系的金额事实彼此独立 |
| `attachment_declaration_key` | 正文附件声明键 | `attachment_manifest` |
| `logical_attachment_candidate_key` | 上传文件内逻辑附件候选键 | `attachment_manifest`；与父 `document_key` 和局部范围共同定位，不伪造物理来源 |
| `attachment_relation_key` | 附件声明与实际来源关系键 | `attachment_manifest` |

## 14. 附件关联状态术语

| 英文字段/枚举 | 中文含义 | 状态/说明 |
|---|---|---|
| `declarations` | 主合同正文中的应有附件声明清单 | 从完整主合同识别，不限于文末独立清单；明确附件引用可形成声明 |
| `actual attachment sources` | 当前实际附件来源集合 | 由上传附件和可可靠切分的正文内嵌附件组成；清单只引用其 `document_key` |
| `logical attachment candidates` | 上传文件内逻辑附件候选集合 | 一个物理上传文件可形成 0..N 个待管理员确认的顶层候选；候选引用父来源和局部范围 |
| `links` | 附件声明与实际来源之间的中性关联清单 | 只保存 `LINKED` 或 `UNCERTAIN`；第一阶段不保存缺失、多余或标题不一致结论 |
| `LINKED` | 已建立有证据支持的正向关联 | 第一阶段可记录 |
| `UNCERTAIN` | 存在候选关联但无法可靠确定 | 第一阶段可记录 |
| `MISSING` | 缺少正文声明对应附件 | 第一阶段不输出，由第二阶段判断 |
| `EXTRA` | 存在没有正文声明来源的实际附件 | 第一阶段不输出，由第二阶段判断 |
| `NO_LINK_ESTABLISHED` | 没有建立关联 | 不作为第一阶段关系记录；没有关系时不生成 `links` 项 |

## 15. 其他接口、代码和格式术语

### 15.1 错误类别

| 英文错误类别 | 中文含义 | 状态/说明 |
|---|---|---|
| `DUPLICATE_ATTACHMENT` | 当前请求存在明确重复附件 | 可作为内部分类；Prepare OpenSpec 已确认在模型调用前按统一参数错误 `10001` 拒绝，不返回残缺 `ReviewContext` |
| `CONTEXT_SCHEMA_UNSUPPORTED` | `ReviewContext` 的 Schema 无法被当前服务安全解析或验证 | 不执行正式检查，也不得伪装成上下文刷新信号 |
| `CONTEXT_INTEGRITY_ERROR` | `ReviewContext` 内容与 `context_digest` 不一致 | 不执行正式检查 |
| `DOCUMENT_REVISION_MISMATCH` | 检查请求版本与上下文版本不一致 | 不执行正式检查 |
| `CONTEXT_INCOMPLETE` | 按声明 Schema 本应存在的必需结构缺失或无效 | 上下文无法安全消费，不执行正式检查；不得用它表示可定位的 `PARTIAL/UNAVAILABLE` 覆盖缺口，后者由各检查点按已确认规则返回 `WARN/FAIL` |
| `SIGNING_PRESET_SERVICE_ERROR` | 签署地预设服务超时、调用报错或返回异常 | 仅预设依赖检查点暂未完成审核；不受影响检查点可作为部分检查结果返回 |
| `SIGNING_PRESET_NON_UNIQUE` | 主体、预设档案或预设人员在预设侧无法唯一定位 | 仅预设依赖检查点暂未完成审核；不受影响检查点可作为部分检查结果返回 |

### 15.2 OpenSpec 变更名称

| 英文名称 | 中文含义 | 状态 |
|---|---|---|
| `contract-review-context-foundation` | 合同评审上下文基础信封 | 已完成并归档 |
| `contract-review-prepare-api` | 第一阶段材料准备接口 | OpenSpec 已创建并完成设计定稿，代码实现待完成 |
| `contract-review-evaluate-api` | 第二阶段正式检查接口 | 尚未开始 |
| `contract-review-two-stage-pilot` | 新旧流程对照试点及生产切换准备 | 尚未开始 |

### 15.3 历史或内部代码术语

| 英文术语 | 中文含义 | 状态/说明 |
|---|---|---|
| `B-1_input` | 按 B-1 检查点组织的专用中间输入 | 新两阶段方案明确不采用这种按检查点编号组织的数据结构 |
| `B-4_input` | 按 B-4 检查点组织的专用中间输入 | 新两阶段方案明确不采用 |
| `definition_label` | 模型或旧逻辑用于描述定义前置标签的字段名 | 不得把“项目单位、施工单位”等具体标签枚举成业务真相 |
| `found_appellation` | 旧 B-1 结构化输出中的“发现称谓” | 旧流程术语；prepare 改为通用签约方观察事实 |
| `router.py` | 旧合同评审接口路由文件 | 旧流程回归基线，不在 prepare 设计阶段重构 |
| `service.py` | 旧合同评审流水线服务文件 | 旧流程回归基线 |
| `schemas.py` | Pydantic 数据结构文件 | 两阶段目录内现有文件是已归档基础信封的当前实现 |
| `run_review_pipeline` | 旧合同评审主流水线函数 | 新 prepare 不调用，也不与其混合结果 |

### 15.4 字段路径、数组和空值写法

| 英文写法 | 中文含义 |
|---|---|
| `contract_identity.name` | 合同身份组中的合同名称字段 |
| `contract_identity.number` | 合同身份组中的合同编号字段 |
| `project_identity.name` | 项目身份组中的项目名称字段 |
| `project_identity.number` | 项目身份组中的项目编号字段 |
| `header.signing_date` | `header` 事实域中的首页签订日期字段 |
| `EmbeddedAttachmentSnapshot.source_locator` | 内嵌附件来源快照在完整主 Markdown 中的绝对定位字段 |
| `coverage[]` | `coverage` 是数组，可包含零项或多项文档覆盖记录 |
| `observations[]` | `observations` 是数组，可包含多个候选观察值 |
| `evidence_ids[]` | `evidence_ids` 是数组，可引用多个证据键 |
| `related_document_keys[]` | `related_document_keys` 是数组，可引用多个相关文档键 |
| `FactIssue[]` | `FactIssue` 的数组，即多个事实域内部问题 |
| `null` | JSON 显式空值；与字段完全不存在不是同一语义 |
| `YYYY-MM-DD` | ISO 风格的完整日期格式，例如 `2026-08-03` |

### 15.5 文本换行格式

| 英文术语 | 中文含义 |
|---|---|
| `CRLF` | Windows 常见换行序列：回车加换行 |
| `CR` | 单独的回车字符 |
| `LF` | 换行字符；规范化 Markdown 坐标计算前统一使用该换行形式 |

## 16. 维护规则

1. 后续每确认一个事实域，都同步增加该域的英文字段、中文含义、枚举和确认状态。
2. 英文字段首次出现在讨论回复时，使用“`field_name`（中文含义）”格式。
3. JSON 示例中出现新字段时，必须在本文找到对应中文解释；找不到则先补本文。
4. 同一英文术语只能有一个稳定中文含义；需要调整时同步搜索主方案和沟通文档。
5. “讨论中”字段不得被实施人员当成正式接口契约；进入 OpenSpec 后必须将状态更新为对应 OpenSpec/Schema 权威。
6. 本文不重复维护完整业务判断，只解释字段含义并链接权威方案，避免两处规则漂移。
