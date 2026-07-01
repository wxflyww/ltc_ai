# LTC AI能力服务 — 详细设计文档

| 项目 | 内容 |
|---|---|
| 文档版本 | V1.0 |
| 撰写人 | Johnny |
| 状态 | 草稿 |
| 更新日期 | 2026-07-01 |
| 关联PRD | `docs/LTC-AI能力服务-PRD.md` |

---

## 0. 范围与关键决策

本设计严格对齐 PRD 4.1 节首期 API 清单，仅详细设计「健康检查 + 文本翻译」接口及其配套（多环境配置、容器化、可观测性、统一错误处理）。PRD 背景与第 2 节提及的 OCR、合同结构化、审批摘要、Agent 编排等更广能力，本期仅作为**预留扩展点**，不在本期落地。

### 已确认的关键决策

| 维度 | 决策 |
|---|---|
| 设计范围 | 仅翻译 + 健康检查（对齐 PRD 4.1），其余能力仅预留扩展点 |
| 翻译形态 | 单条同步 |
| 重试降级 | 指数退避重试 3 次（1s/2s 间隔）+ 失败报错，不做内容降级 |
| 鉴权 | API Key |
| LangChain | 用 LangChain 调模型 + 管理 Prompt（PromptTemplate + YAML 集中管理） |
| 就绪探针 | 仅 `GET /health`，不实现 `/health/ready` |
| metrics 端点 | `/metrics` 不鉴权，靠网络隔离保护 |
| 架构 | 方案 A：薄分层 + 能力包式结构 |

---

## 1. 总体架构与分层

四层，自上而下，每层职责单一、向下依赖：

```
┌─────────────────────────────────────────────┐
│ API 层  (FastAPI Router + Pydantic Schema)  │  HTTP 进出、校验、traceId 注入
├─────────────────────────────────────────────┤
│ 能力层  (capabilities/translate/)            │  翻译业务：组装 prompt、重试、降级
├─────────────────────────────────────────────┤
│ 模型适配层 (models/llm.py)                  │  LangChain ChatModel 适配 vLLM OpenAI 兼容
├─────────────────────────────────────────────┤
│ 基础设施层 (core/)                           │  配置、日志、错误、API Key、traceId
└─────────────────────────────────────────────┘
        │  HTTP (OpenAI 兼容)
        ▼
   vLLM 私有化大模型 (Qwen3.6-35B-A3B / DeepSeek V4-Flash)
```

### 依赖方向

API → 能力 → 模型适配 → 基础设施。基础设施被所有层依赖，但不反向依赖上层。能力层之间不互相依赖（未来加 OCR 不影响翻译）。

### 关键边界

- **能力层**是唯一知道「这是翻译」的地方 —— 组装 prompt、调模型、处理重试。换掉翻译逻辑不影响 API 层和模型层。
- **模型适配层**只暴露一个 `get_chat_model()` 工厂，返回 LangChain `BaseChatModel`，对上层屏蔽 vLLM 地址/模型名/温度等细节（这些来自配置）。
- **基础设施层**不知道任何具体能力，只提供横切关注点。

### 进程模型

单进程 FastAPI（uvicorn），首期无需 worker 进程管理；水平扩展靠多容器实例（docker compose replicas），无状态。

---

## 2. 组件清单与目录结构

能力包式结构，每个文件一个清晰职责：

