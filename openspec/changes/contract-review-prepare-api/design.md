## Context

`contract-review-context-foundation` 已在 `app/capabilities/contract_review/two_stage/` 建立 `ReviewContext` 基础信封、来源快照判别联合、摘要算法和消费前校验，但 `FactDomain.data`、证据容器和准备问题仍是过渡结构，也没有对外路由或实际事实提取。当前旧接口把全文提取、实时预设查询和正式裁决放在同一流水线中，不能作为 Prepare 的实现复用。

本变更是两阶段升级四个 OpenSpec 中的第二个。调用方是合同系统：它只在销售确认“已全部上传”且当前版本全部有效文件解析完成后发送完整 Markdown 快照，并保存返回的 `ReviewContext`。本项目仍无业务数据库；系统预设主数据只属于后续 Evaluate；旧接口继续独立运行。

六个 Prepare 事实域的业务范围已在升级方案中闭合。本设计只将已确认范围收敛成字段、类型、引用和实现边界，不在此变更中裁决任何检查点，也不重新定义旧 SeqN/B-1/B-4 的结果结构。

## Goals / Non-Goals

**Goals:**

- 提供可鉴权、可追踪的 JSON-only Prepare API，并返回一份完整、不可变、可摘要验证的 `ReviewContext`。
- 将六个事实域、统一证据、逐文档覆盖和准备问题强类型化，使 Evaluate 只依赖该契约即可读取全部首期检查所需来源事实。
- 在模型调用前拒绝不合法输入和明确重复附件；保留疑似重复和可定位的来源覆盖缺口。
- 以高召回语义提取配合确定性规范化、证据定位和引用校验，保留多候选、冲突和不确定性，不让模型输出正式等级。
- 保证同一规范化输入、相同准备语义版本和相同模型结构输出具有确定的键、排序、文档集合摘要和上下文摘要语义。
- 与旧流水线、预设查询、持久化和正式裁决保持物理与责任隔离。

**Non-Goals:**

- 不新增 `/prepare` 的 multipart 入口，不改变旧 `/contract-review` 或 `/upload-md`。
- 不实现 Evaluate、规则包、正式 `PASS/WARN/FAIL`、不适用、暂未完成审核或人工放行。
- 不调用、接收或保存签署地预设主数据，不生成 `our_party_key`、`identity_basis` 或运行时主体签署信息汇总。
- 不建设数据库、异步任务系统、通用规则引擎、合同类型枚举、上下文存储或签名 URL。
- 不迁移附件金额与主合同金额比较；`amount_payment` 首期只提取主合同金额和付款事实。
- 不用固定模板词表、最多三条候选或单一样例限制高召回事实。

## Decisions

### 1. API 使用统一响应壳，`data` 直接承载 `ReviewContext`

新增 `POST /api/v1/contract-review/prepare`。请求模型如下：

```text
PrepareRequest
  contract_id: NonBlankStr
  revision_id: NonBlankStr
  main_document: PrepareMainDocumentInput
  uploaded_attachments: list[PrepareUploadedAttachmentInput] = []
  parser_meta?: ParserMeta

PrepareMainDocumentInput
  document_id: NonBlankStr
  filename: NonBlankStr
  markdown: NonBlankNormalizedMarkdown
  source_file_sha256?: Sha256Digest

PrepareUploadedAttachmentInput
  attachment_id: NonBlankStr
  filename: NonBlankStr
  markdown: NonBlankNormalizedMarkdown
  source_file_sha256?: Sha256Digest
```

成功响应沿用 `{code,message,data,traceId,duration_seconds}`，其中 `data` 是完整 `ReviewContext`，不再增加一层 `review_context`，避免同一对象存在两个包装语义。失败响应 `data=null`。`uploaded_attachments` 是当前版本全部有效上传附件的完整快照，允许 `0..N`；正文内嵌附件不由调用方重复传入。

备选方案是新增 multipart 或返回 `review_context_id`。前者与合同系统已保存 Markdown 的链路重复，后者会暗示本项目可按 ID 反查持久化数据，因此不采用。

### 2. `review-context/v1` 在首次对外前完成强类型收敛

基础模块尚未对外消费，故本变更保留 `schema_version=review-context/v1`，但以强类型模型替换过渡结构：

