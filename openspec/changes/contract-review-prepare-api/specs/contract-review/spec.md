## ADDED Requirements

### Requirement: 第一阶段材料准备接口
系统 SHALL 提供 `POST /api/v1/contract-review/prepare` JSON 接口，请求 SHALL 包含非空 `contract_id`、`revision_id`、`main_document`、`uploaded_attachments`，并 MAY 包含 `parser_meta`。成功响应 SHALL 沿用项目统一响应壳，且 `data` SHALL 直接是一份完整 `ReviewContext`；失败响应 SHALL 使用 `data=null`。接口 SHALL 受现有鉴权、Trace 和耗时中间件保护，不得新增 multipart 入口。

#### Scenario: 无附件的合法完整快照
- **WHEN** 调用方提供合法主合同且 `uploaded_attachments=[]`
- **THEN** 系统 SHALL 接受请求并返回 `code=0`
- **AND** `data.source_snapshot.attachments` SHALL 只包含从主 Markdown 可靠识别出的内嵌附件
- **AND** `data` SHALL 包含六个强类型事实域和完整摘要

#### Scenario: 请求不使用统一字段包装
- **WHEN** Prepare 成功生成 `ReviewContext`
- **THEN** 统一响应的 `data` SHALL 直接包含 `schema_version`、`source_snapshot`、`shared_facts`、`evidence_index`、`preparation_issues`、`preparation_meta` 和 `context_digest`
- **AND** 系统 SHALL NOT 再增加 `data.review_context` 包装层

#### Scenario: multipart 调用 Prepare
- **WHEN** 调用方尝试以 multipart 文件上传方式调用 Prepare
- **THEN** 系统 SHALL NOT 提供该入口
- **AND** 现有 `/api/v1/contract-review/upload-md` 行为 SHALL 保持不变

### Requirement: Prepare 输入表示当前完整文件快照
`main_document` SHALL 包含非空 `document_id`、`filename`、`markdown` 和可选 `source_file_sha256`；每个上传附件 SHALL 包含非空 `attachment_id`、`filename`、`markdown` 和可选 `source_file_sha256`。主文档或任一已传附件的 Markdown 经固定规范化后不含实质字符时，系统 SHALL 以 `10001` 参数错误拒绝请求。`uploaded_attachments` SHALL 表示当前合同版本全部有效上传附件，不得解释为本次增量，也不得设置三条上限。

#### Scenario: 多个上传附件完整处理
- **WHEN** 请求包含 N 个不同 `attachment_id` 且 Markdown 均非空的上传附件
- **THEN** 系统 SHALL 将 N 个附件全部纳入来源快照、重复门禁和适用事实域覆盖
- **AND** 系统 SHALL NOT 因数组超过三条而截断或拒绝

#### Scenario: 存在空 Markdown 附件
- **WHEN** 任一上传附件的 Markdown 经 BOM、Unicode 和换行规范化后只包含空白
- **THEN** 系统 SHALL 在模型调用前返回 `10001`
- **AND** 系统 SHALL NOT 返回残缺 `ReviewContext`

#### Scenario: 可选来源元数据缺失
- **WHEN** 请求未提供 `source_file_sha256` 或 `parser_meta`
- **THEN** 系统 SHALL 继续准备
- **AND** 未提供字段 SHALL 从来源快照省略而不是输出 `null` 或虚构值

### Requirement: 来源快照包含上传与内嵌附件的真实身份
系统 SHALL 复用基础契约的来源判别联合：主文档固定为 `document_key=main`；上传附件 SHALL 使用 `source_kind=UPLOADED` 和稳定 `attachment_id`；内嵌附件 SHALL 使用 `source_kind=EMBEDDED`、`source_main_document_id`、绝对 `source_locator` 和标题。上传附件键 SHALL 由稳定业务身份形成；内嵌附件键 SHALL 在当前规范化主 Markdown 和准备语义内可复现。正文只有附件标题而无实质内容时 SHALL 只形成声明，不得伪造空内嵌附件。

#### Scenario: 上传附件与内嵌附件共存
- **WHEN** 主 Markdown 可靠包含一个有实质内容的内嵌附件，且请求另含一个上传附件
- **THEN** `source_snapshot.attachments` SHALL 同时保留两个不同来源对象
- **AND** 内嵌附件证据 SHALL 使用派生文档局部坐标
- **AND** 内嵌附件快照的绝对 `source_locator` SHALL 可追溯到完整主 Markdown

