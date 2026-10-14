# LTC 合同评审 AI 能力 · 产品需求文档（PRD）

| 项目 | 内容 |
|---|---|
| 文档版本 | V1.0 |
| 撰写人 | AI 主理人（基于代码与交付文档整理） |
| 状态 | 评审草稿 |
| 更新日期 | 2026-10-09 |
| 适用范围 | `contract_review` 能力（单阶段评审 `mode=review` + 智能预填 `mode=prefill`），即 LTC AI 能力服务中已上线的合同评审/预填产品线 |
| 上游 PRD | `docs/LTC-AI能力服务-PRD.md`（AI 能力服务总体 PRD V1.0） |

> **文档定位**：本文档是 `contract_review` 能力的独立 PRD，聚焦于「合同组织评审」与「D-02/D-03 字段智能预填」两条已上线产品线的完整需求、契约、验收与演进。文本翻译（`translate`）为兄弟能力，仅在第 2 章边界中列出；「评审智能总结」（`review-summary`）为在途独立能力，与本文档零依赖，不纳入本期范围（见第 12 章）。

---

## 修订历史

| 版本 | 日期 | 说明 |
|---|---|---|
| V1.0 | 2026-10-09 | 初稿，基于现有代码实现、OpenSpec 规格、交付架构文档与项目基线简报整理，对齐已上线事实 |

---

## 1. 背景与目标

### 1.1 业务背景

LTC（Lead to Cash）系统的合同审批流程中，存在两类高频、重复、依赖人工的环节：

1. **合同组织评审**：人工逐条核对合同首页完整性、签章页与预设值一致性、金额大小写、付款阶段、附件一致性等，工作量大且易漏判关键风险。
2. **合同结构化填报（D-02 / D-03）**：合同系统录入环节需从合同正文中手工抽取数十个结构化字段，重复劳动显著。

随着私有化大模型基础设施（Qwen3.6-35B-A3B，vLLM 部署）落地，上述环节可统一由 AI 能力服务以标准 API 形式支撑，降低人工成本、提升一致性与可追溯性。

### 1.2 产品目标

为 LTC 系统提供**稳定、可解释、可追溯**的合同评审与字段预填能力：

- **评审（`mode=review`）**：对合同正文及附件进行自动检查，输出硬阻断项（FAIL/硬阻断）与提示项（WARN/提示），供评审人修订条款。
- **预填（`mode=prefill`）**：从合同正文中抽取 D-02（19 字段）/ D-03（9 字段）结构化字段，原文原样返回，供填报人核对后回写，减少手工抽取。

### 1.3 非目标（本期明确不做）

- 不改动 `two_stage/**`（两阶段升级隔离面）；两阶段 Prepare/Evaluate 尚未接入 serving，本期 PRD 仅将其列为演进方向，不纳入产品承诺。
- 不新增 / 改名 / 改口径 / 服务端计算任何预填字段（「固定口径」见第 7 章）。
- 不涉及合同系统前端界面改造，仅提供后端 AI 能力 API。
- 不涉及大模型训练/微调，仅作为私有化 vLLM 服务的调用方。
- 不负责合同文件、上下文、结果与业务流程的持久化（无业务状态，见第 10 章）。

---

## 2. 产品范围与边界

### 2.1 范围内（已上线）

| 能力 | 入口 | 说明 |
|---|---|---|
| 单阶段合同评审 | `POST /api/v1/contract-review`、`POST /api/v1/contract-review/upload-md` | `mode=review`，JSON 与 multipart 两入口等价 |
| 智能预填 D-02 | 同上，`mode=prefill` + `prefill_scope=d02` | 19 字段抽取（合同信息 + 合同计划 + 财务信息共用） |
| 智能预填 D-03 | 同上，`mode=prefill` + `prefill_scope=d03` | 9 字段抽取（财务信息 + 履约保证金/保函） |
| 统一底座 | 全部入口 | API Key 鉴权、统一错误码、traceId 留痕、可观测指标 |

### 2.2 范围外（兄弟能力 / 演进能力）

| 能力 | 关系 | 说明 |
|---|---|---|
| 文本翻译 `translate` | 兄弟能力 | `POST /api/v1/translate`，P1，与评审/预填共用同一 vLLM 实例 |
| 评审智能总结 `review-summary` | 在途独立能力 | `POST /api/v1/review-summary`（立项 2026-10），独立能力包、零依赖，不在本 PRD 范围内 |
| 两阶段升级（Prepare/Evaluate） | 演进方向 | `app/capabilities/contract_review/two_stage/`，未接 serving，受冻结不变量约束 |

