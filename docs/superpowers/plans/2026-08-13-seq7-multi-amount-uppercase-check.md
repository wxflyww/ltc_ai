# Seq7 多金额中文大写校验实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` before writing implementation code. 逐项执行，不得 commit、push 或 archive。

**Goal:** 序号7只校验有原文证据的金额事实，正确检查合同总金额明确性，杜绝将报价或推导值伪造成合同总金额。

**Architecture:** A-3 提取金额事实、证据和整体金额依据；`sanitize_amount_payment_facts()` 验证证据、保留单侧事实并生成来源键；`check_amount_payment()` 进行 `FAIL/WARN/PASS` 裁决。两阶段 API 和旧序号10数字匹配不改动。

**Tech Stack:** Python 3.11、FastAPI、Pydantic JSON Schema、`decimal.Decimal`、pytest、OpenSpec。

---

## 范围与前提

只允许修改 `prompts/contract_review.yaml`、`response_formats.py`、`amounts.py`、`checks.py`、`service.py`、相关四个合同评审测试文件和当前 change 的任务状态。禁止改动 `two_stage/**`、B-1/B-4、序号8/9、旧序号10、接口外壳和上游解析器。

工作区已有未提交变更。开始前检查 `git status --short` 与相关 diff，只做最小叠加；不得 reset、checkout、revert 或清理无关文件。

## Task 1: 建立 RED 回归

**Files:** `tests/test_contract_review_amounts.py`、`tests/test_contract_review_checks.py`、`tests/test_contract_review_service.py`

- [ ] 同一谈判含税报价同时在 `amount_pairs[]` 和 `total_amount_*` 出现、但 `contract_overall_evidence` 为空：报价只校验一次，另有 `FAIL` 原因“合同没有明确总金额”，不得出现该报价被称为合同总金额或合同总价。
- [ ] 原文“合同总金额为 4690000 元，人民币（大写）肆佰陆拾玖万元整”识别为整体金额，不得因无“合同总价”字样报缺失。
- [ ] 对合同整体金额、报价和付款阶段分别写仅数字与仅大写用例：均为 `WARN`，原因分别为“没有对应的大写金额”和“没有对应的数字金额”。完整不一致仍为 `FAIL`。
- [ ] 执行 `.\.venv\Scripts\python.exe -m pytest tests/test_contract_review_amounts.py tests/test_contract_review_checks.py tests/test_contract_review_service.py -k "seq7 or amount" -v`，确认新增用例先 RED。

## Task 2: 更新 A-3 契约

**Files:** `app/capabilities/contract_review/response_formats.py`、`prompts/contract_review.yaml`、`tests/test_contract_review_prompts.py`

- [ ] 在 A-3 顶层 Schema 增加 `contract_overall_evidence: _nullable_string()`，保留旧字段与 `amount_pairs` 名称。
- [ ] Prompt 明确：`amount_pairs[]` 是原文金额事实，可完整或单侧；非空金额侧和 `amount_evidence` 必须原样摘录，禁止计算、补全、生成和反推。
- [ ] Prompt 明确：只有原文表达本合同整体对价时填写 `contract_overall_evidence`；“合同总金额”等同义表达可用，含税报价、比例、合计和数值相等均不能替代。
- [ ] 删除全部 `|`、表格同行、跨单元格、物理行和固定总金额标签示例；改为“有界证据片段内允许普通空白或一次自然换行；跨空段、标题、独立条款或歧义候选不得配对”。
- [ ] 增加字段、单侧、禁止推导、自然折行和不依赖 `|` 的 Prompt/Schema 测试，并运行 `.\.venv\Scripts\python.exe -m pytest tests/test_contract_review_prompts.py -v`。

## Task 3: 证据守卫和有界恢复

**Files:** `app/capabilities/contract_review/amounts.py`、`tests/test_contract_review_amounts.py`、`tests/test_contract_review_service.py`