#### Scenario: 只有附件标题
- **WHEN** 主 Markdown 出现附件标题或引用但标题后没有实质附件内容
- **THEN** `attachment_manifest.declarations` SHALL 保留该声明
- **AND** `source_snapshot.attachments` SHALL NOT 创建对应空白 `EMBEDDED` 来源

### Requirement: 明确重复附件在模型调用前被拒绝
系统 SHALL 在任何模型调用前完成单次请求重复门禁。重复 `attachment_id`、不同 ID 但规范化文件名与 `parsed_content_sha256` 同时相同的上传附件、以及规范化标题与内容摘要同时相同的内嵌/上传附件 SHALL 作为明确重复，以 `10001` 参数错误拒绝整次请求，并在消息中指出冲突身份或名称。仅同名或仅内容摘要相同 SHALL 作为疑似重复保留，不得静默合并或删除。

#### Scenario: attachment_id 重复
- **WHEN** 同一请求中两个上传附件具有相同 `attachment_id`
- **THEN** 系统 SHALL 返回 `10001`
- **AND** 模型调用次数 SHALL 为 0

#### Scenario: 仅文件名相同
- **WHEN** 两个不同 `attachment_id` 的附件只有规范化文件名相同而内容摘要不同
- **THEN** 系统 SHALL 保留两个来源并继续准备
- **AND** `preparation_issues` SHALL 包含可追溯到两个文档键的疑似重复问题

#### Scenario: 仅内容相同
- **WHEN** 两个不同 `attachment_id` 的附件内容摘要相同但规范化文件名不同
- **THEN** 系统 SHALL 保留两个来源并继续准备
- **AND** 系统 SHALL NOT 将二者静默合并为一个附件

### Requirement: ReviewContext 使用六个强类型事实域
`shared_facts` SHALL 且只 SHALL 包含 `header: FactDomain[HeaderFacts]`、`parties: FactDomain[PartiesFacts]`、`signature: FactDomain[SignatureFacts]`、`amount_payment: FactDomain[AmountPaymentFacts]`、`copy_terms: FactDomain[CopyTermsFacts]` 和 `attachment_manifest: FactDomain[AttachmentManifestFacts]`。每个 `FactDomain` SHALL 包含 `state`、`coverage`、强类型 `data` 和结构化 `issues`，不得继续接受任意 JSON 对象或数组作为公开事实数据。

#### Scenario: 六域齐全但没有观察值
- **WHEN** 合同可靠处理完成但某一适用事实域没有发现任何事实
- **THEN** 该域 SHALL 仍以约定的空强类型结构返回
- **AND** 适用文档覆盖 MAY 为 `COMPLETE`
- **AND** 系统 SHALL NOT 伪造一个空事实对象表示字段曾经出现

#### Scenario: 缺少一个事实域
- **WHEN** 组装结果缺少六域中的任意一个域
- **THEN** 系统 SHALL 将其视为内部组装或 Schema 失败
- **AND** 系统 SHALL NOT 返回成功或用 `UNAVAILABLE` 伪装结构缺失

### Requirement: 字段状态区分缺失、留空、值和不确定
可能缺失、显式留空、存在实质值或无法确定的字段 SHALL 使用 `ObservedField`，至少包含 `presence=ABSENT|PRESENT_EMPTY|PRESENT_VALUE|UNCERTAIN`、`normalization_state=NOT_APPLICABLE|VALID|INVALID|UNCERTAIN` 和 `observations[]`。观察值 SHALL 保留 `raw_text`、可用时的强类型 `normalized_value` 和非空 `evidence_ids[]`。同值重复 SHALL 合并事实并保留全部证据；异值冲突 SHALL 保留全部候选并使用不确定状态，不得选择数组第一项。

#### Scenario: 明确空栏
- **WHEN** 文档可靠包含字段标签或栏位但没有实质值
- **THEN** 字段 SHALL 使用 `presence=PRESENT_EMPTY`
- **AND** 观察 SHALL 保留空栏位置证据
- **AND** 域覆盖 MAY 保持 `COMPLETE`

#### Scenario: 同一字段出现不同值
- **WHEN** 同一业务字段在同一适用范围出现多个规范化后不同的可靠候选
- **THEN** 字段 SHALL 使用 `presence=UNCERTAIN`
- **AND** 所有候选和证据 SHALL 被保留
- **AND** Prepare SHALL NOT 输出正式冲突等级