### 2.3 两条产品红线（不可绕过的约束）

1. **不碰 `two_stage/**`**：两阶段升级是隔离面，唯一真共享为 `get_chat_model()` 单例。
2. **`mode=review` 只关思考**：prompt / 响应模型 / 检查逻辑 / 错误码 / 字段集合一律**冻结不动**（仅允许通过 `model.bind(extra_body={"chat_template_kwargs": {"enable_thinking": False}})` 关闭模型思考以保证 JSON 稳定解析）。任何对评审口径的修改都被视为破坏性变更，须走独立变更评审。

---

## 3. 用户角色与场景

### 3.1 角色清单

| 角色 | 业务身份 | 主要操作 | 核心关注点 |
|---|---|---|---|
| 甲方决策者 | LTC 系统负责人 / 财务中台总监 | 能力上线节奏把控、ROI 评估、合规把关 | 评审准确率与合规可控，上线不破坏现有红线 |
| 填报人（最终用户 A） | D-02 / D-03 填报人（合同系统侧） | 调用 prefill 获取字段预填 | 预填覆盖率与准确率，是否减少手工填报 |
| 评审人（最终用户 B） | 合同评审人 | 调用 review 获取条款评审结论 | 结论可解释、耗时可控、不漏关键风险 |
| 合规 / 运维（受影响方） | 合规审计 / SRE | 审计留痕、可用性监控、超时感知 | 全链路 traceId 留痕、可用性、超时可被正确感知 |
| 合同签约方（受影响方） | 客户 / 相对方 | 接收受评审结论影响的条款与签署地 | 评审结果正确、签署地预设值准确 |

### 3.2 关键场景清单

| 编号 | 角色 | 触发条件 | 期望结果 | 频率 / 时延基线 |
|---|---|---|---|---|
| S1 | 评审人 | 提交 `mode=review` | 约 50s 内返回 `code=0` 结构化评审结论 + traceId | 中频，review≈50s |
| S2 | 填报人 | 提交 `mode=prefill, scope=d02` | 约 7–17s 返回 19 字段预填（原文原样） | 高频，d02≈7–17s |
| S3 | 填报人 | 提交 `mode=prefill, scope=d03` | 约 3s 返回 9 字段预填（原文原样） | 高频，d03≈3s |
| S4 | 填报人 / 评审人 | 通过 upload-md（multipart，`contract_file`）上传 | 等价于 JSON 入口的评审 / 预填结果 | 中频（大合同/附件场景） |
| S5 | 评审人 / 填报人 | 提交 `translate` | 返回译文（`code=0`） | 低频（辅助能力） |

---

## 4. 功能需求总览

> 对齐《高层架构设计》§6.3 功能清单（F1–F12）。P0 功能全部为已上线既有能力（MVP = 线上）；F9–F12 为完整版增强项，不阻断 MVP。

| 一级模块 | 功能项 | 编号 | 优先级 | MVP | 完整版 | 备注 |
|---|---|---|---|---|---|---|
| 合同评审 | 单阶段合同评审（mode=review） | F1 | P0 | ✅ | ✅ | 已上线；受红线二冻结 |
| 预填 | D-02 字段预填 | F2 | P0 | ✅ | ✅ | mode=prefill, scope=d02 |
| 预填 | D-03 字段预填 | F3 | P0 | ✅ | ✅ | mode=prefill, scope=d03 |
| 接入 | 合同上传与 Markdown 解析（upload-md） | F4 | P0 | ✅ | ✅ | 表单字段名必须为 `contract_file` |
| 预填 | 26 字段固定口径 | F6 | P0 | ✅ | ✅ | 不新增/改名/改口径/计算 |
| 底座 | 统一错误码 + traceId 留痕 | F7 | P1 | ✅ | ✅ | 0/1xxxx/2xxxx；响应含 traceId |
| 接入 | API Key 鉴权 | F8 | P0 | ✅ | ✅ | `/health`、`/metrics` 放行 |
| 运营 | 评审量/时延/超时率看板与告警 | F9 | P2 | ❌ | ✅ | 完整版 |
| 底座 | 应用侧并发闸门 | F10 | P2 | ❌ | ✅ | 防批量预填拖慢评审 |
| 底座 | 超时错误码修复（20002/504） | F11 | P1 | ❌ | ✅ | 修复 29999 静默失效 |
| 底座 | 消除隐藏重试与本地/容器漂移 | F12 | P2 | ❌ | ✅ | 对齐依赖版本 |

