# B-1 称谓一致性证据校验 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 仅对首页定义之外、且在当前正文或附件中有可验证证据的签约方称谓生成 B-1 告警。

**Architecture:** A-1a 在既有签约方记录中保留明确简称。B-1 接收结构化观察结果；服务端验证角色、基准称谓、发现称谓、证据范围和证据类型后，构造既有 `CheckItem`。

**Tech Stack:** Python、FastAPI、Pydantic、LangChain、pytest、OpenSpec。

---

### Task 1: 定义模型输出契约

**Files:**
- Modify: `app/capabilities/contract_review/schemas.py`
- Modify: `app/capabilities/contract_review/response_formats.py`
- Modify: `prompts/contract_review.yaml`
- Test: `tests/test_contract_review_service.py`

- [x] 为 `ContractParty` 增加 `aliases`，要求 A-1a 仅提取首部签约方定义中明确声明的简称。
- [x] 为 B-1 定义独立观察 schema，包含角色、基准、发现称谓、证据片段和证据类型。

### Task 2: 验证并生成 B-1 结果

**Files:**
- Modify: `app/capabilities/contract_review/service.py`
- Test: `tests/test_contract_review_service.py`

- [x] 先写失败测试，覆盖结构化观察、附件角色未定义、附件主体定义不一致、主体定义与明确简称匹配和真实别称。
- [x] 仅接受角色和基准匹配、证据片段位于当前分段且证据类型为 `party_appellation` 或 `party_definition` 的观察；附件角色未定义单独生成提示。
- [x] 对合同/项目名称、背景引用、跨范围证据和首页已声明简称返回 `PASS`；附件角色未定义返回 `WARN`。

### Task 3: 执行回归与规范校验

**Files:**
- Modify: `openspec/changes/b1-appellation-evidence-validation/tasks.md`

- [x] 运行合同评审测试、全量测试和 OpenSpec 严格校验。
- [x] 复查变更范围，不纳入既有 `tmp/` 内容。

### Task 4: 收敛 B-1 呈现文案

**Files:**
- Modify: `app/capabilities/contract_review/service.py`
- Test: `tests/test_contract_review_service.py`

- [x] 先写失败测试，覆盖旧模型 `PASS` 空原因及结构化告警的证据引文格式。
- [x] B-1 `PASS` 输出空 `reason`；统一为 `证据“原文”。`，不使用“证据：”。