### Requirement: 覆盖状态只表达事实提取可靠性
域和逐文档覆盖 SHALL 只使用 `COMPLETE|PARTIAL|UNAVAILABLE`。`COMPLETE` SHALL 不引用 `FactIssue`；`PARTIAL/UNAVAILABLE` SHALL 通过 `fact_issue_keys` 引用至少一个结构化问题，问题 SHALL 指明相关文档和受影响事实类别。`header`、`amount_payment`、`copy_terms` 的覆盖 SHALL 只含 `main`；`parties`、`signature`、`attachment_manifest` SHALL 覆盖 `main` 和全部上传/内嵌附件。Prepare 的问题键 SHALL 使用 `fact_issue_key` 或 `preparation_issue_key`，不得复用 Evaluate 具体问题标识 `issue_key`。

#### Scenario: 主合同完整而一个附件局部不可读
- **WHEN** `signature` 对主合同可靠完成，但某附件因表格列丢失只完成部分提取
- **THEN** 主合同覆盖 SHALL 为 `COMPLETE`
- **AND** 该附件覆盖 SHALL 为 `PARTIAL` 并引用受影响事实类别
- **AND** 已可靠取得的主合同和附件事实 SHALL 保留

#### Scenario: 原文语义不明确但覆盖完整
- **WHEN** 原文与证据已可靠取得但主体、用途或角色语义存在多个解释
- **THEN** 对应事实 SHALL 使用 `UNCERTAIN`
- **AND** 覆盖 MAY 保持 `COMPLETE`
- **AND** 系统 SHALL NOT 将该业务歧义写成提取覆盖问题

### Requirement: 统一证据注册表闭合所有引用
`evidence_index` SHALL 只包含 `items[]`，每条 `EvidenceItem` SHALL 包含全局唯一 `evidence_id`、存在于来源快照的 `document_key`、`markdown-chars:{start}-{end}` 和非空 `quote`。所有事实和问题 SHALL 只通过 `evidence_ids[]` 引用注册表；定位切片 SHALL 与 `quote` 完全一致。任何重复证据键、悬空引用、越界定位或引文不一致 SHALL 使 Prepare 整体失败。

#### Scenario: 同一证据被多个事实复用
- **WHEN** 同一原文范围同时支撑主体、签署人或关系事实
- **THEN** `evidence_index.items` SHALL 只需保留一条证据
- **AND** 多个事实 SHALL 引用同一 `evidence_id`

#### Scenario: 引文不能唯一定位
- **WHEN** 模型返回的短引文在限定文档范围内无法定位或存在无法消歧的多个位置
- **THEN** 系统 SHALL NOT 伪造 `source_locator`
- **AND** 可安全局部化时 SHALL 降低对应事实或覆盖并记录问题
- **AND** 无法闭合引用装配时 SHALL 使整次请求失败

### Requirement: header 保留两组身份和首部原始事实
`HeaderFacts` SHALL 包含 `contract_identity{name,number}`、`project_identity{name,number}`、`signing_location` 和 `signing_date`。名称观察 SHALL 另含 `specificity=SPECIFIC|GENERIC|UNCERTAIN`；地点观察 SHALL 保留完整原文和 `city_candidates[]`；有效日期规范化值 SHALL 使用 `YYYY-MM-DD`。本域 SHALL 只读取主合同首部语义范围，不得从文件名、附件、正文履约条款、签章区或其他日期/地点反向补齐，也不得生成 `identity_basis`。

#### Scenario: 合同组和项目组同时存在
- **WHEN** 主合同首部可靠包含合同名称/编号和项目名称/编号
- **THEN** Prepare SHALL 分别保留两组事实和证据
- **AND** Prepare SHALL NOT 选择最终身份组或交叉拼接名称与编号

#### Scenario: 签订地点包含详细地址
- **WHEN** 签订地点栏位包含省、市、区县或详细地址且能可靠提取一个城市
- **THEN** 地点观察 SHALL 保留完整原文
- **AND** `city_candidates` SHALL 保留该城市候选及证据
- **AND** Prepare SHALL NOT 要求原文只等于标准城市名