---

## 5. 核心功能详述

### 5.1 单阶段合同评审（mode=review）—— F1

**业务场景**：评审人在合同系统中发起对一份合同的条款评审。系统在关闭模型思考的前提下调用 vLLM 生成结论，并必调签署地预设值服务获取签署地信息，输出结构化结论（风险点、条款建议、依据）。

**业务流程（时序）**：
1. `AuthMiddleware` 校验 API Key（放行 `/health`、`/metrics`）；`TraceIdMiddleware` 生成/透传 `traceId` 并计时。
2. 路由 `_dispatch()` 按 `mode=review` 分发到评审能力包。
3. 评审能力组装 prompt（**冻结**），调用 vLLM：`model.bind(extra_body={"chat_template_kwargs": {"enable_thinking": False}})` 关闭思考。
4. 评审能力**同步必调**签署地预设值服务（`signing_preset.base_url`）获取签署地信息——这是 review 的**强依赖**。
5. 组装结构化评审结论，回写合同系统。
6. 响应注入 `traceId` + `duration_seconds`，统一错误码封装。

**验收标准（AC）**：
- **正常**：Given 鉴权通过且下游正常，When 提交 `mode=review`，Then 约 50s 内返回 `code=0` 评审结论并附 `traceId` 与 `duration_seconds`。
- **非法 mode**：Given 鉴权通过，When `mode` 不在 `{review, prefill}`，Then 返回 HTTP 422 + `code=10001`。
- **鉴权失败**：Given 缺/错 API Key，When 提交，Then 返回 `code=10002`（`/health`、`/metrics` 不被拦截）。
- **签署地服务不可用**：Given `mock-preset-server` 停服，When 提交 `mode=review`，Then review 链路返回服务端错误（强依赖缺失）；**prefill 不受影响**。
- **模型超时（已知待修复）**：Given vLLM 超时，When review 进行中，Then 设计应返回 `code=20002`/HTTP 504；**当前实际返回 `code=29999`/HTTP 500（F11 待修复）**，评审结果页须标注「已知待修复」，不向用户隐瞒。

### 5.2 智能预填 D-02 / D-03（mode=prefill）—— F2 / F3 / F6

**业务场景**：填报人在合同系统发起字段预填，减少从合同正文手工抽取字段的重复劳动。系统仅读取「正文里」的内容（`contract_md` + `prefill_scope`），直送全文不切分，按 `scope` 返回抽取结果，**原文原样**呈现，供填报人核对后一键回写。

**业务流程（时序）**：
1. 鉴权 + `traceId` 注入。
2. `_dispatch()` 按 `mode=prefill` 分发到预填能力包。
3. 预填**只读取** `contract_md` + `prefill_scope`，直送全文（不切分）；内嵌正文的附件视同正文参与，**单独上传的** `attachments`/`attachment_files` 不参与（与 review 三份合一不同）。
4. 调用 vLLM（关闭思考）抽取字段，按 `SCOPE_GROUPS` 过滤：`d02` = contract_info + contract_plan + finance_info；`d03` = finance_info + guarantee。
5. 按固定口径规整（原文原样，仅明列例外归一），回写合同系统。
6. 响应注入 `traceId` + `duration_seconds`。
   - **注：prefill 不调用 `mock-preset-server`**（与 review 的关键差异）。

**验收标准（AC）**：
- **D-03 正常**：Given 鉴权通过，When `scope=d03`，Then 约 3s 内返回 9 字段预填且 `code=0`、字段原文原样。
- **D-02 正常**：Given 鉴权通过，When `scope=d02`，Then 约 7–17s 内返回 19 字段预填且 `code=0`。
- **all 正常**：Given 鉴权通过，When `scope=all`，Then 返回去重后 26 字段预填。
- **非法 scope**：Given 鉴权通过，When `scope` 缺失或非法，Then 返回 `code=10001`。
- **口径 - 原文原样**：Given 含金额（`¥1,000,000`）、比例（`50`）、日期（`2026/06/17`）的合同，When 预填，Then 金额保留符号与千分位、比例返回 `"50%"`、日期不归一，仅 `currency`/`milestone_*` 明列例外可归一。
- **附件隔离**：Given 单独上传 `attachments`/`attachment_files`，When 预填，Then 这些附件不参与字段抽取（仅内嵌正文附件参与）。

