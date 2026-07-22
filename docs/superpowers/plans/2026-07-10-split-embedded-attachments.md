# 内嵌附件拆分实现计划

> **给执行代理的要求：** 实现本计划时必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，逐项执行并用复选框跟踪状态。

**目标：** 在合同组织评审接收到 Markdown 合同正文后，先把合同正文中的内嵌附件拆成附件文本，并从主合同正文中移除，再复用现有后续检查链路。

**架构：** 新增一个小而独立的 Markdown 附件拆分模块，只负责识别独立成行的附件标题并返回“清理后的合同正文 + 拆出的附件列表”。`service._preprocess_request()` 调用该模块，把拆出的附件排在上传附件之前，后续 A-1a/A-1b/A-3/A-4/B-1/B-4 逻辑保持不变。

**技术栈：** Python 3.11、FastAPI 能力包结构、Pydantic、pytest、OpenSpec。

---

## 文件结构

- 新增：`app/capabilities/contract_review/embedded_attachments.py`
  - 职责：识别合同 Markdown 中独立成行的附件标题，拆分附件正文。
- 修改：`app/capabilities/contract_review/service.py`
  - 职责：在 `_preprocess_request()` 中接入拆分器，使用清理后的合同正文和合并后的附件列表。
- 新增：`tests/test_contract_review_embedded_attachments.py`
  - 职责：覆盖附件标题识别、正文移除、非标题引用忽略。
- 修改：`tests/test_contract_review_service.py`
  - 职责：覆盖预处理集成和 B-4 能收到拆分后的附件。
- 修改：`openspec/changes/split-embedded-attachments/tasks.md`
  - 职责：实现完成后勾选 OpenSpec tasks。

---

### 任务 1：为拆分器添加失败测试

**文件：**
- 新增：`tests/test_contract_review_embedded_attachments.py`

- [ ] **步骤 1：写入拆分器单元测试**

```python
from app.capabilities.contract_review.embedded_attachments import split_embedded_attachments


def test_extracts_three_embedded_attachments_and_removes_from_contract():
    contract_md = """# 合同

甲方：客户公司
乙方：我方公司

附件一
技术规范内容

附件二：
报价明细内容

## 附件3
服务承诺内容
"""

    cleaned, attachments = split_embedded_attachments(contract_md)

    assert "甲方：客户公司" in cleaned
    assert "附件一" not in cleaned
    assert "技术规范内容" not in cleaned
    assert [item["title"] for item in attachments] == ["附件一", "附件二", "附件3"]
    assert [item["text"] for item in attachments] == [
        "附件一\n技术规范内容",
        "附件二：\n报价明细内容",
        "## 附件3\n服务承诺内容",
    ]
    assert [item["filename"] for item in attachments] == ["附件一.md", "附件二.md", "附件3.md"]
    assert all(item["source"] == "合同正文内嵌" for item in attachments)


def test_does_not_split_inline_attachment_references():
    contract_md = """# 合同

本合同详见附件一。
附件一式三份，甲乙双方各执一份。
正文继续。
"""

    cleaned, attachments = split_embedded_attachments(contract_md)

    assert cleaned == contract_md
    assert attachments == []


def test_no_embedded_attachments_keeps_contract_unchanged():
    contract_md = "# 合同\n\n甲方：客户公司\n乙方：我方公司\n"

    cleaned, attachments = split_embedded_attachments(contract_md)

    assert cleaned == contract_md
    assert attachments == []
```

- [ ] **步骤 2：运行测试确认红灯**

```powershell
.venv/Scripts/python -m pytest tests/test_contract_review_embedded_attachments.py -q
```

预期：失败，原因是 `embedded_attachments` 模块尚不存在。

---

### 任务 2：实现内嵌附件拆分器

**文件：**
- 新增：`app/capabilities/contract_review/embedded_attachments.py`
- 测试：`tests/test_contract_review_embedded_attachments.py`

- [ ] **步骤 1：实现拆分器**

```python
import re


_ATTACHMENT_HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(附件\s*(?:[一二三四五六七八九十]+|\d+))\s*[：:、.]?\s*$"
)


def _match_attachment_heading(line: str) -> str | None:
    match = _ATTACHMENT_HEADING_RE.match(line)
    if not match:
        return None
    return re.sub(r"\s+", "", match.group(1))


def _make_attachment(title: str, lines: list[str], index: int) -> dict:
    text = "\n".join(lines).strip()
    return {
        "index": index,
        "filename": f"{title}.md",
        "file_type": "md",
        "title": title,
        "source": "合同正文内嵌",
        "text": text,
    }


def split_embedded_attachments(contract_md: str) -> tuple[str, list[dict]]:
    lines = contract_md.splitlines()
    cleaned_lines: list[str] = []
    attachments: list[dict] = []
    current_title: str | None = None
    current_lines: list[str] = []

    for line in lines:
        title = _match_attachment_heading(line)
        if title is not None:
            if current_title is not None:
                attachments.append(_make_attachment(current_title, current_lines, len(attachments) + 1))
            current_title = title
            current_lines = [line]
            continue

        if current_title is None:
            cleaned_lines.append(line)
        else:
            current_lines.append(line)

    if current_title is not None:
        attachments.append(_make_attachment(current_title, current_lines, len(attachments) + 1))

    if not attachments:
        return contract_md, []

    cleaned = "\n".join(cleaned_lines).rstrip()
    if contract_md.endswith("\n") and cleaned:
        cleaned += "\n"
    return cleaned, attachments
```

