# 设计：按模型调用语义设置结构化输出预算

## 根因证据

诊断 trace `tmp/llm-trace-audit/20260727-212950-api_v1_contract-review_upload-md-a4bcf345.html` 显示：

- completion_tokens=4817，content_chars=13573，total_tokens=16384，finish_reason=length
- 模型在 B-1 检查技术协议时，将"吉利座舱中心""吉利"等部门/品牌名称误判为甲方称谓
- 每处出现生成一条 WARN 观察，checks 数组无限增长直至触发 LengthFinishReasonError
- reasoning_content 未膨胀，根因是可见 JSON 中 checks 数组无边界

## 为什么统一 maxItems=3 不适用于所有数组

模型调用按语义分为四类：

| 类别 | 调用 | 是否适用 maxItems=3 | 理由 |
|------|------|---------------------|------|
| 审查发现项 | B-1、B-4 | 是 | 只输出问题，无问题为空；每范围最多 3 个不同且最强的问题足够表达审查结论 |
| 有界信息提取 | A-1a header/parties、A-1b、A-3 | 否 | 提取字段由合同结构决定，parties 通常 2-5 个，payment_stages 由合同条款决定 |
| 与输入数量对应的逐项映射 | attachment_title_matching | 否 | 必须为每个 uploaded_id 返回 decision，MATCH 也不能省略 |
| 可能复制大段原文的文本提取 | A-1a sections.content | 不设置固定上限 | 见下方专项分析 |

### A-1a sections.content 专项分析

`sections[].content` 用于提取合同分节正文，下游被 `check_copies_and_attachments` 用于附件内容定位。其长度由合同原文决定，无法从现有业务契约安全推导上限。若设置 maxLength 会导致：
- 截断后的 content 无法匹配附件标题
- 扩大本 change 的业务范围，需要重构提取链路

**决定**：本 change 不修改 sections.content，记录风险供后续评估。

## 为什么审查发现项适合最多 3 条

1. B-1/B-4 的数据流：模型只输出 WARN/FAIL → 无问题返回 `{"checks": []}` → PASS 由服务端在空 checks 时统一生成。
2. 审查结论的有效性不依赖穷举：3 个不同且证据最强的问题足以表达该范围的审查结论。
3. 优先级为 FAIL 高于 WARN；相同问题或相同证据不得重复占用名额。
4. 服务端已有去重逻辑（`_b1_reason_fingerprint`、`seen_reasons`），maxItems=3 是对模型生成阶段的约束，与服务端去重互补。

## 数据流：只输出问题、空列表表示无问题、后端生成 PASS

```
模型生成阶段（Schema + Prompt 约束）
  → 只输出 WARN/FAIL 观察，最多 3 条
  → 无问题返回 {"checks": []}

服务端防御阶段
  → 排序：FAIL 优先于 WARN
  → 去重：相同 reason fingerprint 只保留首条
  → 截取：保留前 3 条
  → 空结果生成 PASS（reason=null）
```

## Schema、Prompt、服务端三层约束分别解决什么问题

| 层 | 解决的问题 | 机制 |
|----|-----------|------|
| Schema | 在模型生成阶段硬约束输出结构 | maxItems=3、result enum=[WARN,FAIL]、maxLength |
| Prompt | 引导模型语义行为 | 最多 3 条、排序规则、去重规则、排除非签约主体 |
| 服务端 | 防御模型未严格执行 Schema | 确定性排序+去重+截取，不依赖集合无序行为 |

三层互补：Schema 和 Prompt 在生成阶段限制，减少无效 token 消耗；服务端防御确保即使模型溢出也不影响最终结果。

## 第 4 个及以后问题被隐藏的风险

- 若一个检查范围确实存在 4+ 个不同真实问题，第 4 个及以后不会出现在最终结果中。
- 缓解：FAIL 优先于 WARN 确保最严重问题不被丢弃；去重确保不同问题不被相同问题挤占。
- 接受理由：审查结论不需要穷举所有问题，3 个最强问题足以触发业务关注和人工复核。

## 提取类和映射类调用为什么采用不同边界

- **提取类**（A-1a、A-3、A-4）：输出数量由合同内容决定，不是"问题列表"。截断会导致下游校验数据不完整。
- **映射类**（attachment_title_matching）：输出数量等于输入 uploaded 数量，是逐项对应关系。省略任何一项（包括 MATCH）都会破坏一对一匹配完整性。
- 这两类调用的 token 风险远低于审查类：提取结果有自然上界（合同结构），映射结果等于输入数量。

## 明确不使用的手段

1. **全局调小 max_tokens**：只会让结果更早截断，误伤正常提取任务，当前无统一全局业务阈值。
2. **样例词黑名单**：不针对"吉利""吉利座舱中心"创建枚举式黑名单或样例特判。B-1 的通用语义规则（部门/品牌/项目团队/产品/系统不是签约方称谓）已覆盖此类场景。

## maxLength 取值依据

| 字段 | maxLength | 依据 |
|------|-----------|------|
| B-1 role | 20 | 角色标签如"甲方""乙方"，不超过 10 字 |
| B-1 baseline_appellation | 100 | 企业法定全称通常 20-50 字 |
| B-1 found_appellation | 100 | 同上 |
| B-1 evidence_quote | 200 | 完整短句，最终 reason 限制 160 字，证据引文需略长 |
| B-4 attachment_evidence | 200 | 同 evidence_quote |
| B-4 reason | 200 | 非金额问题描述，最终会被服务端格式化 |

## 服务端防御的确定性保证

- 排序规则：FAIL 在前，WARN 在后；同级别保持模型输出顺序（稳定排序）。
- 去重规则：使用 `_b1_reason_fingerprint`（B-1）或 reason 文本（B-4）作为指纹。
- 截取：排序+去重后取前 3 条，不使用集合或随机行为。
- 不吞掉结构错误：非 dict 元素仍抛出 ModelFormatError。
- 不把截断/格式异常伪装成 PASS：LengthFinishReasonError 仍由现有 `_raise_if_length_issue` 处理。