### 5.3 Markdown 上传入口（upload-md，multipart）—— F4

**业务场景**：用户通过 multipart 表单上传 Markdown 合同（字段名必须为 `contract_file`），指定 `mode` 与可选 `prefill_scope`、`attachment_files`，发起评审或预填。该入口与 JSON 入口**共用** `_dispatch()`，能力等价。

**验收标准（AC）**：
- **评审上传**：Given `multipart/form-data` 且字段名为 `contract_file`，When `mode=review`，Then 返回与 JSON review 等价的结论（`code=0`）。
- **预填上传**：Given 含 `prefill_scope` 的 multipart 上传，When `mode=prefill`，Then 返回与 JSON prefill 等价的结果。
- **字段名错误**：Given 表单字段名为 `file` 而非 `contract_file`，When 提交，Then 参数校验失败（`code=10001`/422）。
- **非法 mode**：Given 上传表单 `mode` 不在 `{review, prefill}`，When 提交，Then HTTP 422 + `code=10001`。

### 5.4 文本翻译（translate）—— 兄弟能力（F5）

`POST /api/v1/translate`：提交源文本，返回译文（`code=0`）。复用统一鉴权/响应壳，与评审/预填共用同一 vLLM 实例（注意无并发闸门时批量预填会拖慢翻译/评审，见 F10）。非本 PRD 核心，仅作边界说明。

---

## 6. 接口契约（API Contract）

### 6.1 统一响应壳

所有接口返回统一结构（由 `ApiResponse` 封装）：

```json
{
  "code": 0,
  "message": "success",
  "data": { },
  "traceId": "uuid-or-empty",
  "duration_seconds": 12.345
}
```

- 成功 `code=0`；客户端错误 `1xxxx`；服务端错误 `2xxxx`。
- 所有响应含 `traceId` + `duration_seconds`（由 `TraceIdMiddleware` 注入）。

### 6.2 统一错误码

| 错误码 | HTTP | 含义 | 触发场景 |
|---|---|---|---|
| 0 | 200 | 成功 | 正常返回 |
| 10001 | 422 | 参数校验失败 | `mode`/`prefill_scope` 非法、表单字段名错误、必填缺失 |
| 10002 | 401 | 鉴权失败 | 缺/错 API Key（`/health`、`/metrics` 除外） |
| 20001 | 5xx | 模型调用重试耗尽 | vLLM 持续失败 |
| 20002 | 504 | 超时（**设计值，当前实际为 29999，F11 待修复**） | vLLM 超时 |
| 20003 | 5xx | 格式异常 | 模型输出无法解析/结构不符 |
| 29999 | 500 | 未知（**当前超时的实际落地值，待修复**） | 异常穿透全局 handler |

### 6.3 接口清单

| 方法 | 路径 | 鉴权 | 入参形态 | 说明 |
|---|---|---|---|---|
| POST | `/api/v1/contract-review` | 是 | JSON body | `mode` ∈ {review, prefill}；`prefill_scope` ∈ {all, d02, d03} |
| POST | `/api/v1/contract-review/upload-md` | 是 | multipart | 表单字段：`contract_file`(必填)、`attachment_files`(可选)、`mode`(表单, 默认 review)、`prefill_scope`(表单, 默认 all) |
| GET | `/health` | 否 | — | 存活探针 |
| GET | `/metrics` | 否 | — | Prometheus 指标 |

### 6.4 请求 Schema（JSON 入口 `contract-review`）

```json
{
  "contract_md": "合同正文 Markdown（必填，非空）",
  "attachments": [
    { "index": 1, "filename": "附件1.md", "file_type": "md", "text": "附件正文" }
  ],
  "mode": "review | prefill",
  "prefill_scope": "all | d02 | d03"
}
```

- `mode` 缺省 `review`；`prefill_scope` 缺省 `all`。
- `mode` 非法 → 422 + 10001。