```text
ReviewContext
  schema_version: "review-context/v1"
  source_snapshot: SourceSnapshot
  shared_facts: SharedFacts
  evidence_index: EvidenceIndex
  preparation_issues: list[PreparationIssue]
  preparation_meta: PreparationMeta
  context_digest: Sha256Digest

SharedFacts
  header: FactDomain[HeaderFacts]
  parties: FactDomain[PartiesFacts]
  signature: FactDomain[SignatureFacts]
  amount_payment: FactDomain[AmountPaymentFacts]
  copy_terms: FactDomain[CopyTermsFacts]
  attachment_manifest: FactDomain[AttachmentManifestFacts]
```

不保留任意 JSON `data` 或按证据类别分组的旧容器作为公开兼容入口。因为基础信封从未注册生产 API，此收敛不是对调用方的破坏性变更。

### 3. 公共状态、覆盖、问题和观察值使用可引用的强类型

```text
FactState = COMPLETE | PARTIAL | UNAVAILABLE
Presence = ABSENT | PRESENT_EMPTY | PRESENT_VALUE | UNCERTAIN
NormalizationState = NOT_APPLICABLE | VALID | INVALID | UNCERTAIN

FactDomain[T]
  state: FactState
  coverage: list[DocumentCoverage]
  data: T
  issues: list[FactIssue]

DocumentCoverage
  document_key: DocumentKey
  state: FactState
  affected_fact_kinds: list[NonBlankStr]
  fact_issue_keys: list[FactIssueKey]

FactIssue
  fact_issue_key: FactIssueKey
  code: NonBlankStr
  message: NonBlankStr
  related_document_keys: non_empty_list[DocumentKey]
  affected_fact_kinds: non_empty_list[NonBlankStr]
  evidence_ids: list[EvidenceId]

PreparationIssue
  preparation_issue_key: PreparationIssueKey
  code: NonBlankStr
  message: NonBlankStr
  related_document_keys: non_empty_list[DocumentKey]
  evidence_ids: list[EvidenceId]

ObservedField[TObservation]
  presence: Presence
  normalization_state: NormalizationState
  observations: list[TObservation]

ObservedValue[T]
  raw_text: str
  normalized_value?: T
  evidence_ids: non_empty_list[EvidenceId]
```

`ObservedField` 必须保留“没有发现字段”和“发现字段但明确留空”的结构差异：`ABSENT` 使用空 `observations[]` 且 `normalization_state=NOT_APPLICABLE`；`PRESENT_EMPTY` 至少包含一条 `raw_text=""`、`evidence_ids` 非空的观察，并使用 `normalization_state=NOT_APPLICABLE`；`PRESENT_VALUE` 至少包含一条实质观察；`UNCERTAIN` 必须保留造成不确定性的候选或来源观察及其证据，不得静默选主值。`NOT_APPLICABLE` 只表示当前没有可规范化的实质值，因此可与 `ABSENT` 或 `PRESENT_EMPTY` 搭配，不得与已有可规范化实质值的状态搭配。

`COMPLETE` 域和覆盖不得引用覆盖问题；`PARTIAL/UNAVAILABLE` 必须引用至少一个能解释缺口的 `FactIssue`。Prepare 的 `fact_issue_key`、`preparation_issue_key` 只标识准备问题，不得命名为 Evaluate 专用的 `issue_key`。字段缺失、显式留空、已取得的无效文本、同值重复、异值冲突或原文语义歧义属于事实状态，不写入覆盖问题。技术失败不创建残缺上下文。

域的 `coverage` 只包含该域适用的文档：`header`、`amount_payment`、`copy_terms` 固定只含 `main`；`parties`、`signature`、`attachment_manifest` 必须逐一覆盖 `main` 和快照中全部上传/内嵌附件。覆盖完整且没有观察值仍是 `COMPLETE`，不得伪造空白事实。

### 4. 统一证据注册表是事实的唯一原文证据来源

```text
EvidenceIndex
  items: list[EvidenceItem]

EvidenceItem
  evidence_id: EvidenceId
  document_key: DocumentKey
  source_locator: MarkdownCharLocator
  quote: NonEmptyStr
```

`evidence_id` 在整个 `ReviewContext` 内唯一；所有 `evidence_ids`、`fact_issue_keys`、文档键和跨域键必须解析到且只解析到一个目标。`source_locator` 固定为 `markdown-chars:{start}-{end}`，按规范化 Markdown 的 Unicode code point、左闭右开计数；切片必须与 `quote` 完全相同。模型只提供短引文候选，后端在正确文档范围唯一定位后生成证据。定位歧义或失败降低对应事实/覆盖，不得制造位置。