```
ltc_ai/
├── app/
│   ├── main.py                    # FastAPI 应用装配：注册路由、中间件、异常处理器、生命周期
│   ├── core/
│   │   ├── config.py              # 多环境配置加载（env > config-{env}.yaml > 默认）
│   │   ├── logging.py             # 结构化 JSON 日志，注入 traceId
│   │   ├── errors.py              # 统一错误码定义 + 业务异常基类
│   │   ├── exception_handlers.py  # 全局异常→统一响应格式转换
│   │   ├── middleware.py          # traceId 注入、API Key 校验、耗时记录
│   │   └── response.py            # 统一响应包装（code/message/data/traceId/duration_seconds）
│   ├── models/
│   │   └── llm.py                 # LangChain ChatModel 工厂：从配置构造 vLLM 适配模型
│   └── capabilities/
│       ├── __init__.py
│       └── translate/
│           ├── router.py          # POST /api/v1/translate 路由
│           ├── service.py        # 翻译业务：组装prompt、调模型、重试逻辑
│           ├── schemas.py        # TranslateRequest / TranslateResponse (Pydantic)
│           └── prompts.py        # 加载 prompts/translate.yaml，构造 PromptTemplate
├── prompts/
│   └── translate.yaml             # 翻译 prompt 模板（集中管理，便于迭代/A-B）
├── config/
│   ├── config.yaml                # 默认配置（公共基线）
│   ├── config-dev.yaml            # dev 覆盖
│   ├── config-test.yaml           # test 覆盖
│   └── config-prod.yaml           # prod 覆盖（密钥走环境变量，不入库）
├── tests/
│   ├── conftest.py                # pytest fixture：mock LLM client、TestClient
│   ├── test_translate_api.py      # 接口级测试（mock 模型层）
│   ├── test_translate_service.py   # 重试/降级逻辑单测
│   └── test_health.py             # 健康检查
├── Dockerfile                     # 多阶段构建，python:3.11-slim
├── docker-compose.yml             # 基础
├── docker-compose.test.yml        # 测试环境 override
├── docker-compose.prod.yml        # 生产环境 override
├── .env.example                   # 环境变量样例（密钥占位，不入库真实值）
├── pyproject.toml                 # 依赖与项目元数据
└── README.md
```

### 组件职责一览

| 组件 | 职责 | 依赖 |
|---|---|---|
| `main.py` | 装配应用，唯一入口 | 所有 core + capabilities |
| `core/config.py` | 加载并合并配置，暴露全局 Settings | pydantic-settings |
| `core/middleware.py` | traceId 生成/透传、API Key 校验、请求耗时记录 | core/config, core/logging |
| `core/errors.py` + `exception_handlers.py` | 错误码表 + 异常→HTTP 响应映射 | core/response |
| `core/response.py` | 统一响应包装 `{ code, message, data, traceId, duration_seconds }` | — |
| `models/llm.py` | `get_chat_model()` 返回配置好的 ChatModel | core/config, langchain |
| `capabilities/translate/router.py` | 路由 + 请求校验，调用 service | translate/service, translate/schemas |
| `translate/service.py` | 组装 prompt、调模型、指数退避重试 | models/llm, translate/prompts |
| `translate/prompts.py` | 加载 YAML 模板构造 PromptTemplate | prompts/translate.yaml |

### 两个关键决策

1. **Prompt 用 YAML 而非硬编码** — 满足 PRD 4.2「Prompt 模板集中管理，便于迭代与 A/B」。改 prompt 不动代码，且为未来 A/B（同目录放 `translate_v2.yaml`）留口子。
2. **测试 mock 在模型层边界** — `tests/` 通过 mock `models/llm.py` 的 `get_chat_model()` 返回值来测 service，不真正打 vLLM。这让接口/重试逻辑可单测，且 CI 不依赖大模型可用性。

---

## 3. 数据流与接口契约

### 翻译请求的端到端数据流

```
LTC系统
  │ POST /api/v1/translate  (Header: X-API-Key, X-Trace-Id?)
  ▼
[middleware]  生成/透传 traceId → API Key 校验 → 开始计时
  ▼
[router]  Pydantic 校验 TranslateRequest
  ▼
[service]  从 prompts 加载模板 → 用 PromptTemplate 组装最终 prompt
  ▼
[service]  调 models/llm.get_chat_model() → 指数退避重试 (1s/2s, 共3次)
  ▼
[models/llm]  LangChain ChatModel → vLLM OpenAI 兼容接口
  ▼
[service]  提取译文，组装 TranslateResponse
  ▼
[middleware]  记录耗时 + traceId → 统一响应包装
  ▼
LTC系统收到 { code, message, data, traceId, duration_seconds }
```