### 6.5 响应 Schema —— 评审（mode=review）

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "overall_result": "PASS | BLOCK",
    "check_time": "2026-10-09T13:02:48",
    "checks": [
      {
        "id": "序号1",
        "name": "合同首页完整性",
        "result": "PASS | WARN | FAIL | NA",
        "block_level": "通过 | 提示 | 硬阻断 | 不适用",
        "reason": "问题说明或 null"
      }
    ],
    "metrics": [
      { "id": "A-1a", "name": "合同首页/签约方提取", "duration_seconds": 3.1,
        "token_usage": { "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0 },
        "segments": [] }
    ]
  },
  "traceId": "...",
  "duration_seconds": 50.2
}
```

- `overall_result = BLOCK` 当且仅当存在 `result=FAIL 且 block_level=硬阻断` 的检查项。
- `metrics` 输出各模型调用步骤的耗时与 token 消耗（步骤级 + B-1 分段汇总）。

### 6.6 响应 Schema —— 预填（mode=prefill）

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "mode": "prefill",
    "prefill_status": "ok | failed",
    "prefill": {
      "contract_info": { },
      "contract_plan": [ { } ],
      "finance_info": { },
      "guarantee": [ { } ]
    }
  },
  "traceId": "...",
  "duration_seconds": 8.5
}
```

- 四组结构**固定键**，未请求/未抽到的组按「未取到」表达（`contract_info`/`finance_info` 为空对象、`contract_plan`/`guarantee` 为空数组），**不省略键** → 调用方**不能凭键存在判 scope**。
- 响应**不含** `overall_result` / `check_time` / `checks` / `metrics`（与评审零耦合）。

---

## 7. 数据模型与字段口径（预填 26 字段）—— F6

### 7.1 总览

预填字段集合共 **26 字段**（D-02 19 项 + D-03 9 项，去重后 `finance_info` 由 D-02/D-03 共用）。分组如下：

| 组 | 所属 scope | 字段数 | 是否附 evidence |
|---|---|---|---|
| `contract_info`（合同信息） | d02 | 9 | 否 |
| `contract_plan`（合同计划，数组，每项） | d02 | 8（含 1 个 int） | 是（每行固定 3 条） |
| `finance_info`（财务信息） | d02/d03 共用 | 2 | 否 |
| `guarantee`（履约保证金/保函，数组，每项） | d03 | 7 | 是 |

### 7.2 字段明细（按代码 schema 实列）

**`contract_info`（D-02 合同信息，9 字段，全部原文摘录字符串）**：`payment_terms`、`payment_method`、`service_content`、`service_valid_months`、`service_sla`、`service_start_date`、`service_end_date`、`onsite_service_count`、`inspection_count`。

**`contract_plan`（D-02 合同计划，数组，每项 8 字段）**：`milestone_name`、`milestone_code`、`milestone_text`、`milestone_seq`(int)、`plan_finish_date`、`plan_payment_date`、`payment_amount`、`evidence[]`（行级、按出处）。

**`finance_info`（D-02/D-03 共用，2 字段）**：`contract_amount`、`currency`。

**`guarantee`（D-03 履约保证金/保函，数组，每项 7 字段）**：`type`、`amount`、`payee`、`bank_name`、`bank_account`、`return_clause`、`evidence[]`。🔴 `type` **实际只输出** `履约保函` / `履约保证金` **两种**（2026-10-14 定案）；schema 枚举另声明 `预付款保函` / `投标保函` / `质量保函` / `质保保函` / `支付保函` 5 值，**仅作负向参考**（命中其一即排除该条），**不会出现在响应里**。

### 7.3 固定口径（铁律，服务端零加工）

- **除 `milestone_seq`（int）外，业务字段一律字符串、原文原样**：不做数字换算、不剥货币符号（¥/￥/$/€/£）、不去千分位、不做日期归一。原因：任何本机类型转换都是加工误差来源（如 `float` 把 `13` 序列化成 `13.0`）。展示类型由合同系统自行定夺。
- **例外清单（穷尽，仅在 prompt 层 / 字段级规则实现，服务端不后处理）**：
  1. 三个金额字段（`contract_plan[].payment_amount`、`finance_info.contract_amount`、`guarantee[].amount`）剥货币符号词 + 千分位 `,` + 首尾空白；**保留** `%`/小数点/量级「万/亿」；**禁止换算**；同处中阿并存取阿拉伯。
  2. `currency` → 归一 ISO 4217 三位大写代码（人民币→CNY、美元→USD、日元→JPY、欧元→EUR），**不是恒等于 CNY**（随合同变化）。
  3. `milestone_name`/`milestone_code` → 13 名标准清单映射（如 `begin`/`finalaccept`/`end`）。
