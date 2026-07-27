# 附件标题智能匹配 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用最小确定性规范化和私有化模型批量语义判断，减少附件标题格式差异造成的误报，并在不确定时保留人工确认提示。

**Architecture:** `attachments.py` 负责标题规范化、唯一精确匹配、模型候选构造和映射校验；`service.py` 仅在存在未匹配候选时调用新的结构化提示词。附件检查只接受后端验证的一对一 `MATCH` 映射，其他情况保持未匹配状态。

**Tech Stack:** Python、FastAPI、LangChain、OpenAI 兼容私有化模型、Pytest、OpenSpec。

---

### Task 1: 标题规范化与映射校验

**Files:**

- Modify: `tests/test_contract_review_attachments.py`
- Modify: `app/capabilities/contract_review/attachments.py`

- [x] **Step 1: 写入失败测试**

```python
def test_build_attachment_title_match_plan_matches_normalized_filename_once():
    plan = build_attachment_title_match_plan(
        [{"index": 1, "title": "价格明细表", "content_embedded_in_contract": False}],
        [{"index": 1, "filename": "附件1：价格明细表.md"}],
    )
    assert plan["matches"] == [{"declared_id": "declared-0", "uploaded_id": "uploaded-0"}]
```

- [x] **Step 2: 验证测试失败**

运行：`.venv\Scripts\python.exe -m pytest tests/test_contract_review_attachments.py::test_build_attachment_title_match_plan_matches_normalized_filename_once -q`

预期：因 `build_attachment_title_match_plan` 尚不存在而失败。

- [x] **Step 3: 写入最小实现并验证通过**

实现路径、扩展名、附件序号前缀和格式符号的规范化；只有两侧均唯一的相同规范化标题直接映射。验证：`.venv\Scripts\python.exe -m pytest tests/test_contract_review_attachments.py -q`。

### Task 2: 私有化模型批量匹配

**Files:**

- Modify: `prompts/contract_review.yaml`
- Modify: `app/capabilities/contract_review/response_formats.py`
- Modify: `app/capabilities/contract_review/service.py`
- Modify: `app/capabilities/contract_review/attachments.py`
- Test: `tests/test_contract_review_service.py`
- Test: `tests/test_contract_review_prompts.py`

- [x] **Step 1: 写入失败的服务级测试**

测试未匹配的“价格明细表”与“附件1：价格明细表2.11.md”会触发新提示词；模型返回 `MATCH` 后不再输出标题未匹配提示。另测 `UNCERTAIN` 和重复候选标识保持提示。

- [x] **Step 2: 验证测试失败**

运行：`.venv\Scripts\python.exe -m pytest tests/test_contract_review_service.py -k attachment_title -q`。

预期：因新提示词尚未被调用或映射尚未使用而失败。

- [x] **Step 3: 实现结构化提示词和条件调用**

模型对每个未匹配上传附件返回 `uploaded_id`、可空 `declared_id`、`judgement` 与 `reason`；`judgement` 仅允许 `MATCH`、`MISMATCH`、`UNCERTAIN`。后端仅接受候选存在且一对一的 `MATCH`。

- [x] **Step 4: 验证服务与提示词测试通过**

运行：`.venv\Scripts\python.exe -m pytest tests/test_contract_review_service.py tests/test_contract_review_prompts.py -q`。

### Task 3: 回归和交付

**Files:**

- Modify: `openspec/changes/attachment-title-matching/tasks.md`
- Modify: `docs/superpowers/plans/2026-07-27-attachment-title-matching.md`

- [x] **Step 1: 更新任务状态**

将完成项目从 `- [ ]`更新为 `- [x]`。

- [x] **Step 2: 运行全量验证**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_attachments.py tests/test_contract_review_service.py tests/test_contract_review_prompts.py -q
.venv\Scripts\python.exe -m pytest tests/ -q
openspec.cmd validate attachment-title-matching --strict
git diff --check
```

- [ ] **Step 3: 提交变更**

只暂存本次 change、计划、提示词、附件匹配实现和测试文件；不暂存 `tmp/`。提交信息：`feat(contract-review): match attachment titles semantically`。