traceId 优先级：请求头 `X-Trace-Id` 透传 > 自动生成 UUID。这样 LTC 侧可传自己的 traceId，跨系统日志可串联。

### 接口契约

#### `GET /health` — 存活探针，不鉴权

```jsonc
// 200
{ "status": "ok", "version": "1.0.0" }
```

仅探进程存活，不打 vLLM（避免探针拖垮服务）。

#### `POST /api/v1/translate` — 文本翻译，需鉴权

```jsonc
// 请求
{
  "text": "本合同自双方签字之日起生效",   // 必填，源文本
  "target_lang": "en"                      // 必填，目标语言代码
}

// 成功响应 200
{
  "code": 0,
  "message": "ok",
  "data": {
    "translated_text": "This contract takes effect upon signature by both parties.",
    "source_lang": "zh",                  // 源语言回填（入参未传则模型自识别）
    "model": "qwen3.6-35b-a3b",           // 实际使用的模型名，便于排查
    "token_usage": { "prompt_tokens": 12, "completion_tokens": 14, "total_tokens": 26 }
  },
  "traceId": "a1b2c3...",
  "duration_seconds": 0.842                // 本次调用总耗时（秒，3位小数）
}

// 错误响应（示例：模型调用失败）
{
  "code": 20001,
  "message": "模型调用失败，重试耗尽",
  "data": null,
  "traceId": "a1b2...",
  "duration_seconds": 3.124
}
```

**字段说明**：

| 字段 | 位置 | 说明 |
|---|---|---|
| `text` | 请求 | 必填，源文本 |
| `target_lang` | 请求 | 必填，目标语言代码（`en`/`zh`/`ja`…），不做枚举强校验，未知语言由模型处理或返回错误码 |
| `source_lang` | 请求可选 | 源语言代码；不传则由模型自识别并在响应回填 |
| `translated_text` | 响应 data | 译文 |
| `model` | 响应 data | 实际使用的模型名，便于排查"为什么这条译得不好" |
| `token_usage` | 响应 data | token 消耗，支撑 Prometheus Token 指标 |
| `duration_seconds` | 响应顶层 | 本次调用总耗时（秒，3位小数），与 `traceId` 并列，成功/错误响应都带 |

**请求头**：

| 头 | 说明 |
|---|---|
| `X-API-Key` 或 `Authorization: Bearer <key>` | 鉴权凭证，必填 |
| `X-Trace-Id` | 可选，透传调用方 traceId；未传则服务端生成 |

### 统一响应格式与错误码

所有接口统一 `{ code, message, data, traceId, duration_seconds }`。`code=0` 成功，非 0 为错误码。错误码分段：

| 码段 | 含义 | 示例 |
|---|---|---|
| `0` | 成功 | — |
| `1xxxx` | 客户端错误 | `10001` 参数校验失败、`10002` API Key 无效/缺失 |
| `2xxxx` | 服务端错误 | `20001` 模型调用失败(重试耗尽)、`20002` 模型超时、`20003` 模型返回格式异常、`29999` 未捕获异常兜底 |

HTTP 状态码与 `code` 映射：客户端错误→400/401/422，服务端错误→500/504。`traceId` 和 `duration_seconds` 在错误响应也必带。

---

## 4. 错误处理与重试/降级细节

### 重试策略（指数退避）

`translate/service.py` 调模型时的重试规则：

| 参数 | 值 | 说明 |
|---|---|---|
| 最大尝试次数 | 3 次（1 次初始 + 2 次重试） | 不无限重试，保护 vLLM |
| 退避间隔 | 1s → 2s（指数翻倍） | 共最多额外等待 3s |
| 重试条件 | 仅对**可重试错误**重试 | 见下表 |
| 抖动 | ±20% 随机抖动 | 避免重试风暴（多实例同时重试砸 vLLM） |

**可重试 vs 不可重试**：

