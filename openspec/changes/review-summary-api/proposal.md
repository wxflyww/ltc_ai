# 评审智能总结 0.2 接口立项

> 唯一事实源：`docs/integration/2026-10-02-review-summary-design.md`（设计定稿 2026-10-02，改动边界经 2026-10-03 确认）。本文与 spec 均以设计文档为准，冲突时以设计文档为准并回改本文。

## Why

- 合同审批详情页需要「评审智能总结」面板：审批人打开页面时，合同系统传入评审环节结构化数据，AI 接口返回整包面板 JSON，合同系统零业务理解渲染。
- 现有能力（`contract-review` 评审/预填、`translate`）均不覆盖"评审数据 → 面板总结"这一产品；0.1（approval-summary）方案已作废，0.2 设计已完成前置评审、碰头清单清零并定稿。
- 设计承诺的工程约束（独立能力包、唯一侵入点 `main.py` +2 行、错误码零新增）需要以 OpenSpec change 固化为可验收契约。

## What Changes

- 新增 JSON-only 接口 `POST /api/v1/review-summary`，命名统一 **review-summary**（弃用 0.1 的 approval-summary）。
- 输入契约四组：`contract_meta`（整组可选、字段全 optional、可扩展，CRM 客户字段暂缓）、`route_reason`（可选，合同系统已生成人话原文照搬）、`risk_register[]`（合同系统预选，只含高风险项，12 字段全可选照搬）、`opinions[]`（必填数组可为 `[]`，`action` 枚举 `pass/conditional/reject`）。
- 响应为整包面板 JSON（第一原则）：`review_summary`（AI 总述）+ `key_concerns[]`（提级块固定置首 + 风险项按传入顺序）+ `opinion_details[]`（骨架照搬 + AI 摘要）+ `degraded_sections[]`。
- AI 生成仅两处（总述、单节点意见摘要），其余全部原文装配；防幻觉五条铁律：数字零生成、事实单点归属、source_refs 服务端校验（无引用或悬空引用的结论直接丢弃）、总述形容词可溯源（CRM 暂缓期不写客户评价）、存在 `reject` 时总述中性化。服务端兜底三项（铁律 1 的阿拉伯数字 token 抽验、铁律 3 溯源校验、铁律 5 正面定性词表），铁律 2/4 由 Prompt 约束（分工与已知宽松见 design.md D6）。
- 空态矩阵 6 场景与 `degraded_sections` 标记归接口侧单一实现；模型调用失败复用统一错误码 20001/20002/20003，不新增错误码。
- 实时生成 + 规范化输入内容 hash 缓存，输入任何变更自动失效，合同系统无需通知。
- 模型调用与现行能力共用 `get_chat_model()` 单例（只消费 `bind()` 返回的新对象），关闭思考走 `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`；SDK 层 `max_retries=0`，业务层仅解析失败重试 1 次。
- 改动边界（设计 §7.2.1）：🔴 不碰 `contract_review` 整包、`two_stage/**`、`translate/**`、`app/models/llm.py`、`app/core/` 全部、现有 prompts/config 键/tests/Docker 件；🟡 唯一侵入点 `app/main.py` +2 行；🟢 全新建 `app/capabilities/review_summary/`、`prompts/review_summary.yaml`、`tests/test_review_summary_*.py`。

## Capabilities

### New Capabilities

- `review-summary`：评审环节结构化数据 → 评审智能总结面板整包 JSON 的独立能力，与 `contract-review` 零依赖。

### Modified Capabilities

无。`contract-review`（MVP 评审 + 预填）的请求、响应、检查逻辑与测试期望一律不变。

## Impact

- API：新增 `POST /api/v1/review-summary`；沿用统一响应壳（`code`/`message`/`traceId`/`duration_seconds`）、`X-API-Key`/`Bearer` 鉴权与 `X-Trace-Id` 中间件，零新码零新壳。
- 代码：新建 `app/capabilities/review_summary/` 整包（schemas/service/router/cache/prompts 装配）；`app/main.py` +2 行注册 router，为全仓唯一既有文件改动。
- 配置与依赖：一期零改动——配置硬编码默认值、现有依赖够用、`tests/conftest.py` 现有 fixture 自动重置单例；确需时只新增、不改既有键。
- 测试：新增 `tests/test_review_summary_*.py`（模型边界 mock + TestClient API 契约；空态矩阵与五条铁律须有常驻用例）；现有测试相对立项基线（838/490，立项时实际已漂移，口径以 tasks.md §0/§6 为准）只增不减，是"没碰"的回归证明。
- 调用方：合同系统负责数据正确性/一致性、只传高风险项、回退重审只传当前有效轮、`route_reason` 传现成人话、`action` 按枚举传；面板建议异步加载，调用失败时整体降级不阻塞审批。
- ⚠️ 非代码影响：与评审/预填共用同一 vLLM 实例且应用侧无并发闸门，上线后会挤占 GPU 算力，上线节奏需留意。
