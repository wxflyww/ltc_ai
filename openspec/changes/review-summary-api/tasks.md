# Tasks — review-summary-api

> 完成标志：现有测试 838+490 全绿 + 新增 review_summary 测试全绿 + `openspec validate review-summary-api --strict` is valid。
> 红线：唯一侵入点 = `app/main.py` +2 行；不碰 `contract_review` 整包 / `two_stage` / `translate` / `core` / `llm.py` / 现有 prompts、config 键、tests、Docker 件（设计 §7.2.1）。

## 0. 收口说明

> 本节为 §4/§5 收口证据。基线口径以窗口 A 报告为准（只增不减）；`.venv` Python 3.11.9、`PYTHONPATH=.` 全量运行。
> ⚠️ 本节数字为 W4 收尾时点快照；归档前补强（§6）后最新证据以 §6.4 为准。

- **本 change 自有测试**：`tests/test_review_summary_*.py`（7 个文件）**115 passed / 0 failed**。
- **全量回归 `pytest tests/`**：**989 passed / 20 failed / 1 skipped**（窗口 A 基线 890 → 只增不减 ✓）。
- **全量回归 `pytest tests/two_stage/`**：**526 passed / 20 failed**（窗口 A 基线 515 → 只增不减 ✓）。
- **20 个失败全部为既有 checkpoint 用例**：`test_m2_signature_replay.py`（19）+ `test_m2_signature_diagnostic.py`（1），根因是缺 `%TEMP%\m2-header-checkpoint-retirement-02.json` 等快照文件，属其他在途工作、与本 change 无关，**如实记录不修**；非 m2 失败经 grep 核对为 **0**。
- **隔离守卫**：既有文件唯一改动 = `app/main.py` **+2/−0**（1 行 `import review_summary_router` + 1 行 `include_router`），`git diff --numstat app/main.py` 佐证；`review_summary` 包对 `contract_review`/`translate`/`two_stage` **零 sibling-capability import**，仅消费 `app.core.*`（基础设施）与 `app.models.llm`（模型适配层）的稳定公开 API、未改动其源文件；`llm.py` 单例经 call-site `bind(extra_body=...)` 使用、原 `extra_body` 恒 `None`，由常驻 `test_thinking_scope_guard.py` 断言（含在 989 passed 内）。工作树中 `llm.py`、`two_stage/*`、`config-test.yaml`、docs 的改动属窗口 A 的独立治理在途项，**不在本 change 白名单**。
- **OpenSpec 校验**：`openspec.cmd validate review-summary-api --strict --no-interactive` → `Change 'review-summary-api' is valid`，exit 0。
- **5.4 真实 vLLM 端点联调**：按 design D5 登记为**上线前补验**，非首版验收前置，保持未勾选。

## 1. 骨架与契约

- [x] 1.1 新建 `app/capabilities/review_summary/` 包骨架（`__init__.py`/`schemas.py`/`service.py`/`router.py`/`cache.py`）与 `prompts/review_summary.yaml`
- [x] 1.2 先写失败测试，再实现输入 Schema：四组数据（`contract_meta` 整组可选、`route_reason` 可选、`risk_register` 12 字段全可选、`opinions` 必填可空 + `action` 枚举），未定义字段 `extra` 按既有能力口径处理，"未知新增可选字段不拒绝"有用例
- [x] 1.3 先写失败测试，再实现输出 Schema：`review_summary`（text+source_refs）/`key_concerns[]`（escalation|risk）/`opinion_details[]`/`degraded_sections[]`，与设计 §4 示例逐字段对齐
- [x] 1.4 `app/main.py` +2 行注册 router（全仓唯一既有文件改动；先确认改动行数恰为 2）
- [x] 1.5 TestClient API 契约测试：鉴权壳、`code=0` 整包四字段、非法请求 422+10001 且模型调用 0 次

## 2. 装配区与生成管线

- [x] 2.1 实现装配区：提级块置首 + 风险项按传入顺序跟排 + 12 字段原文照搬（缺字段行不渲染）+ 意见详情骨架按传入顺序；纯确定性代码，零模型参与
- [x] 2.2 实现 Prompt 加载与消息构造（参照 translate 能力包模式，独立 yaml）：总述 + 意见摘要两任务，嵌入五条铁律与 reject 中性化指令；CRM 暂缓期总述不写客户评价
- [x] 2.3 实现模型调用接线：`get_chat_model()` 单例 + `bind(extra_body={"chat_template_kwargs":{"enable_thinking":False}})`；SDK `max_retries=0`；业务层仅解析失败重试 1 次；错误映射复用 20001/20002/20003
- [x] 2.4 先写失败测试，再实现 source_refs 服务端校验：无引用或悬空引用（含数组越界）的结论直接丢弃；总述丢弃 → `text=null` + `review_summary.model` 标记，摘要丢弃 → `summary=null` + `opinion_details.model` 标记；丢弃不阻塞装配区
- [x] 2.5 先写失败测试，再实现 reject 中性化服务端校验：存在 `action=reject` 时总述正面定性直接判失败走丢弃/降级路径