- [ ] **步骤 2：运行单元测试确认绿灯**

```powershell
.venv/Scripts/python -m pytest tests/test_contract_review_embedded_attachments.py -q
```

预期：通过。

---

### 任务 3：接入合同评审预处理

**文件：**
- 修改：`app/capabilities/contract_review/service.py`
- 修改：`tests/test_contract_review_service.py`

- [ ] **步骤 1：添加预处理集成测试**

在 `tests/test_contract_review_service.py` 的 service import 中加入 `_preprocess_request`，并新增：

```python
def test_preprocess_request_splits_embedded_attachments_and_merges_uploaded():
    request = ContractReviewRequest(
        contract_md="# 合同\n\n正文内容\n\n附件一\n内嵌附件内容\n",
        attachments=[
            AttachmentInput(index=10, filename="上传附件.md", file_type="md", text="上传附件内容"),
        ],
    )

    prepared = _preprocess_request(request)

    assert "正文内容" in prepared["full_text"]
    assert "内嵌附件内容" not in prepared["full_text"]
    assert [item["filename"] for item in prepared["attachments"]] == ["附件一.md", "上传附件.md"]
    assert prepared["attachments"][0]["text"] == "附件一\n内嵌附件内容"
    assert prepared["attachments"][0]["source"] == "合同正文内嵌"
    assert "【附件】附件一.md" in prepared["full_text_and_attachments"]
    assert "【附件】上传附件.md" in prepared["full_text_and_attachments"]
```

- [ ] **步骤 2：运行测试确认红灯**

```powershell
.venv/Scripts/python -m pytest tests/test_contract_review_service.py::test_preprocess_request_splits_embedded_attachments_and_merges_uploaded -q
```

预期：失败，因为 `_preprocess_request()` 尚未接入拆分器。

- [ ] **步骤 3：接入拆分器**

在 `service.py` 中新增 import：

```python
from app.capabilities.contract_review.embedded_attachments import split_embedded_attachments
```

将 `_preprocess_request()` 改为：

```python
def _preprocess_request(request: ContractReviewRequest) -> dict:
    contract_md, embedded_attachments = split_embedded_attachments(request.contract_md)
    uploaded_attachments = [item.model_dump() for item in request.attachments]
    attachment_dicts = [*embedded_attachments, *uploaded_attachments]
    full_text_and_attachments = contract_md
    if attachment_dicts:
        attachment_text = "\n\n".join(
            f"【附件】{item.get('filename')}\n{item.get('text', '')}"
            for item in attachment_dicts
        )
        full_text_and_attachments = f"{contract_md}\n\n{attachment_text}"
    return {
        "full_text": contract_md,
        "full_text_and_attachments": full_text_and_attachments,
        "attachments": attachment_dicts,
    }
```

- [ ] **步骤 4：运行预处理测试确认绿灯**

```powershell
.venv/Scripts/python -m pytest tests/test_contract_review_service.py::test_preprocess_request_splits_embedded_attachments_and_merges_uploaded -q
```

预期：通过。

---

### 任务 4：验证 B-4 收到合并后的附件

**文件：**
- 修改：`tests/test_contract_review_service.py`

- [ ] **步骤 1：添加流水线测试**

新增：