内嵌附件证据使用派生文档的局部坐标；其来源快照另以绝对 `source_locator` 指向完整主 Markdown，形成两跳追溯。证据不携带自由 `attributes`，避免把核心事实藏入非强类型扩展。

### 5. `header` 和 `parties` 按已冻结结构定稿

```text
HeaderFacts
  contract_identity: IdentityGroup
  project_identity: IdentityGroup
  signing_location: ObservedField[SigningLocationObservation]
  signing_date: ObservedField[ObservedValue[IsoDate]]

IdentityGroup
  name: ObservedField[NameObservation]
  number: ObservedField[ObservedValue[str]]

NameObservation extends ObservedValue[str]
  specificity: SPECIFIC | GENERIC | UNCERTAIN

SigningLocationObservation
  raw_text: str
  normalized_value?: str
  city_candidates: list[str]
  evidence_ids: non_empty_list[EvidenceId]

PartiesFacts
  canonical_parties: list[CanonicalParty]
  party_mentions: list[PartyMention]

CanonicalParty
  party_key: PartyKey
  declared_name: ObservedField[ObservedValue[str]]
  declared_designations: list[DeclaredDesignation]
  definition_evidence_ids: non_empty_list[EvidenceId]

DeclaredDesignation
  designation_key: DesignationKey
  kind: CONTRACT_ROLE | NAME_ALIAS | UNCERTAIN
  text: NonBlankStr
  evidence_ids: non_empty_list[EvidenceId]

PartyMention
  mention_key: MentionKey
  document_key: DocumentKey
  mention_kind: PARTY_DEFINITION | PARTY_APPELLATION | ROLE_REFERENCE
  observed_text: NonBlankStr
  referenced_designation_keys: list[DesignationKey]
  explicit_entity_name?: ObservedField[ObservedValue[str]]
  candidate_party_keys: list[PartyKey]
  local_definition_state: PRESENT | ABSENT | UNCERTAIN | NOT_APPLICABLE
  comparison_state: MATCHED_DECLARATION | OUTSIDE_DECLARED_SET | UNCERTAIN | NOT_APPLICABLE
  evidence_ids: non_empty_list[EvidenceId]
```

只有主合同签约方定义区生成 `canonical_parties`；正文和附件只生成 `party_mentions`。Prepare 不生成我方/客户侧最终分类，不用附件或实时预设修改主合同基准，也不限制签约方或观察数量。

### 6. `signature` 使用真实块、独立实体和显式关系

为同时表达一个块多个栏位、一个栏位多人、多号不确定归属、替代组、块外账户/联系观察以及跨块复用，采用实体加引用，不依赖数组位置：

```text
SignatureFacts
  signature_blocks: list[SignatureBlock]
  signer_slots: list[SignerSlot]
  alternative_signer_groups: list[AlternativeSignerGroup]
  signer_candidates: list[SignerCandidate]
  identity_number_candidates: list[IdentityNumberCandidate]
  person_id_relations: list[PersonIdRelation]
  signing_date_observations: list[SignatureDateObservation]
  account_observations: list[SignatureFieldObservation]
  contact_observations: list[SignatureFieldObservation]

SignatureBlock
  signature_block_key: SignatureBlockKey
  document_key: DocumentKey
  party_binding_state: BOUND | UNBOUND | UNCERTAIN
  party_key?: PartyKey
  candidate_party_keys: list[PartyKey]
  local_company_name: ObservedField[ObservedValue[str]]
  evidence_ids: non_empty_list[EvidenceId]

SignerSlot
  signer_slot_key: SignerSlotKey
  signature_block_key: SignatureBlockKey
  role_text: NonBlankStr
  role_state: ELIGIBLE_SIGNER | IRRELEVANT_PERSON | UNCERTAIN
  presence: Presence
  signer_keys: list[SignerKey]
  identity_number_keys: list[IdentityNumberKey]
  evidence_ids: non_empty_list[EvidenceId]

AlternativeSignerGroup
  signer_group_key: SignerGroupKey
  signer_slot_keys: non_empty_list[SignerSlotKey]
  relation_state: CONFIRMED | UNCERTAIN
  evidence_ids: non_empty_list[EvidenceId]

SignerCandidate
  signer_key: SignerKey
  signer_slot_key: SignerSlotKey
  raw_name: NonBlankStr
  normalized_name?: NonBlankStr
  evidence_ids: non_empty_list[EvidenceId]

IdentityNumberCandidate
  identity_number_key: IdentityNumberKey
  signer_slot_key?: SignerSlotKey
  raw_text: NonBlankStr
  normalized_value?: NonBlankStr
  normalization_state: VALID | INVALID | UNCERTAIN
  evidence_ids: non_empty_list[EvidenceId]

PersonIdRelation
  signer_key: SignerKey
  identity_number_key: IdentityNumberKey
  association_state: DIRECT | UNIQUE_IN_BLOCK | UNCERTAIN
  evidence_ids: non_empty_list[EvidenceId]

SignatureDateObservation
  signature_date_key: SignatureDateKey
  signature_block_key: SignatureBlockKey
  party_key?: PartyKey
  field: ObservedField[ObservedValue[IsoDate]]

SignatureFieldObservation
  field_observation_key: SignatureFieldObservationKey
  document_key: DocumentKey
  signature_block_key?: SignatureBlockKey
  party_binding_state: BOUND | UNBOUND | UNCERTAIN
  party_key?: PartyKey
  candidate_party_keys: list[PartyKey]
  field_kind: BANK_NAME | BANK_ACCOUNT | ACCOUNT_HOLDER |
              ADDRESS | PHONE | FAX | WEBSITE | POSTAL_CODE
  purpose_state: CONFIRMED | UNCERTAIN | NOT_APPLICABLE
  purpose_text?: NonBlankStr
  field: ObservedField[ObservedValue[str]]
```