### Requirement: parties 分离主合同基准与跨文档观察
`PartiesFacts` SHALL 包含 `canonical_parties[]` 和 `party_mentions[]`。`CanonicalParty` SHALL 使用 `party_key`、`declared_name`、`declared_designations[]` 和 `definition_evidence_ids[]`；声明称谓 SHALL 使用 `CONTRACT_ROLE|NAME_ALIAS|UNCERTAIN`。`PartyMention` SHALL 使用 `mention_key`、`document_key`、`mention_kind`、`observed_text`、声明/主体候选引用、本地定义状态、比较状态和证据。只有主合同签约方定义区 SHALL 建立 canonical party；附件和正文观察不得修改该基准。

#### Scenario: 多方合同
- **WHEN** 主合同可靠声明 N 个签约主体且一个主体具有多个角色或简称
- **THEN** Prepare SHALL 保留 N 个 canonical parties 和全部已声明称谓
- **AND** 系统 SHALL NOT 假定同一角色文本只能对应一个主体

#### Scenario: 附件只有角色没有本地主体定义
- **WHEN** 附件在权利义务语境使用合同角色但未在该附件建立角色与主体关系
- **THEN** Prepare SHALL 保留 `ROLE_REFERENCE`、`local_definition_state=ABSENT`、候选主体和证据
- **AND** Prepare SHALL NOT 继承主合同角色映射后宣称已匹配

### Requirement: signature 保留真实签章块、人员和字段关系
`SignatureFacts` SHALL 包含 `signature_blocks[]`、`signer_slots[]`、`alternative_signer_groups[]`、`signer_candidates[]`、`identity_number_candidates[]`、`person_id_relations[]`、`signing_date_observations[]`、`account_observations[]` 和 `contact_observations[]`。签章块、栏位、人员、号码、日期和字段观察 SHALL 使用版本内稳定键显式引用，不得依赖数组位置。签署人栏位和签署日期 SHALL 引用真实 `signature_block_key`；块外账户或联系观察 SHALL 省略该键而保留真实文档、主体绑定/候选、用途状态和证据。

签章装配 SHALL 只在所有关系有可定位证据且唯一可确定时自动完成。事实值可定位但主体、用途或归属没有充分证据时，系统 SHALL 保留该值，并使用 `UNBOUND` 或 `UNCERTAIN`，不得把模型推测升级为 `BOUND` 或 `CONFIRMED`。当同一证据集合支持多个合理的栏位、人员归属、替代关系或主体/用途关系解释时，系统 SHALL 抛出 `NeedsConfirmationError` 并停止本次 Prepare，不得依赖数组位置、距离、预设或模型内部标签强行选择。候选的无效、跨文档或跨块引用仍 SHALL 视为引用不闭合并使请求失败，而非降级为人工确认。

#### Scenario: 一个栏位填写多名人员
- **WHEN** 同一签署人栏位可靠填写多名人员
- **THEN** `signer_keys` SHALL 引用全部人员候选
- **AND** Prepare SHALL NOT 只保留第一个姓名

#### Scenario: 多人多号归属不清
- **WHEN** 同一签章块存在多名待核验人员和多个身份证号且原文不能证明逐一归属
- **THEN** Prepare SHALL 保留全部人员、号码和 `association_state=UNCERTAIN` 的候选关系
- **AND** 系统 SHALL NOT 按顺序、距离或实时预设进行配对

#### Scenario: 同角色签署结构无法唯一解释
- **WHEN** 同一签章块中存在多个同角色人员或栏位，现有可靠证据无法唯一证明其是一个栏位多人还是多个独立栏位
- **THEN** 系统 SHALL 抛出 `NeedsConfirmationError`
- **AND** 系统 SHALL NOT 合并、拆分或选择任一栏位作为自动装配结果

#### Scenario: 账户来自块外收款条款
- **WHEN** 主合同块外条款以可靠证据明确账户属于某主体且用于本合同收款或结算
- **THEN** Prepare SHALL 保留账户字段、主体、用途和证据
- **AND** 该观察 SHALL NOT 虚构 `signature_block_key`

#### Scenario: 签章来源缺口与可靠空结果
- **WHEN** 已可靠完成某文档的签章范围扫描且没有发现签章事实
- **THEN** 该文档 `signature` coverage SHALL 为 `COMPLETE`
- **WHEN** 可定位来源缺口只影响签章域的部分事实类别
- **THEN** 该文档 coverage SHALL 为 `PARTIAL`
- **WHEN** 可定位来源缺口明确影响签章块、签署栏位/人员、人员证件关联、签署日期以及账户/联系观察的全部适用类别
- **THEN** 该文档 coverage SHALL 为 `UNAVAILABLE`