```python
def test_run_review_pipeline_sends_embedded_and_uploaded_attachments_to_b4():
    request = ContractReviewRequest(
        contract_md="# 合同\n甲方：客户公司\n乙方：我方公司\n\n附件一\n内嵌附件内容",
        attachments=[
            AttachmentInput(index=2, filename="附件二.md", text="上传附件二"),
            AttachmentInput(index=3, filename="附件三.md", text="上传附件三"),
        ],
    )
    outputs = [
        '{"header":{"contract_name":"测试合同","project_name":null,"project_number":null,"contract_number":"HT-1","signing_location":"沈阳","signing_date":"2026年7月8日","parties":[{"role":"甲方","name":"客户公司"},{"role":"乙方","name":"我方公司"}]},"signature_parties":[{"role":"甲方","name":"客户公司"},{"role":"乙方","name":"我方公司"}],"sections":[]}',
        '{"signature":{"role":"乙方","name":"我方公司","legal_rep_name":"张三","signing_date":"2026年7月8日","bank_name":"招商银行","bank_account":"123456","account_holder":"我方公司","address":"地址","phone":"024-12345678","fax":"","website":"","postal_code":"110000"}}',
        '{"currency":"人民币","payment_method":"电汇","total_amount_numeric":"100","total_amount_uppercase":"壹佰元整","total_amount_match":true,"payment_stages":[]}',
        '{"copies":{"total_copies":2,"party_copies":[{"role":"甲方","copies":1},{"role":"乙方","copies":1}]},"attachments_declared":[{"index":1,"title":"附件一","content_embedded_in_contract":false},{"index":2,"title":"附件二","content_embedded_in_contract":false},{"index":3,"title":"附件三","content_embedded_in_contract":false}],"total_declared":3}',
        '{"checks":[]}',
        '{"checks":[]}',
        '{"checks":[]}',
        '{"checks":[]}',
    ]
    b4_texts = []

    def fake_invoke(model, messages, response_format=None):
        content = messages[-1].content
        if "【当前附件】" in content:
            b4_texts.append(content)
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            with patch("app.capabilities.contract_review.service.fetch_preset") as fake_fetch:
                fake_fetch.return_value = SystemPreset(
                    entity_name="我方公司",
                    legal_rep_name="张三",
                    legal_rep_id_number="",
                    authorized_reps=[],
                    bank_name="招商银行",
                    bank_account="123456",
                    account_holder="我方公司",
                    address="地址",
                    phone="024-12345678",
                    fax="",
                    website="",
                    postal_code="110000",
                )
                items = run_review_pipeline(request)

    assert len(b4_texts) == 3
    assert any("内嵌附件内容" in text for text in b4_texts)
    assert any("上传附件二" in text for text in b4_texts)
    assert any("上传附件三" in text for text in b4_texts)
    assert all(item.result != "FAIL" for item in items if item.id == "附件检查-数量标题")
```

- [ ] **步骤 2：运行流水线测试**

```powershell
.venv/Scripts/python -m pytest tests/test_contract_review_service.py::test_run_review_pipeline_sends_embedded_and_uploaded_attachments_to_b4 -q
```

预期：通过。

---

### 任务 5：OpenSpec 与最终验证

**文件：**
- 修改：`openspec/changes/split-embedded-attachments/tasks.md`

- [ ] **步骤 1：勾选 OpenSpec tasks**

将 `openspec/changes/split-embedded-attachments/tasks.md` 中所有任务改为 `[x]`。

- [ ] **步骤 2：运行 OpenSpec 校验**

```powershell
openspec.cmd validate split-embedded-attachments --strict
```

预期：输出 `Change 'split-embedded-attachments' is valid`。

- [ ] **步骤 3：运行完整验证**

```powershell
.venv/Scripts/python -m pytest tests/ -q
```

预期：通过。

```powershell
.venv/Scripts/python -c "from app.main import create_app; app=create_app(register_middleware=False); print('routes', len(app.routes))"
```

预期：输出类似 `routes 8`。

```powershell
git diff --check
```

预期：退出码为 0。Windows 换行提示可以接受，空白错误不可接受。

---

## 自检

- OpenSpec change 的三个场景都有测试覆盖：全部在正文中、全部为上传附件、正文和上传附件混合。
- 拆分器只识别独立成行的附件标题，不识别“详见附件一”“附件一式三份”等正文引用。
- 拆出的附件从主合同正文移除，但仍进入附件列表。
- `_preprocess_request()` 是唯一接入点，后续检查链路保持现有结构。
- 计划中没有占位内容。

---

## 已完成增量（2026-07 会话追加）

本计划落地后，已完成以下增强并在代码中生效：

- 长度问题分类：区分“输入上下文超长”和“模型输出截断”。
- 阻断项业务化：
    - 输入超长返回 `模型上下文长度`（`FAIL` + `硬阻断`）。
    - 输出截断返回 `模型输出长度`（`FAIL` + `硬阻断`）。
- B-1 可追溯增强：
    - `name` 输出为 `称谓一致性-<范围>`。
    - `reason` 增加 `【范围】<范围>` 前缀。
- B-1 结果治理：重复告警去重，过滤非称谓噪声。
- 审计增强：模型调用异常事件（含重试异常）记录 `length_issue=input|output` 分类信息。

## 验证结果（2026-07 会话）

- 合同评审相关回归通过，含：
    - 输出长度截断阻断项测试。
    - 调用异常审计事件测试。
    - B-1 范围前缀与去重测试。
    - 中间件链路 HTML 审计落盘测试。
- 阶段性汇总结果：`47 passed, 1 warning`。

## 文档同步状态

- OpenSpec 已同步：
    - `openspec/changes/split-embedded-attachments/proposal.md`
    - `openspec/changes/split-embedded-attachments/tasks.md`
    - `openspec/changes/split-embedded-attachments/specs/contract-review/spec.md`
- Superpowers 已同步：
    - `docs/superpowers/plans/2026-07-10-split-embedded-attachments.md`
    - `docs/superpowers/specs/2026-07-07-contract-review-design.md`