- **`service_start_date`/`service_end_date` 口径**：由模型从合同名称判定是否服务类合同；🔴 **两字段各自独立取值**（2026-10-13 修订：原「非服务类须成对」**已废止**）；服务条款给期限时按**绝对日期个数**分流（2 个、构成区间 → 起点/终点各归其位；1 个 → 按**语义方向**归位，**指向不明则都 `null`**，宁可空、不要错位）；「事件起算+期限」→ `null`（**只作用于这两个时间字段**，不影响 `service_valid_months` 等期限字段，「之日起两年」→ `service_valid_months=两年`）。
- **evidence**：行级、按出处；某出处原文确实不存在时为 `{"section": null, "quote": "无"}` —— 「无」按**出处**理解，调用方须用**全等**判定，否则「无违约条款」会被误判为缺失。
- **不新增字段 / 不改名 / 不改口径 / 服务端不计算**。

### 7.4 预填输入边界

- 预填**只吃正文里的内容**：只读 `contract_md` + `prefill_scope`，直送全文不切分。
- **内嵌正文的附件**视同正文参与；**单独上传的** `attachments`/`attachment_files` **不参与**（review 则三份合一）。

---

## 8. 评审检查点清单（Checkpoint Catalog）—— F1

评审输出一组检查项，每项含 `id` / `name` / `result`(PASS|WARN|FAIL|NA) / `block_level`(通过|提示|硬阻断|不适用) / `reason`。检查点目录如下（逻辑取自 `checks.py` 与 OpenSpec 规格）：

| 编号 | 名称 | 阻断级别 | 核心校验逻辑 |
|---|---|---|---|
| 序号1 | 合同首页完整性 | 硬阻断/提示 | 合同名称缺失(FAIL)、合同编号缺失(WARN)、签订地点/日期缺失(WARN)、我方签署主体名称 vs 预设值不一致(FAIL)、首部签约方缺失(FAIL) |
| 序号2 | 签章页完整性 | 硬阻断/提示 | 首部与签章区块同名角色名称一致性；九项字段（法定代表人/开户银行/账号/账户名称/地址/电话/传真/网址/邮编）缺失(WARN)或与非空预设值不一致(FAIL) |
| 序号3 | 我方签署日期 | 硬阻断 | 签章区块我方签署日期早于首部签订日期、或早于当前系统日期(FAIL)；我方日期缺失则 PASS（跳过） |
| 序号11 | 账户信息 | 硬阻断/提示 | 开户银行/账号/账户名称 vs 预设值一致性 |
| 序号7 | 总价大小写一致性 | 硬阻断/提示 | 小写金额与大写金额一致性；合同无明确总金额(FAIL)；无对应大写/小写(WARN)；单位错误「圆」、小数用「点」(FAIL) |
| 序号8 | 货币条款 | 硬阻断 | 币种缺失(FAIL) |
| 序号9 | 付款方式 | 硬阻断 | 付款方式缺失(FAIL) |
| 序号10 | 付款阶段校验 | 硬阻断/提示 | 付款阶段比例合计≠100%(FAIL)、阶段金额合计≠合同总价(FAIL)、阶段不明确(WARN) |
| B-1 | 称谓一致性 | 提示 | 以首部甲乙方定义及明确简称为基准，检查正文与附件中各签约方称谓是否一致（按正文+每个附件分段检查，最多各 3 条，FAIL 优先）；合同/项目名称、部门/品牌/项目团队等不触发；噪声与重复告警过滤 |
| B-4 | 附件内容一致性 | 硬阻断 | 附件内容与合同正文关键信息（尤其总价）一致性；金额基准须为 A-3 从正文提取且经服务端验证的数值+原文 |
| 附件数量/标题一致性 | 声明附件 vs 实际上传附件 | 提示/硬阻断 | 声明数量多于上传(FAIL)；规范化后标题唯一一致则关联；语义模型一对一 MATCH 则关联，UNCERTAIN/MISMATCH 不关联并提示 |

**提取步骤（非检查项，产出数据供上述检查使用）**：A-1a（首页/签约方/章节提取）、A-1b（我方签章区块提取）、A-3（金额与付款条款提取）、A-4（合同份数/附件声明提取）、附件标题语义匹配。模型调用均使用 JSON Schema `response_format`（strict），缺顶层字段时重试一次，仍不符返回 `20003`。