签署人栏位和签署日期必须引用真实签章块；账户/联系观察可以来自块外合格来源，此时不伪造 `signature_block_key`。只有当前文档证据可靠确定主体时才设置 `party_key`。身份证号只是合同来源事实；Prepare 不用预设值反向关联人员或选择候选。

### 7. `amount_payment` 保留所有显式金额和付款关系，不计算裁决值

金额和比例的规范化值使用十进制字符串，不使用二进制浮点数：

```text
AmountPaymentFacts
  amounts: list[AmountFact]
  amount_relations: list[AmountRelation]
  payment_methods: list[PaymentMethodObservation]
  payment_stages: list[PaymentStage]

AmountFact
  amount_key: AmountKey
  document_key: "main"
  semantic_role: ObservedField[ObservedValue[str]]
  numeric_amount: ObservedField[ObservedValue[DecimalString]]
  uppercase_amount: ObservedField[ObservedValue[str]]
  currency: ObservedField[ObservedValue[str]]
  tax_treatment: ObservedField[ObservedValue[str]]
  evidence_ids: non_empty_list[EvidenceId]

AmountRelation
  amount_relation_key: AmountRelationKey
  amount_key: AmountKey
  relation_kind: CONTRACT_OVERALL | PRICING_COMPONENT | PAYMENT_STAGE
  relation_state: CONFIRMED | UNCERTAIN
  payment_stage_key?: PaymentStageKey
  evidence_ids: non_empty_list[EvidenceId]

PaymentMethodObservation
  payment_method_key: PaymentMethodKey
  raw_text: NonBlankStr
  normalized_value?: NonBlankStr
  evidence_ids: non_empty_list[EvidenceId]

PaymentStage
  payment_stage_key: PaymentStageKey
  name: ObservedField[ObservedValue[str]]
  sequence: ObservedField[ObservedValue[int]]
  ratio_percent: ObservedField[ObservedValue[DecimalString]]
  amount_keys: list[AmountKey]
  trigger_condition: ObservedField[ObservedValue[str]]
  payment_term: ObservedField[ObservedValue[str]]
  payment_method_keys: list[PaymentMethodKey]
  evidence_ids: non_empty_list[EvidenceId]
```

同值但不同业务位置、角色或关系的金额保持不同 `amount_key`。数字金额和大写金额可独立存在；原文中的 `圆`、`点` 等不得在 Prepare 被改写。`CONTRACT_OVERALL` 关系必须有原文关系证据，不能从数值相等、分项或阶段合计推导。Prepare 不计算阶段金额、比例合计、人民币大写期望值或尾差。

### 8. `copy_terms` 以原文陈述为唯一份数事实

```text
CopyTermsFacts
  statements: list[CopyStatement]
  overall_total_statement_key?: StatementKey
  allocations: list[CopyAllocation]

CopyStatement
  statement_key: StatementKey
  scope_key: ScopeKey
  document_key: "main"
  raw_text: NonBlankStr
  count: ObservedField[ObservedValue[int]]
  evidence_ids: non_empty_list[EvidenceId]

CopyAllocation
  allocation_key: AllocationKey
  statement_key: StatementKey
  candidate_party_keys: list[PartyKey]
  allocation_semantics: EACH | COLLECTIVE | UNCERTAIN
  evidence_ids: non_empty_list[EvidenceId]
```

