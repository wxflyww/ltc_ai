# B-4 金额基准与证据校验 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 使 B-4 附件总价结论可追溯至合同正文和当前附件原文，并保证 B-4 的结果与阻断级别一致。

**Architecture:** A-3 新增总价正文引文；服务端仅将经正文验证的数值与引文传递给 B-4。B-4 对金额观察执行范围和数值校验后生成固定原因，其余 B-4 项维持现有解析路径，最后统一由结果推导阻断级别。

**Tech Stack:** Python、Pydantic JSON Schema、LangChain、pytest、OpenSpec。

---

### Task 1: 先定义并验证金额证据契约

**Files:**
- Modify: `app/capabilities/contract_review/response_formats.py`
- Modify: `prompts/contract_review.yaml`
- Test: `tests/test_contract_review_service.py`

- [x] 写失败测试：A-3 schema 要求 `total_amount_evidence`；B-4 schema 要求金额观察字段；流水线发送的 B-4 基准含经验证的总价和正文原文。
- [x] 运行 `.venv\Scripts\python.exe -m pytest tests/test_contract_review_service.py -k "b4 or amount_evidence" -v`，确认测试因字段或基准尚未实现而失败。
- [x] 用最小 schema 和提示词修改满足失败测试，不改变既有 A-3 数值字段和 B-4 非金额 `reason` 字段。

### Task 2: 校验 B-4 金额观察

**Files:**
- Modify: `app/capabilities/contract_review/service.py`
- Test: `tests/test_contract_review_service.py`

- [x] 写失败测试：正文和附件证据均有效且金额不同生成可追溯 `FAIL`；伪造附件证据或缺少正文证据不生成金额 `FAIL`。
- [x] 运行相应测试并确认其在实现前失败。
- [x] 新增小型基准构建和金额观察校验函数；仅接受 `check_type=total_amount`、匹配 A-3 基准和当前附件证据的观察。
- [x] 再次运行相应测试并确认通过。

### Task 3: B-4 阻断级别归一化与回归

**Files:**
- Modify: `app/capabilities/contract_review/service.py`
- Test: `tests/test_contract_review_service.py`
- Modify: `openspec/changes/b4-amount-evidence-validation/tasks.md`

- [x] 写失败测试：B-4 `PASS + 硬阻断` 输出归一为 `PASS + 通过`。
- [x] 运行测试并确认其在实现前失败。
- [x] 在 B-4 解析边界按 `RESULT_TO_BLOCK_LEVEL` 归一所有项，不修改其他检查点的全局规则。
- [x] 运行 B-4 定向、合同评审服务、全量测试，以及 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\change_orchestrator.ps1 -Mode validate -ChangeName b4-amount-evidence-validation` 和 `git diff --check`。