### Requirement: amount_payment 保留所有显式金额与付款事实
`AmountPaymentFacts` SHALL 包含 `amounts[]`、`amount_relations[]`、`payment_methods[]` 和 `payment_stages[]`。每个金额 SHALL 使用唯一 `amount_key`，分别以带状态的观察保存数字金额、大写金额原文、币种、税务口径、语义角色和证据；十进制金额与比例规范化值 SHALL 使用十进制字符串而非浮点数。付款阶段 SHALL 使用 `payment_stage_key`，保存名称、明示顺序、比例、金额引用、触发条件、期限、方式和证据。只有原文明示时 SHALL 建立 `CONTRACT_OVERALL` 关系。

#### Scenario: 数字金额与大写金额只有一侧
- **WHEN** 某一业务位置只可靠出现数字金额或只出现大写金额
- **THEN** Prepare SHALL 保留该金额对象和已出现一侧的原文证据
- **AND** 未出现一侧 SHALL 使用相应字段状态
- **AND** 系统 SHALL NOT 补写、反推或删除该金额对象

#### Scenario: 同值金额位于不同业务位置
- **WHEN** 两处金额数值相同但业务位置、语义角色或关系不同
- **THEN** Prepare SHALL 生成两个不同 `amount_key`
- **AND** 两个对象 SHALL 各自保留证据和关系

#### Scenario: 付款阶段算术
- **WHEN** 原文包含合同整体金额、付款比例和阶段金额
- **THEN** Prepare SHALL 只保留原文事实和关系
- **AND** Prepare SHALL NOT 计算期望阶段金额、比例合计、差额、舍入或尾差调整
- **AND** 大写金额中的 `圆`、`点` 等原文 SHALL NOT 被静默改写

### Requirement: copy_terms 只保留主合同文本份数事实
`CopyTermsFacts` SHALL 包含 `statements[]`、可选 `overall_total_statement_key` 和 `allocations[]`。陈述 SHALL 使用 `statement_key`、`scope_key`、原文、整数观察和证据；分配 SHALL 使用 `allocation_key`、陈述引用、主体候选及 `EACH|COLLECTIVE|UNCERTAIN`。整体总份数索引 SHALL 只引用已有原文明示陈述，不得由各方份数或附件数量计算。

#### Scenario: 各方份数存在但没有整体总份数
- **WHEN** 主合同只写明各方各执份数而未明示整体总份数
- **THEN** Prepare SHALL 保留所有 allocation 事实
- **AND** `overall_total_statement_key` SHALL 被省略
- **AND** Prepare SHALL NOT 计算并写回整体总份数

#### Scenario: 附件自身份数声明
- **WHEN** 附件文本写有自身份数
- **THEN** 该值 SHALL NOT 补足或冲突 `copy_terms` 的主合同总份数

### Requirement: attachment_manifest 只保留声明、候选和中性关系
`AttachmentManifestFacts` SHALL 包含 `declared_total`、`declarations[]`、`logical_attachment_candidates[]` 和 `links[]`。物理实际附件集合 SHALL 只来自 `source_snapshot.attachments`。关系 SHALL 使用 `LINKED|UNCERTAIN`；`LINKED` SHALL 只引用一个实际文档，`UNCERTAIN` MAY 引用一个或多个候选。没有关系时不得生成伪记录；Prepare SHALL NOT 输出 `MISSING`、`EXTRA`、`NO_LINK_ESTABLISHED`、标题一致性或正式等级。

#### Scenario: 一个上传文件含多个逻辑附件候选
- **WHEN** 一个上传文件中可靠识别出多个顶层逻辑附件范围但尚未由管理员确认
- **THEN** Prepare SHALL 保留 0..N 个带父文档和局部范围的逻辑候选
- **AND** 这些候选 SHALL NOT 自动增加 `source_snapshot.attachments` 数量
- **AND** 这些候选 SHALL NOT 被当作可靠关联

#### Scenario: 声明没有可关联来源
- **WHEN** 主合同存在附件声明但没有建立任何可靠或候选关系
- **THEN** Prepare SHALL 保留声明并不生成 link
- **AND** Prepare SHALL NOT 输出附件缺失结论

