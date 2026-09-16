## Why

私有化部署的 `Qwen3.6-35B` **默认开启思考模式**，会在正式答案前先输出一大段英文 `Here's a thinking process: ...`。实测（2026-09-16，`192.168.16.10:8080`）它带来两类问题：

1. **慢**：合同评审链路单次调用由 **7.42s 涨到 40.58s**（输出 1,074 → 6,103 tokens），其中绝大部分是思考文本。
2. **可能静默出错**：思考文本里会写出**结构草稿**。一旦结构化输出（`response_format`）未生效，`parse_json_object` → `_extract_json_object`（`app/capabilities/contract_review/prompts.py:38`）会**从头扫描并命中思考里的草稿 JSON**，返回一个能解析、但结构错误的答案，**不抛任何异常**。

当前模型调用不传任何思考开关，行为完全由后端默认值决定 —— 即"默认开思考"。

## 范围与红线（用户明确定，2026-09-16）

本变更**只做一件事：关掉合同评审链路的思考模式**，并遵守三条边界：

1. **`two_stage/**` 零改动（红线）** —— 两阶段正在并行精雕，不得引入任何不可控变量。两阶段的模型调用**既不传参、也不受本变更影响**。
2. **`mode=review` 只关思考，其他一律不碰（红线）** —— 不改 prompt、不改响应模型、不改错误码、不改评审逻辑、不改响应字段集合与类型。
3. **`translate` 零改动** —— 该能力由其他同事负责，其调用形态与行为逐项不变（另：其"输出混入思考文本"的既存缺陷单独知会责任人，不在本变更内处理）。

## What Changes

- `app/capabilities/contract_review/service.py` 的 `_invoke_json_prompt` 中，取到模型后按开关做一次绑定：
  `model = model.bind(extra_body={"chat_template_kwargs": {"enable_thinking": False}})`
  —— 该函数是评审链路全部模型调用的**唯一入口**（`service.py:316` 首次调用与 `:357` 格式错重试共用同一个 `model` 变量），**一处接线即覆盖 `mode=review` 与 `mode=prefill` 两条链路**。
- `app/core/config.py` 的 `LlmSettings` 新增 `disable_thinking: bool = True`，环境变量 `LTC__LLM__DISABLE_THINKING` 可覆盖。
- `config/config.yaml` 与 `config-dev.yaml` / `config-test.yaml` / `config-prod.yaml` 同步该默认值。
- **`app/models/llm.py` 零改动** —— 实测 `model.bind(...)` 返回的 `_ChatModelBinding` 会透传底层模型属性，`invoke_model` 内的指标标签仍为真实模型名（`Qwen3.6-35B`，已实测），且与 `response_format` 共存无冲突。故无需为该开关修改通用模型适配层，**共享文件不被触碰**。
- 不改动 `response_format`（结构化输出）机制：它与关思考**各管一层**（前者约束格式、后者保证输出确定性），互不替代。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `contract-review`：组织评审链路与预填链路的模型调用改为关闭思考模式，输出确定性改善、响应时间下降；**响应结构、字段集合、字段类型、错误码与既有行为不变**。

## Impact

- **API**：**无调用方可见变化** —— 响应壳、字段集合、字段类型、错误码全部不变。对 `mode=review` 的影响是"同样的结构、更快的响应、更稳定的取值"。
- **代码（仅 2 个文件，均属 contract_review 自身与其配置）**：
  - `app/capabilities/contract_review/service.py`：新增 2 行（读开关 + bind）。
  - `app/core/config.py`：`LlmSettings` 新增 1 个字段。
- **配置**：新增 `llm.disable_thinking`（环境变量 `LTC__LLM__DISABLE_THINKING`），默认 `true`；`config/config.yaml` 与 `config-dev` / `config-test` / `config-prod` 同步。该开关是**逃生门**：`chat_template_kwargs` 属 vLLM / Qwen 特有参数，切换或不支持它的后端时置 `false` 即一键退回现状。
- **测试**：新增断言"评审链路的模型调用确实携带 `chat_template_kwargs.enable_thinking=false`"、"开关置 `false` 时不携带"；并保留一条守护断言"`translate` 的调用形态不含该参数"。既有 `tests/test_llm_factory.py` 只断言存在的键、不检查多余键，且本变更不改构造参数，不受影响。
- **已知取值差异（非回归 · 已实测量化）**：关思考会改变模型输出分布，实测 `mode=review` 的 `header.parties[].role` 存在差异 ——

  | | 第 1 次 | 第 2 次 | 第 3 次 |
  |---|---|---|---|
  | 现状（不关思考） | 甲方 / 乙方 | 招标人（甲方）/ 供应商（乙方） | 招标人（甲方）/ 供应商（乙方） |
  | 关思考 | 甲方 / 乙方 | 甲方 / 乙方 | 甲方 / 乙方 |

  **结论：该字段的波动在现状下本就存在（`temperature=0.3`），关思考后收敛到 prompt few-shot 约定的写法**（`prompts/contract_review.yaml:23` 的示例正是 `"role": "甲方"`）。同期对照 `sections` 数量三次均为 `16`，顶层键集合完全一致。故属"更稳定且更贴合 prompt 约定"，不构成契约回归。
- **不做**：不改动 `translate` 能力的任何代码与行为；不改动 `two_stage/**`（既不传参也不开关）；不改 `app/models/llm.py`；不在 `get_chat_model()` 上做全局默认；不修改任何 prompt、响应模型与错误码体系；不引入 `max_tokens` 或其它输出长度限制。