`overall_total_statement_key` 只能引用一条已有且被原文明示为整体总份数的 `CopyStatement`；不得由 allocations 相加产生，也不得复制第二份权威值。附件份数和附件声明数量不进入本域。

### 9. `attachment_manifest` 只表达集合事实和正向/候选关系

```text
AttachmentManifestFacts
  declared_total: ObservedField[ObservedValue[int]]
  declarations: list[AttachmentDeclaration]
  logical_attachment_candidates: list[LogicalAttachmentCandidate]
  links: list[AttachmentRelation]

AttachmentDeclaration
  attachment_declaration_key: AttachmentDeclarationKey
  title: ObservedField[ObservedValue[str]]
  ordinal: ObservedField[ObservedValue[int]]
  evidence_ids: non_empty_list[EvidenceId]

LogicalAttachmentCandidate
  logical_attachment_candidate_key: LogicalAttachmentCandidateKey
  parent_document_key: DocumentKey
  title: ObservedField[ObservedValue[str]]
  source_locator: MarkdownCharLocator
  evidence_ids: non_empty_list[EvidenceId]

AttachmentRelation
  attachment_relation_key: AttachmentRelationKey
  attachment_declaration_key: AttachmentDeclarationKey
  candidate_document_keys: non_empty_list[DocumentKey]
  relation_state: LINKED | UNCERTAIN
  evidence_ids: non_empty_list[EvidenceId]
```

实际物理附件集合以 `source_snapshot.attachments` 为唯一事实来源，manifest 不复制身份、内容或哈希。`LINKED` 必须且只能指向一个实际来源；`UNCERTAIN` 可指向一个或多个候选。没有关系时不生成记录；Prepare 不生成 `MISSING`、`EXTRA`、`NO_LINK_ESTABLISHED` 或标题一致性结论。逻辑候选不自动计入实际附件数量。

### 10. Prepare 流水线按失败边界分段，四类标准附件使用安全扫描

固定编排顺序为：请求校验与规范化 → 摘要及输入文档模型 → 内嵌附件边界识别 → 明确重复门禁 → 逐域候选召回/语义提取 → 确定性规范化与关系装配 → 证据唯一定位和切片验证 → 覆盖/问题聚合 → 引用完整性与稳定排序 → `document_set_hash`/`context_digest` 生成。

任一模型超时、调用失败、输出截断、Schema/格式重试耗尽、证据装配失败或内部引用无法闭合时，请求整体失败且不返回 `ReviewContext`。`PARTIAL/UNAVAILABLE` 只用于 Markdown 已存在但某一可定位来源范围确实未被可靠看清的情况。

首期标准附件目录只包含需求说明书、技术规范书、工作说明书和质量标准四类，以及未来逐项经过业务审核并进入版本化目录的同义名称；当前没有明确列入目录的同义名称不得自行启用。标准附件资格至少要求附件边界可靠、文档内部身份有证据、正文结构可交叉印证且没有身份冲突；文件名、篇幅或宽泛关键词不能单独触发该路径。目录外类型、补充协议、商务协议以及类型或边界不可靠的附件继续执行普通完整提取。

可靠识别的四类标准附件仍完整进入 `attachment_manifest`，保存标题、编号、边界、来源、内容摘要、声明关联和覆盖。随后对其规范化 Markdown 全文执行低成本确定性安全扫描，扫描范围必须覆盖主体定义/称谓（包括“甲方/乙方应……”类用法）、签署区、法人或授权人、人员与身份证号关联、签署日期、账户及公司级联系方式。扫描无候选且完整执行时，相关事实域可按“已完整检查但没有事实”结束内容处理；扫描命中时，只把带绝对坐标的章节、表格、签章区或相邻窗口交给对应事实域做局部语义提取，不展开整份标准附件。

扫描、候选定位、局部提取、证据装配或结果合并任一步未完整执行时，请求整体失败，不返回残缺上下文。扫描器和目录不得运行时自学习或由模型自动扩充；未来新增类型或同义名称须经过业务确认并升级目录版本及 `pipeline_version`。

### 11. 重复门禁区分明确重复与疑似重复