## 3. 空态矩阵与缓存

- [x] 3.1 按设计 §5.1 六行空态矩阵逐行编写用例（含两行"非降级 SHALL 为空数组"的负向断言），实现 `degraded_sections` 逻辑
- [x] 3.2 先写失败测试，再实现规范化输入 hash 缓存（一期进程内内存实现，零新增依赖、零 config 键）：同输入命中不发起模型调用、任一字段变更自动失效

## 4. 测试与回归

- [x] 4.1 五条铁律常驻用例齐备：source_refs 悬空丢弃、reject 中性化、数字零生成（输出中的金额/比例与输入逐字一致）、事实单点归属（总述不展开装配区数字条款）、形容词铁律（CRM 缺位不写客户评价）——`test_summary_system_prompt_embeds_the_five_rules` 逐条断言"数字零生成/事实单点归属/溯源/形容词/中性/客户评价"，另有悬空丢弃、reject 正面定性丢弃、词表强制、装配区逐字数字等硬校验用例
- [x] 4.2 模型层边界统一 mock，`tests/test_review_summary_*.py` 全绿（115 passed）
- [x] 4.3 全量回归：`pytest tests/` 989 passed（基线 890，只增不减）、`pytest tests/two_stage/` 526 passed（基线 515，只增不减）；20 failed 全部为既有 `test_m2_signature_replay.py`/`test_m2_signature_diagnostic.py` 缺 checkpoint 失败，本 change 自有测试零改动既有测试文件，如实记录不修
- [x] 4.4 隔离守卫：`review_summary` 未修改 `contract_review`、`translate`、`two_stage`、`core`、`llm.py` 源文件；对上述包零 sibling-capability import，仅经稳定公开 API 消费 `app.core`/`app.models.llm`；`llm.py` 原单例 `extra_body` 恒 `None` 不受 call-site `bind()` 影响（`test_thinking_scope_guard.py` 常驻）

## 5. 收口与文档

- [x] 5.1 回填本文件 checkbox 并在顶部加「§0 收口说明」（证据：测试通过数 + validate 结果）
- [x] 5.2 `openspec.cmd validate review-summary-api --strict` 输出 is valid
- [x] 5.3 `.workbuddy/memory/` 当日日志记录立项与实施结论、必要时更新 `MEMORY.md` 长期条目
- [ ] 5.4 真实 vLLM 端点联调（非首版验收前置，登记为上线前补验）：demo 样例全链路跑通，记录耗时与 token；缓存命中/失效各验一次

## 6. 归档前补强（2026-10-03，本窗口）

> 背景：§0 验收观察发现铁律 1 的 spec 承诺（"服务端强制"）超出实际实现（当时仅 Prompt 层）。经用户选定"归档前补完"，先补代码再归档，避免不实措辞随 delta 提升为正式 spec。

- [x] 6.1 数字抽验（TDD 先行）：新增 `tests/test_review_summary_number_guard.py` 8 用例（RED 阶段 6 failed + 2 条正面控制通过），再在 `service.py` 实现 `_NUMBER_TOKEN`/`_input_number_corpus`/`_numbers_are_verifiable`，总述与逐条意见摘要两处接入，失败走 D4 丢弃/降级；语料=规范化请求体 JSON（与缓存键同源）
- [x] 6.2 `RouteReason.text` 收紧为 `Field(min_length=1)`：空串 → 422+10001，schema 层与 API 层用例各 1（含在 6.1 的 8 用例内）
- [x] 6.3 spec 措辞如实化：铁律前言改为分层表述（1 限阿拉伯数字 token/3/5 服务端兜底，2/4 Prompt 约束）、新增「含编造数字的 AI 结论被丢弃」场景、缓存条款补 `.model` 降级不写缓存、输入契约补 `route_reason.text` 非空、回归场景基线措辞去掉硬编码只增不减；design.md 补 D6（抽验范围 + 两处已知宽松 + 时机决策）；proposal.md 同步铁律分工与回归口径措辞
- [x] 6.4 重测证据：`tests/test_review_summary_*.py` 8 文件 **123 passed**（§0 基线 115 + 新增 8）；`pytest tests/` **997 passed / 20 failed / 1 skipped**（§0 基线 989，只增不减；20 failed 仍全为 `test_m2_signature_replay.py` 19 + `test_m2_signature_diagnostic.py` 1 的缺快照环境性失败，分组计数核对非 m2 失败 = 0）；`pytest tests/two_stage/` **526 passed / 20 failed**（与 §0 一致）
- [x] 6.5 `openspec.cmd validate review-summary-api --strict` → is valid（见本窗口令执行记录）
