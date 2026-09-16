> **实施计划**：`docs/superpowers/plans/2026-09-16-llm-disable-thinking.md`（Task 1–5，TDD 先红后绿）。  
> **次序**：本 change **先做**，`contract-review-mvp-prefill` 依赖它。

## 1. 契约基线与回归保护

- [ ] 1.1 为评审链路写失败测试：一次模型调用中传入的模型对象 `extra_body` 含 `{"chat_template_kwargs": {"enable_thinking": False}}`，确认测试先失败
- [ ] 1.2 为开关写失败测试：`llm.disable_thinking=false` 时，模型调用**不携带** `extra_body`，确认测试先失败
- [ ] 1.3 记录 `mode=review` 的响应基线：顶层键集合、`checks` / `metrics` 条目数与字段，作为改后对照
- [ ] 1.4 核实既有 `tests/test_llm_factory.py` 与本变更无交集（本变更不改 `ChatOpenAI` 构造参数），确认全量测试基线仍为全绿

## 2. 实现：评审链路调用层关思考（仅改 contract_review 自身）

- [ ] 2.1 在 `app/capabilities/contract_review/service.py` 的 `_invoke_json_prompt` 中，`model = get_chat_model()` 之后按开关追加一次绑定：开关为真时 `model = model.bind(extra_body={"chat_template_kwargs": {"enable_thinking": False}})`
- [ ] 2.2 确认该绑定同时覆盖 `service.py:316`（首次调用）与 `service.py:357`（格式错重试）两处 —— 两处共用同一个 `model` 变量，不得只改一处
- [ ] 2.3 确认 `response_format` 与关思考**可同时生效**（实测共存无冲突）：绑定后的对象仍能正常接收 `invoke_model(..., response_format=...)`
- [ ] 2.4 确认 `invoke_model` 的指标标签未受影响：绑定后 `getattr(model, "model_name", "")` 仍返回真实模型名（实测 `Qwen3.6-35B`），`llm_calls_total` / `llm_tokens_total` 标签不退化
- [ ] 2.5 在 `app/core/config.py` 的 `LlmSettings` 新增 `disable_thinking: bool = True`（环境变量 `LTC__LLM__DISABLE_THINKING` 可覆盖）
- [ ] 2.6 在 `config/config.yaml` 与 `config-dev.yaml` / `config-test.yaml` / `config-prod.yaml` 补 `disable_thinking: true`，保持四处一致

## 3. 边界守护（两条红线 + 一条排除）

- [ ] 3.1 **验证 `two_stage/**` 零改动**：本变更不得**新增**任何 `two_stage/**` 条目（对比本变更开始前的 `git status --short app/capabilities/contract_review/two_stage/`；用户自己已存在的未提交改动不属于本变更，须原样保留、不得顺手提交）；`prepare_model.py:369` 的调用形态与本变更前逐字节一致
- [ ] 3.5 **共享单例非污染前置实测（2026-09-16 已完成，实施后须复核）**：`get_chat_model()` 是进程级单例（`llm.py:18,21-25`），本变更在 `service.py:294` 处 `model.bind(...)`。实测证明 `bind()` 返回新对象且**不污染原单例**：
  - `m1 is get_chat_model()` 为 true（单例）；`bound is not m1` 为 true（新对象）
  - bind 前后原单例 `model_kwargs["extra_body"]` **均为 `None`**；连做 3 次 bind 后仍为 `None`
  - 生产时序实测（同进程、不 reset 单例）：two_stage 真实调用路径（`build_prepare_prompt` + `get_prepare_response_format` + `invoke_model`）在 bind 前后两次调用中，**对象 id 相同**、类仍为 `ChatOpenAI`、`extra_body` 仍为 `None`、解析顶层键一致、无 thinking 污染 → 6/6 全通过
  - 证据：`tmp/_probe_ts_isolation.json`、`tmp/_probe_ts_timeline.json`
- [ ] 3.6 **`tests/two_stage/` 回归基线**：本变更前实测 **467 passed / 0 failed**（5.34s）；实施后必须仍为该结果，不得修改 two_stage 测试期望来凑绿
- [ ] 3.7 **不新增跨流程共享开关**：`disable_thinking` 只被 `contract_review` 自身读取，**two_stage 不读该配置**；配置项仅为后端兼容逃生门，不构成"新旧流程隐式开关互相切换"（`two_stage/AGENTS.md:29` 的硬约束）
- [ ] 3.2 **验证 `app/models/llm.py` 零改动**：`git status --short app/models/llm.py` 无输出；`invoke_model` 签名与函数体不变
- [ ] 3.3 加一条守护断言测试：`translate` 的模型调用（`app/capabilities/translate/service.py:53`）**不含**该参数，防止将来被顺手"统一"而改变其行为
- [ ] 3.4 确认 `mode=review` 除"关思考"外**无任何其他改动**：prompt 文件、`response_formats.py`、`schemas.py`、`checks.py`、`amounts.py`、错误码体系在本变更内 `git status` 均无输出

## 4. 验证与交付

- [ ] 4.1 对真实端点 `192.168.16.10:8080` 实测 `mode=review` 关思考前后的耗时与输出（记录 prompt / completion tokens），确认与设计文档 §4.6 的量级一致（预期 48.19s → 42.19s）
- [ ] 4.2 核实关思考后 `mode=review` 响应**结构层面**与 1.3 基线逐字段一致（键集合、类型、语义），仅允许取值层面的非回归差异
- [ ] 4.3 复验 §"已知取值差异"表的可重复性：对 `header.parties[].role` 再各跑若干次，确认关思考后取值收敛、现状侧持续波动（样本量小，结论表述保持保守）
- [ ] 4.4 运行合同评审全量回归与两阶段既有测试，记录命令与结果（预期与基线同为 753 passed / 0 failed）
- [ ] 4.5 执行 `./scripts/change_orchestrator.ps1 -Mode validate -ChangeName llm-disable-thinking` 通过严格校验
- [ ] 4.6 知会 `translate` 责任人：其调用未携带 `response_format`，实测输出 25,782 字符中约 67% 为思考文本（44.08s）；关闭思考后为 11.21s 且输出纯译文。**本变更不代其修改**

## 5. 明确不做（红线清单）

- [ ] 5.1 不动 `app/capabilities/contract_review/two_stage/**`（零改动，不传参、不开关）
- [ ] 5.2 不动 `mode=review` 的除关思考外的任何东西（包括但不限于prompt / 响应模型 / 检查逻辑 / 错误码 / 字段集合）
- [ ] 5.3 不改动 `translate` 能力的任何代码与行为
- [ ] 5.4 不改 `app/models/llm.py`，不在 `get_chat_model()` 上做全局默认
- [ ] 5.5 不改动 `response_format` 结构化输出机制（与关思考分层，互不替代）
- [ ] 5.6 不引入 `max_tokens` 或其它输出长度限制（本变更只处理思考模式）