在首次模型调用前拒绝：重复 `attachment_id`；不同 ID 但规范化文件名和 `parsed_content_sha256` 同时相同的上传附件；规范化标题和内容哈希同时相同的内嵌/上传附件。错误沿用 `10001` 参数错误语义，并列出冲突身份/名称，不新增业务数据库或跨请求历史判断。

仅同名或仅内容哈希相同的不同 ID 附件继续处理，在 `preparation_issues` 形成结构化疑似重复记录。正文内只有标题而无实质内容时只形成附件声明，不生成空内嵌来源。

### 12. 稳定键、排序和版本边界由业务坐标决定

所有键在同一 `ReviewContext` 的各自声明范围内唯一，并从规范化业务坐标确定生成，不使用数组顺序、随机 UUID、模型自由文本或证据输出顺序。`document_key`、`evidence_id` 和跨域键不承诺跨合同版本稳定；相同输入和相同准备语义必须可复现。

组装前对来源、事实候选、关系、证据和问题按明确字段排序。`pipeline_version` 覆盖预处理、分段、Prompt/Schema 编排、确定性后处理、证据和键语义；`prompt_bundle_hash` 覆盖全部 Prepare Prompt 与模型输出 Schema。`created_at` 参与上下文摘要，因此相同输入的两次准备允许 `context_digest` 不同；调用方不得把它当业务幂等键。

### 13. 日志与敏感数据边界沿用项目基础设施但更严格

Prepare 可以把合同中的身份证号、账户和联系信息作为事实与精确证据写入返回的完整 `ReviewContext`，因为它们本已存在于合同系统保存的 Markdown 中。普通日志、Trace、指标标签、异常消息和模型审计元数据不得记录完整 Markdown、Prompt、证据引文、身份证号、银行账号或联系值；只记录调用名称、时长、token、重试次数、状态和非业务摘要。

Prepare 不调用签署地预设接口，且不得把任何预设字段加入请求、Prompt、上下文或缓存。备选的 HMAC/专用等值令牌会增加不必要的密钥体系且不能替代传输鉴权，首期不采用。

## Risks / Trade-offs

- [强类型事实模型较大] → 按六域拆分 Schema/提取器和独立测试，公共类型只承载确实共享的状态、证据和引用语义。
- [LLM 输出可能遗漏高召回候选] → 不设三条上限，保留分段覆盖和候选；后端不静默选主值，真实端点验收与 mock 契约测试分开记录。
- [稳定键算法实现不一致] → 在实现前为同值不同位置、同位置多证据、输入顺序变化和重复值建立固定测试向量；键不使用数组序号。
- [证据定位造成长文开销] → 四类标准附件先做全文确定性安全扫描，只将命中窗口交给模型；模型返回短引文，后端在正确文档/局部范围定位，重叠窗口按最终坐标去重，统一注册表复用同一证据。
- [同一 `review-context/v1` 与基础实现不同] → 基础信封尚未暴露 API，本变更一次性替换过渡结构；严格契约测试阻止部署混用旧内部模型。
- [可定位覆盖缺口与技术失败混淆] → 技术、模型、Schema、引用和装配失败整体失败；只有来源文本或局部证据确实无法可靠取得时才生成 `PARTIAL/UNAVAILABLE`。
- [旧规则与新事实边界漂移] → 全检查点迁移矩阵只用于验证事实依赖；Prepare 不复制旧结果、不调用旧流水线、不因当前代码偏差删除事实。

## Migration Plan

1. 先以契约测试将基础信封升级为六域强类型模型和统一证据注册表，保持旧路由未引用新服务。
2. 按公共输入/证据/覆盖基础、六域提取器、组装校验和 API 路由分批实现，每批使用失败测试驱动。
3. 定点验证 `tests/two_stage/`、新 API 契约和受影响旧合同评审回归；严格校验 OpenSpec 与 Git 范围。
4. 部署后由合同系统在非生产试点环境发送“已全部上传”的完整快照并保存 JSON；在 Evaluate 尚未上线前不切换管理员正式检查入口。
5. 回退时停止合同系统调用新端点并移除新路由注册；旧接口仍独立可用。已经保存的 `ReviewContext` 作为审计数据保留，但不得交给不支持其契约的 Evaluate。

## Open Questions

无阻塞业务问题。具体 Prompt 文案、模型调用分段阈值、稳定键编码格式和错误类内部命名属于实现细节，但必须满足本设计的可复现、无截断、引用闭合和对外错误语义，并由测试固定。