### Requirement: 跨结构标识和引用具有明确唯一范围
`document_key` 和 `evidence_id` SHALL 在整个 `ReviewContext` 内唯一；`party_key`、`designation_key`、`mention_key`、签章实体键、金额/付款键、份数键和附件清单键 SHALL 在各自声明集合内唯一。所有引用 SHALL 指向类型正确的现存目标。键 SHALL 从规范化业务坐标确定生成，不得使用随机 UUID、数组顺序、模型自由文案或证据返回顺序；本变更不承诺这些键跨合同版本稳定。

#### Scenario: 输入数组顺序变化
- **WHEN** 两次准备包含相同规范化文档、事实、关系和证据，但输入附件或模型候选数组顺序不同
- **THEN** 稳定键和输出排序 SHALL 保持一致
- **AND** `document_set_hash` SHALL 保持一致

#### Scenario: 悬空跨域引用
- **WHEN** 一个签章、份数、金额或附件关系引用不存在或类型不匹配的目标键
- **THEN** 组装校验 SHALL 失败
- **AND** 系统 SHALL NOT 返回成功上下文

### Requirement: Prepare 元数据和摘要解释本次准备语义
`preparation_meta` SHALL 包含 `pipeline_version`、`prompt_bundle_hash`、`model_deployment` 和 `created_at`。`pipeline_version` SHALL 随预处理、分段、提取编排、确定性后处理、证据或稳定键语义变化而升级；`prompt_bundle_hash` SHALL 覆盖全部 Prepare Prompt 和模型输出 Schema。来源、事实、关系、证据和问题 SHALL 在计算摘要前确定性排序。`context_digest` SHALL 继续保护除自身外的完整上下文，但不得作为业务幂等键。

#### Scenario: 相同文件快照重新准备
- **WHEN** 相同 `contract_id/revision_id/document_set_hash` 因 Prepare 升级再次生成上下文
- **THEN** 系统 SHALL 生成新的完整不可变 `ReviewContext`
- **AND** 新上下文 SHALL 明确记录实际 `pipeline_version`、Prompt 摘要、模型部署和创建时间
- **AND** 系统 SHALL NOT 原地覆盖或假定 `context_digest` 必须与旧上下文相同

### Requirement: 技术失败不得伪装成覆盖不足
模型超时、调用失败、输出截断、格式或 Schema 重试耗尽、内嵌附件/长文安全扫描与局部提取链未完整执行、证据组装失败、引用不闭合或上下文摘要生成失败 SHALL 使整个 Prepare 请求失败，使用项目现有参数、模型调用、超时、格式或未知错误语义。`PARTIAL/UNAVAILABLE` SHALL 只表示能够定位到具体文档和事实类别的来源提取或证据覆盖缺口。

#### Scenario: 模型输出达到长度上限
- **WHEN** 任一必需 Prepare 模型调用返回 `finish_reason=length` 且重试后仍不能形成完整强类型输出
- **THEN** 系统 SHALL 返回模型格式/输出过长错误
- **AND** 系统 SHALL NOT 返回部分 `ReviewContext`

#### Scenario: Markdown 局部表格丢列
- **WHEN** Markdown 非空且其他范围可可靠提取，但某一文档局部表格丢列使特定事实类别无法看清
- **THEN** 系统 MAY 将该文档对应覆盖标记为 `PARTIAL`
- **AND** 问题 SHALL 指明文档和受影响事实类别
- **AND** 已可靠事实和证据 SHALL 保留

### Requirement: 四类标准附件只做清单处理、安全扫描和必要局部提取
首期标准附件目录 SHALL 只包含需求说明书、技术规范书、工作说明书和质量标准四类，以及逐项经过业务审核并进入版本化目录的同义名称；没有明确列入目录的名称 SHALL NOT 自动生效。只有附件边界可靠、文档内部身份有证据、正文结构可交叉印证且没有身份冲突时，Prepare 才可应用标准附件路径。文件名、文本长度或宽泛关键词 SHALL NOT 单独触发该路径；目录外类型、补充协议、商务协议以及类型或边界不可靠的附件 SHALL 执行普通完整提取。

可靠识别的标准附件 SHALL 完整进入附件清单和来源快照，并对规范化 Markdown 全文执行确定性安全扫描。扫描 SHALL 覆盖主体定义/称谓、签署区、法人或授权人、人员与身份证号关联、签署日期、账户及公司级联系方式；无候选且扫描完整时 SHALL 结束内容处理，相关域 MAY 以完整覆盖和空事实结束。扫描命中时 SHALL 仅对带可验证坐标的局部范围执行相关事实提取。系统 SHALL NOT 对整份标准附件做全文 LLM 语义展开，也 SHALL NOT 运行时学习或由模型自动扩充目录。扫描、定位、局部提取或组装任一步未完成 SHALL 使整个 Prepare 请求失败。