| 错误类型 | 可重试? | 理由 |
|---|---|---|
| 连接超时 / 读取超时 | ✅ | 瞬态，vLLM 可能瞬时拥塞 |
| 5xx（vLLM 服务端错误） | ✅ | 瞬态 |
| 429（限流） | ✅ | 退避后可能恢复 |
| 4xx 非 429（如 400 参数错、401 鉴权错） | ❌ | 重试无意义，立即失败 |
| 模型返回格式异常（JSON 解析失败等） | ❌ | 非瞬态，重试结果不变 |

实现用 tenacity 控制重试，重试耗尽后抛 `ModelInvocationError`，由全局异常处理器转成 `code=20001`、HTTP 500。

### 降级策略

**不做内容降级** —— 不返回缓存译文、不切备选模型、不返回机器翻译备选。重试到上限仍失败，直接返回明确错误码 `20001`，让 LTC 侧决定如何处理（重试调用、走人工、或降级到其他流程）。

权衡：内容降级会让接口语义模糊（LTC 侧不知道拿到的是模型译文还是降级文本），且引入缓存依赖。清晰报错 + 让调用方决策，契约更干净。

### 错误处理分层

| 层 | 触发场景 | 错误码 | HTTP 状态 |
|---|---|---|---|
| `router` | Pydantic 校验失败 | `10001` | 422 |
| `middleware` | API Key 缺失/无效 | `10002` | 401 |
| `service` | 入参业务校验（如空文本） | `10001` | 400 |
| `models/llm` | 超时 | `20002` | 504 |
| `service` | 重试耗尽仍失败 | `20001` | 500 |
| `service` | 模型返回格式异常 | `20003` | 500 |
| 全局 | 未捕获异常兜底 | `29999` | 500 |

所有异常都经过 `core/exception_handlers.py` 转成统一 `{ code, message, data:null, traceId, duration_seconds }` 格式。traceId 和 duration_seconds 在异常路径也注入，保证错误响应可追溯。

### 关键边界

- **重试逻辑只在 service 层**，模型适配层不重试（只做调用 + 抛出原始错误）。这样重试策略可随能力调整，不污染模型层。
- **错误码集中定义在 `core/errors.py`**，避免散落字符串。新增能力复用同一套码段规则。
- **结构化日志在异常路径也记录**：每次重试记 warn，最终失败记 error，均带 traceId + 接口耗时（秒）+ 模型调用耗时（秒）。

---

## 5. 配置 / 部署 / 可观测性

### 多环境配置（对齐 PRD 5.1）

加载优先级（高→低）：**环境变量 > config-{env}.yaml > config.yaml（默认基线）**。

`core/config.py` 用 `pydantic-settings` 实现：先加载 `config.yaml` 默认基线，再用 `LTC_ENV` 环境变量（`dev`/`test`/`prod`）选 `config-{env}.yaml` 覆盖，最后环境变量再覆盖一遍。

```yaml
# config/config.yaml — 默认基线（公共配置）
server:
  host: "0.0.0.0"
  port: 8000
  log_level: "INFO"
llm:
  base_url: ""          # vLLM OpenAI 兼容端点，各环境覆盖
  model: "qwen3.6-35b-a3b"
  temperature: 0.3
  timeout: 30
auth:
  api_keys: []          # 生产走环境变量注入，不入库
```

```yaml
# config/config-prod.yaml — 生产覆盖
llm:
  base_url: "http://vllm-prod.internal:8000/v1"
  model: "qwen3.6-35b-a3b"
server:
  log_level: "WARNING"
```

**密钥不入库**：`api_keys`、`base_url`（如含凭证）等敏感项在 yaml 里留空或占位，通过 `.env` / 环境变量注入。`.env.example` 提交占位样例，真实 `.env` 在 `.gitignore` 内。镜像构建时不打环境配置进去，靠运行时挂载/环境变量切换 —— 满足 PRD「无需重新构建镜像切换环境」。

### 容器化（对齐 PRD 5.2）

**Dockerfile**（多阶段，`python:3.11-slim`）：
- 阶段 1（builder）：装编译依赖、`pip install` 到虚拟环境
- 阶段 2（runtime）：只拷虚拟环境 + 应用代码，非 root 用户运行，无编译工具
- 产物镜像小、攻击面小