---

## 9. 非功能需求

### 9.1 性能与响应

- 时延基线（跨天不可比，共享 GPU 漂移）：review≈50s、d02≈7–17s、d03≈3s。
- 模型调用封装返回 `(content, token_usage)`；解析失败重试 1 次（业务层）。
- 模型默认开思考 → 必须关闭思考（`enable_thinking=False`）以保证 JSON 稳定解析；否则会静默返回错误结构不报错（已实锤）。

### 9.2 安全

- 服务间调用鉴权：API Key 白名单（`LTC__AUTH__API_KEYS`），`AuthMiddleware` 校验；`/health`、`/metrics` 放行。
- 密钥/凭证通过环境变量或密钥管理服务注入，**不进入代码库**。
- 签署地预设值来自内部 `mock-preset-server`（review 强依赖）。

### 9.3 可观测性

- 结构化日志（JSON）含 traceId、接口耗时、模型调用耗时。
- Prometheus 指标（`/metrics`）：QPS、错误率、模型调用延迟、Token 消耗。
- 评审响应 `data.metrics` 输出步骤级耗时与 token（含 B-1 分段汇总）。
- LLM 审计事件记录调用异常并标注长度问题类型（input/output）。

### 9.4 部署与多环境

- 容器化：`docker` → 测试服务器 `192.168.9.67:8001`（容器 `ltc-ai-test`，`8001:8000`）。
- 多环境配置：`dev`/`test`/`prod`（`config-{LTC_ENV}.yaml`），优先级：环境变量 > 环境配置 > 默认配置。
- 注意：`docker restart` 是静默空转，更新代码必须 `docker rm -f` + `docker run` 重建（容器创建时钉死镜像 ID）。

### 9.5 并发与资源（F10，完整版）

- 预填与评审**共用同一 vLLM 实例**，应用侧当前**无并发闸门**；并发 16 时 p50 已达 26s，批量预填会拖慢评审/翻译。
- F10 目标：引入应用侧并发闸门，保护评审时延 SLA，避免批量预填挤占 GPU。

---

## 10. 架构与依赖

### 10.1 分层结构

```
API 层 (FastAPI Router + Pydantic)
  → 能力层 (app/capabilities/contract_review/)   # 组装 prompt、重试、预填/评审分发
    → 模型适配层 (app/models/llm.py)            # LangChain ChatModel 工厂（get_chat_model() 单例）
      → 基础设施层 (app/core/)                  # 配置/日志/错误/中间件
```

- 新增能力只需在 `app/capabilities/` 下新建独立包并在 `main.py` 注册路由（能力间零依赖）。
- `contract-review` 与 `translate`/`review-summary` 零依赖；与 `two_stage/**` 唯一共享为 `get_chat_model()` 单例。

### 10.2 外部依赖

| 依赖 | 作用 | 关键约束 |
|---|---|---|
| 私有化 vLLM（Qwen3.6-35B） | 模型推理 | `192.168.16.10:8080/v1`，须带 Bearer Key，须关闭思考；timeout dev/test=300、prod=30（prod 未覆盖→击穿） |
| 签署地预设值服务（mock-preset-server） | review 强依赖 | 仅 review 调用；prefill 不碰；停服→review 挂、prefill 不挂 |
| LTC 系统（Java/Spring Boot） | 主要调用方 | HTTP/REST JSON；负责文件/上下文/结果持久化 |

### 10.3 无状态约束

本项目保持**无业务状态**：调用方负责合同文件、上下文、结果、跨版本关联与业务流程的持久化。新旧流程不得共享请求状态、混合检查结果或通过隐式开关互相切换。

---

## 11. 已知问题与技术债

| 编号 | 问题 | 影响 | 状态 |
|---|---|---|---|
| F11 | 超时错误码失效：超时抛 `OpenAITimeoutError`（非内置 `TimeoutError`）→ 捕不到 → 落全局 handler → 实际返 `29999`/500（设计应为 `20002`/504） | 模型超时客户端永远拿不到 20002 | 已写未部署（`llm.py` 加 `max_retries=0` + `except (TimeoutError, APITimeoutError)`） |
| F12 | OpenAI SDK 隐藏重试 + 本地/容器依赖不一致 | 读超时被静默重试 2 次（最坏 3 请求/15min）；本地绿≠容器绿（`OpenAITimeoutError` 仅容器版存在） | 待治理，对齐依赖版本 |
| 红线风险 | `mode=review` 口径冻结，任何改动须独立变更评审 | 避免破坏评审一致性 | 受控 |