- [ ] 重构 `sanitize_amount_payment_facts(a3_result, full_text)` 为深拷贝纯函数；数字与大写分别验证，已验证的一侧必须保留。
- [ ] 证据定位只归一化普通空白、一次自然换行和数字千分位；不得改写 `圆/点`、用数学等价验证来源或把百分比当金额。
- [ ] `total_amount_*` 额外要求 `contract_overall_evidence` 可定位、具有整体对价语义且覆盖已出现金额侧；不满足时清空兼容字段，不影响报价或阶段事实。
- [ ] 付款阶段始终保留名称和比例；无效金额侧单独置空。只有比例不产生金额事实。
- [ ] 删除 `_recover_table_row_total_price()`、`_is_markdown_table_data_row()`、`_TOTAL_PRICE_MARKERS` 和所有 `|`/物理行恢复分支。
- [ ] 仅在已验证的 `contract_overall_evidence` 缺完整配对时，从该片段恢复唯一“数字 + 大写关联语义 + 财务大写”；多候选、跨独立文本块或无整体语义一律拒绝，不得扫描全文猜测。
- [ ] 来源键：完整事实由数字和大写唯一位置组成，单侧由已出现一侧位置组成；歧义为 `None`，只保存到 `_amount_source_keys`，不进入 API、Schema 或 B-4。
- [ ] 补自然折行、跨段拒绝、伪造证据、同源别名、同值不同位置、错误大写保留与歧义拒绝测试；运行 `.\.venv\Scripts\python.exe -m pytest tests/test_contract_review_amounts.py tests/test_contract_review_service.py -k "amount or overall or evidence" -v`。

## Task 4: 序号7裁决和文案

**Files:** `app/capabilities/contract_review/checks.py`、`tests/test_contract_review_checks.py`、`tests/test_contract_review_service.py`

- [ ] `check_amount_payment()` 先独立判断整体金额。无明确依据时增加 `FAIL` 原因“合同没有明确总金额”，不附带或杜撰金额内容。
- [ ] `_collect_amount_pairs()` 收集完整和单侧事实，只按唯一来源键合并；不得按标签、金额值、证据包含关系或 reason 去重。兼容字段展示使用“合同总金额”，不得写“合同总价”。
- [ ] 完整不一致：`FAIL`，回显实际、期望和分类；仅数字：`WARN` “{金额名称}没有对应的大写金额”；仅大写：`WARN` “{金额名称}没有对应的数字金额”；仅比例：不产生序号7金额结论。
- [ ] 期望值唯一来源为 `format_rmb_uppercase()`；`点` 为小数书写错误，`圆` 按当前项目临时规则为单位错误，均不得在事实阶段自动改写。
- [ ] 聚合严格为 `FAIL > WARN > PASS`，不改序号8/9、旧序号10或两阶段实现。补齐矩阵、精确文案、同源去重和同值不同位置回归，并运行 `.\.venv\Scripts\python.exe -m pytest tests/test_contract_review_checks.py tests/test_contract_review_service.py -k "seq7 or amount" -v`。

## Task 5: 服务回归与交付

**Files:** `app/capabilities/contract_review/service.py`（仅有必要时）、`tests/test_contract_review_service.py`、当前 change 的 `tasks.md`

- [ ] 确认服务在 A-3 后、`check_amount_payment()` 前调用守卫；B-4 只使用已验证总金额基线，绝不读取私有来源键。
- [ ] 端到端 mock 覆盖：两处报价错误各出现一次、无虚构第三处总金额；仅总金额加比例不推导阶段金额；阶段单侧只提示。
- [ ] 依次执行 `.\.venv\Scripts\python.exe -m pytest tests/test_contract_review_amounts.py tests/test_contract_review_checks.py tests/test_contract_review_prompts.py tests/test_contract_review_service.py -q`、`.\.venv\Scripts\python.exe -m pytest tests/ -q`、`openspec.cmd validate seq7-multi-amount-uppercase-check --strict`、`git diff --check`、`git status --short`。
- [ ] 仅勾选有实际命令输出证明完成的任务。真实端点复测只能由用户执行；Copilot 必须报告其未完成状态、风险和最终 `git status`，不得 commit、push 或 archive。

## 覆盖自检

- 不从含税报价猜总金额：Task 1、3、4、5。
- 总金额同义表达：Task 1、2、3。
- 所有金额对象单侧提示：Task 1、2、3、4。
- 自然折行与跨块拒绝：Task 2、3。
- 删除 `|`/表格行依赖：Task 2、3。
- 同源去重、不同位置保留：Task 3、4。
- `点` 与临时 `圆` 规则：Task 4。