**docker-compose**（base + override）：
- `docker-compose.yml`：基础服务定义（端口、健康检查、资源限制）
- `docker-compose.test.yml` / `docker-compose.prod.yml`：override `LTC_ENV`、资源限制、日志级别、挂载的配置文件
- 启动：`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`
- 资源限制通过 `deploy.resources`（CPUs/内存），对齐 PRD

### 可观测性（对齐 PRD 5.3）

**结构化日志**（JSON）—— `core/logging.py` 配置，每条日志含：

```json
{
  "timestamp": "2026-07-01T10:30:00.123Z",
  "level": "INFO",
  "traceId": "a1b2c3...",
  "endpoint": "/api/v1/translate",
  "duration_seconds": 0.842,
  "llm_duration_seconds": 0.780,
  "message": "..."
}
```

- `duration_seconds`：本次调用总耗时（秒），与响应里的 `duration_seconds` 同源。
- `llm_duration_seconds`：仅模型调用耗时（秒，含重试累计）。两者分开便于区分「服务自身开销」和「模型等待」。

秒采用 3 位小数（`0.842s` = `842ms`），不丢精度，且与接口契约单位一致。

**Prometheus 指标**（`/metrics` 端点，`prometheus-fastapi-instrumentator`）：

| 指标 | 类型 | 说明 |
|---|---|---|
| `http_requests_total{endpoint,code}` | Counter | QPS、错误率 |
| `http_request_duration_seconds{endpoint}` | Histogram | 接口延迟 |
| `llm_calls_total{model,status}` | Counter | 模型调用成功/失败 |
| `llm_call_duration_seconds{model}` | Histogram | 模型调用延迟 |
| `llm_tokens_total{model,type}` | Counter | Token 消耗（prompt/completion） |

模型相关指标在 `models/llm.py` 调用前后埋点，HTTP 指标由 instrumentator 自动采集。`/metrics` 不鉴权，靠网络隔离保护。

**接入现有监控告警** —— Prometheus scrape 配置由运维侧加，本期只保证 `/metrics` 暴露标准格式。

### 安全（对齐 PRD 5.4）

- API Key 校验中间件：从 `Authorization: Bearer <key>` 或 `X-API-Key` 头读取，与配置的 `api_keys` 白名单比对。
- `/health` 和 `/metrics` 不鉴权（前者是探针、后者靠网络隔离保护）。
- vLLM 端点内网访问，服务不出公网。

---

## 6. 测试策略

| 测试文件 | 范围 | 说明 |
|---|---|---|
| `tests/test_health.py` | `GET /health` | 验证存活探针返回 |
| `tests/test_translate_api.py` | 接口级 | 通过 TestClient + mock `get_chat_model()`，验证请求/响应契约、鉴权、错误码、`duration_seconds`/`traceId` 字段 |
| `tests/test_translate_service.py` | 重试/降级逻辑 | mock 模型层抛可重试/不可重试错误，验证重试次数、退避间隔、最终错误码 |

测试在模型层边界 mock，CI 不依赖 vLLM 可用性。模型适配层与 vLLM 的真实集成另由部署侧冒烟测试覆盖（不在本期自动化测试范围）。

---

## 7. 扩展点（本期不实现）

为 PRD 背景中提及的更广能力预留以下扩展点，本期不落地：

- **新增能力**：在 `app/capabilities/` 下新增独立包（如 `capabilities/ocr/`、`capabilities/summarize/`），自包含 router/service/schemas/prompts，在 `main.py` 注册即可，不影响现有能力。
- **Agent 编排**：未来基于 LangChain 构建 Agent 时，复用 `models/llm.py` 的 `get_chat_model()` 工厂与 `core/` 横切设施。
- **Prompt A/B**：`prompts/` 下新增版本化模板文件（如 `translate_v2.yaml`），`prompts.py` 按配置选择加载。
- **就绪探针**：如需区分「服务存活」与「模型可调」，未来加 `GET /health/ready` 轻量探测 vLLM。