---

## 12. 演进路线

| 方向 | 状态 | 与本期关系 |
|---|---|---|
| 两阶段升级（Prepare 出事实 / Evaluate 出裁决） | 代码就绪，未接 serving | 冻结不变量：`ReviewContext` 不可变；`Prepare` 仅输出 Draft 不判 PASS/WARN/FAIL；新旧流程隔离。本期 PRD 不纳入产品承诺 |
| 评审智能总结 `review-summary` | 在途立项（2026-10） | 独立能力包、零依赖、错误码零新增；与 `contract_review` 并列，不在本 PRD 范围 |
| F9 看板与告警 / F10 并发闸门 / F11 超时修复 / F12 依赖对齐 | 完整版增强 | 不阻断 MVP，按需排期 |

---

## 13. 度量指标与验收基线

- **准确性**：评审检查点命中率、预填字段原文原样一致性（口径零加工）、B-1/B-4 误报/漏报率。
- **时延 SLA**：review≤60s、d02≤20s、d03≤5s（基线与目标）。
- **可用性**：接口成功率、vLLM 超时率（修复 F11 后可正确感知）。
- **可观测**：traceId 覆盖率 100%、`/metrics` 暴露 QPS/错误率/模型延迟/Token。
- **回归基线**：现有测试套件（含预填 52p、contract_review 套件、two_stage 套件）为「未碰」的回归证明；任何评审口径改动须保证旧测试期望不被静默修改制造全绿。

---

## 14. 风险与依赖

| 风险 | 等级 | 说明 / 缓解 |
|---|---|---|
| 共享 vLLM 算力挤占 | 中 | 评审/预填/翻译/总结共用实例且无并发闸门；上线新能力（review-summary）须留意节奏（F10） |
| 模型默认开思考导致 JSON 解析静默错误 | 高（已缓解） | 通过 `enable_thinking=False` 关闭；须确保该绑定只在调用点生效、不污染单例 |
| 超时错误码失真（F11） | 中 | 当前实际返 29999，运维/调用方无法区分超时；修复后须回归 |
| 本地/容器依赖漂移（F12） | 中 | 本地绿≠容器绿；CI 须以容器为准 |
| 签署地预设值强依赖 | 中 | review 依赖 `mock-preset-server`；该服务 `unhealthy` 是假警报，但停服会真实阻断 review（prefill 不碰） |
| 红线二冻结约束 | 高（受控） | 任何 `mode=review` 口径改动须走独立变更评审，不得静默修改 |

---

## 附录 A：术语表

| 术语 | 含义 |
|---|---|
| MVP | 单阶段旧流程 `POST /api/v1/contract-review`（含预填），已上线冻结基线 |
| D-02 / D-03 | 合同系统结构化录入表单：D-02（19 字段）、D-03（9 字段） |
| 预填 scope | `all`/`d02`/`d03`，决定抽取哪些字段组 |
| 红线一/二 | 不碰 `two_stage/**`；`mode=review` 只关思考、口径冻结 |
| traceId | 全链路关联 ID，所有响应注入 |
| 签署地预设值 | review 强依赖的内部主数据服务（实体名/法定代表人/授权人/账户等） |

## 附录 B：预填字段速查（26 字段）

```
contract_info (D-02, 9): payment_terms, payment_method, service_content, service_valid_months,
                         service_sla, service_start_date, service_end_date,
                         onsite_service_count, inspection_count
contract_plan (D-02, 每项 8): milestone_name, milestone_code, milestone_text,
                               milestone_seq(int), plan_finish_date, plan_payment_date,
                               payment_amount, evidence[]
finance_info (共用, 2): contract_amount, currency
guarantee (D-03, 每项 7): type, amount, payee, bank_name, bank_account,
                           return_clause, evidence[]
```

---

> 本文档为 `contract_review` 能力完整 PRD 初稿，用于产品/研发/业务对齐。所有口径、检查逻辑、错误码、性能基线均以当前代码实现与 OpenSpec 规格为事实基准；凡涉及 `mode=review` 口径的修改，须遵循第 2.3 条红线与第 14 章风险管控。