#### Scenario: 四类标准附件安全扫描无命中
- **WHEN** 一份可靠识别的需求说明书、技术规范书、工作说明书或质量标准完成全文确定性安全扫描且没有相关事实候选
- **THEN** 该附件仍 SHALL 保留完整清单、来源、摘要、声明关系和覆盖
- **AND** 相关事实域 MAY 以 `COMPLETE` 和空事实结束
- **AND** 系统 SHALL NOT 对整份附件发起全文 LLM 语义提取

#### Scenario: 四类标准附件安全扫描命中
- **WHEN** 全文安全扫描命中主体、签章、人员、签署日期、账户或公司级联系方式候选
- **THEN** Prepare SHALL 仅对带可验证坐标的局部范围执行对应事实域提取
- **AND** 所得事实和证据 SHALL 归属于该附件 `document_key`

#### Scenario: 类型或边界不可靠
- **WHEN** 附件只在文件名中出现目录名称、内部身份或结构不能交叉确认、存在身份冲突，或者属于补充协议、商务协议等目录外类型
- **THEN** Prepare SHALL NOT 应用标准附件路径
- **AND** 该附件 SHALL 执行普通完整提取

#### Scenario: 安全扫描或局部处理未完成
- **WHEN** 安全扫描、候选定位、局部提取、证据装配或结果合并因内部错误或执行中断未完成
- **THEN** Prepare SHALL 整体失败
- **AND** 系统 SHALL NOT 把未处理范围伪装成 `COMPLETE`、`PARTIAL` 或免检

### Requirement: Prepare 不输出裁决或消费预设主数据
Prepare 响应 SHALL 只包含来源、事实、候选、状态、关系、证据、覆盖、准备问题和版本元数据。Prepare SHALL NOT 输出 `PASS/WARN/FAIL`、不适用、暂未完成审核、`check_key`、`reason_key`、Evaluate `issue_key`、旧 SeqN/B-1/B-4 结果、规则包结果、人工放行或流程指令。Prepare SHALL NOT 调用或接收签署地预设主数据，也不得生成 `our_party_key`、最终 `identity_basis`、已核验签署人集合或主体级最终选值。

#### Scenario: 合同事实明显缺失或冲突
- **WHEN** Prepare 可靠确认一个业务字段缺失、留空、格式无效或存在冲突候选
- **THEN** 系统 SHALL 通过字段状态、候选和证据表达该事实
- **AND** 域覆盖 MAY 保持 `COMPLETE`
- **AND** 响应 SHALL NOT 包含正式等级或阻断命令

#### Scenario: 请求携带预设或历史审核结果
- **WHEN** 调用方在严格请求模型中增加预设主数据、历史检查结果或人工放行字段
- **THEN** 系统 SHALL 拒绝额外字段
- **AND** Prepare SHALL NOT 使用这些数据改变来源事实

### Requirement: 新旧流程和敏感数据保持隔离
Prepare 实现 SHALL 位于 `app/capabilities/contract_review/two_stage/`，不得调用 `run_review_pipeline`、旧 Prompt、旧结果组装或旧预设查询。现有旧接口和测试期望 SHALL 保持不变。本项目 SHALL NOT 持久化 Markdown 或 `ReviewContext`。合同来源身份证号、银行账号和联系值 MAY 作为事实及精确证据进入返回上下文，但 SHALL NOT 进入普通日志、Trace、指标标签或异常消息；Prepare 日志 SHALL 只记录调用名、时长、token、重试和状态等非业务元数据。

#### Scenario: Prepare 成功处理含身份证号合同
- **WHEN** 合同原文可靠包含待保留的身份证号事实
- **THEN** `ReviewContext` MAY 保留该合同原文事实和证据
- **AND** 普通日志与错误消息 SHALL NOT 回显完整号码、完整 Markdown 或证据引文

#### Scenario: 旧接口回归
- **WHEN** 新 Prepare 模块和路由被注册
- **THEN** `/api/v1/contract-review` 和 `/api/v1/contract-review/upload-md` SHALL 继续使用旧独立流水线
- **AND** 两条路径 SHALL NOT 共享请求状态、事实对象或检查结果
