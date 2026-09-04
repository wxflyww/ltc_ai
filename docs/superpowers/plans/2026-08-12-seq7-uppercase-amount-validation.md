# 序号7人民币大写金额确定性校验实施计划

> 对应 OpenSpec change：`seq7-uppercase-amount-validation`。执行时使用测试驱动方式逐项完成；本计划创建时尚未修改业务代码。

**目标：** 修复 MVP 序号7信任模型 `total_amount_match` 导致金额单位和大写书写错误漏检的问题，并为未来二阶段 Evaluate 保留可复用的确定性规则。

**架构：** A-3 继续提取小写金额和大写原文；新增无状态金额工具把 `Decimal` 生成标准人民币中文大写；现有 `check_amount_payment()` 比较生成值与提取值并形成序号7结果。二阶段 Prepare 只保留事实和证据，未来 Evaluate 复用同一工具。

**技术约束：** Python 3.11、标准库 `decimal.Decimal`、pytest；不新增第三方依赖，不改变现有 API 请求/响应，不在本次实现完整二阶段接口。

---

## Task 1：建立金额生成器的失败测试

**文件：**

- 新建：`tests/test_contract_review_amounts.py`
- 后续新建：`app/capabilities/contract_review/amounts.py`

### Step 1：先写标准金额参数化测试

测试公开函数 `format_rmb_uppercase(value) -> str | None`，至少覆盖：

| 输入 | 期望 |
|---:|---|
| `0` | `零元整` |
| `100` | `壹佰元整` |
| `1001` | `壹仟零壹元整` |
| `924528.30` | `玖拾贰万肆仟伍佰贰拾捌元叁角` |
| `1000001.01` | `壹佰万零壹元零壹分` |
| 负数、超过两位小数、非数字文本 | `None` |

### Step 2：运行测试，确认因模块/函数不存在而失败

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_amounts.py -v
```

预期：失败，且失败原因只指向尚未实现的金额工具。

## Task 2：实现最小人民币中文大写生成器

**文件：**

- 新建：`app/capabilities/contract_review/amounts.py`
- 测试：`tests/test_contract_review_amounts.py`

### Step 1：实现输入规范化

- 用 `Decimal(str(value))` 转换输入，捕获 `InvalidOperation`、`ValueError` 和 `TypeError`。
- 仅接受非负且小数位不超过两位的金额；不使用二进制浮点计算角分。
- 把金额拆成整数、角、分三个确定值。

### Step 2：实现整数分组和零位规则

- 数字使用 `零壹贰叁肆伍陆柒捌玖`。
- 个级单位使用 `拾佰仟`，分组单位使用 `万亿`。
- 连续零只输出一个 `零`；分组边界按实际位值补零，不根据具体样例特判。
- 整数部分始终以 `元` 结束；无角分时追加 `整`，有分无角且整数非零时在分前补 `零`。

### Step 3：运行参数化测试直到通过

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_amounts.py -v
```

预期：新增金额工具测试全部通过。

## Task 3：用失败用例锁定序号7漏检

**文件：**

- 修改：`tests/test_contract_review_checks.py`
- 修改：`app/capabilities/contract_review/checks.py`

### Step 1：新增四类序号7测试

- 本次原样例：`924528.30` + `人民币玖拾贰万肆仟伍佰贰拾捌点叁圆` + `total_amount_match=True`，期望 `FAIL/硬阻断`。
- 正确表达：同一小写金额 + `人民币玖拾贰万肆仟伍佰贰拾捌元叁角`，即使模型布尔值缺失也期望 `PASS`。
- 数值不一致：大写缺少 `叁角`，期望 `FAIL` 且原因包含实际值和期望值。
- 单位错误：使用 `圆`，期望 `FAIL`，不得自动替换为 `元`。

### Step 2：运行定点测试，确认现有实现至少在原样例上失败

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_checks.py -k "seq7 or uppercase_amount" -v
```

预期：原样例仍返回 `PASS`，测试失败，证明修复目标可复现。

## Task 4：接入服务端确定性判断

**文件：**

- 修改：`app/capabilities/contract_review/checks.py`
- 测试：`tests/test_contract_review_checks.py`

### Step 1：在 `check_amount_payment()` 中调用金额工具

- 小写或大写缺失时保留现有硬阻断。
- 小写金额无法可靠转换时输出格式无法校验的硬阻断。
- 去除大写字段首尾空白和可选 `人民币` 前缀后，与生成结果精确比较。
- 不读取 `total_amount_match` 决定序号7结果。

### Step 2：生成可复核原因

不一致原因至少包含实际大写金额和服务端期望金额；发现 `圆`、`点` 等字符时说明金额单位或书写形式错误。不得改变序号7的 `id`、名称、结果枚举和阻断等级。

### Step 3：运行金额和检查层测试

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_amounts.py tests/test_contract_review_checks.py -v
```

预期：新增用例及既有金额/付款检查全部通过。

## Task 5：增加旧流水线回归

**文件：**

- 修改：`tests/test_contract_review_service.py`
- 仅在需要验证共享流水线时修改：`tests/test_contract_review_api.py`

### Step 1：增加模型误报场景

在 `run_review_pipeline()` 的模型输出序列中返回本次错误大写和 `total_amount_match=true`，断言最终 checks 中序号7为 `FAIL/硬阻断`。同时保留一个正确大写为 `PASS` 的对照用例。

### Step 2：验证两个入口没有分叉实现

确认 JSON 入口和 multipart 入口仍进入同一个 `run_review_pipeline()`；若现有 API 用例已经覆盖该路由关系，只补断言，不复制金额算法测试。

### Step 3：运行定点流水线测试

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_service.py tests/test_contract_review_api.py -v
```

预期：流水线和两个 API 契约保持通过，错误样例被硬阻断。

## Task 6：完整验证与交付复测

**文件：**

- 更新：`docs/superpowers/_private/2026-08-12-seq7-test-feedback-collection.md`
- 更新：`docs/superpowers/baselines/2026-07-31-contract-review-legacy-baseline.md`

### Step 1：运行全量自动化测试

```powershell
.venv\Scripts\python.exe -m pytest tests/ -v
```

预期：全量测试通过；如存在与本变更无关的既有失败，单独记录并提供定点通过证据，不修改无关代码。

### Step 2：检查变更范围

```powershell
git diff --check
git status --short
```

预期：代码变更只包含金额工具、序号7接入和直接测试；文档只包含本 change、迁移追加记录和测试台账状态。

### Step 3：回写并执行真实复测

自动化验证通过后把台账置为“待复测”，记录命令和结果。使用安育漫原合同通过 MVP 真实端点复测；只有真实结果不再为 `PASS` 且原因可识别“点/圆”问题后，才能把条目标记为“已关闭”。
