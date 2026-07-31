# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## 项目概述

LTC AI 能力服务是 LTC（Lead to Cash）系统的 AI 中台能力层，基于 FastAPI + LangChain 构建，调用私有化 vLLM 大模型（Qwen3.6-35B-A3B / DeepSeek V4-Flash）。

## 常用命令

### 开发环境搭建

```bash
# 创建虚拟环境并安装依赖
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

### 本地运行

```bash
# 基础运行（无鉴权）
LTC_ENV=dev .venv/Scripts/python -m uvicorn app.main:app --reload

# PowerShell 带鉴权联调
$env:LTC_ENV="dev"; $env:LTC__AUTH__API_KEYS='["changeme-api-key"]'; python -m uvicorn app.main:app --reload
```

### 测试

```bash
# 运行全部测试
.venv/Scripts/python -m pytest tests/ -v

# 运行单个测试文件
.venv/Scripts/python -m pytest tests/test_translate_service.py -v

# 运行单个测试函数
.venv/Scripts/python -m pytest tests/test_translate_api.py::test_translate_success_contract -v
```

### 容器部署

```bash
# 构建镜像
docker compose build

# 生产环境运行
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 测试环境运行
docker compose -f docker-compose.yml -f docker-compose.test.yml up -d
```

## 架构设计

### 分层结构

采用"薄分层 + 能力包"结构，能力之间零依赖：

```
API 层 (FastAPI Router + Pydantic)
  → 能力层 (app/capabilities/{ capability }/)   # 组装 prompt、重试逻辑
    → 模型适配层 (app/models/llm.py)            # LangChain ChatModel 工厂
      → 基础设施层 (app/core/)                  # 配置/日志/错误/中间件
```

新增能力（如 OCR/摘要）只需在 `app/capabilities/` 下新建独立包并在 `main.py` 注册路由。

### 配置系统

优先级（高→低）：环境变量 > `config-{LTC_ENV}.yaml` > `config.yaml` > 默认值。

环境变量使用双下划线分隔嵌套属性，前缀为 `LTC__`：

- `LTC_ENV` - 运行环境：`dev` / `test` / `prod`
- `LTC__LLM__BASE_URL` - vLLM OpenAI 兼容端点
- `LTC__LLM__MODEL` - 模型名
- `LTC__LLM__API_KEY` - vLLM OpenAI 兼容端点 API Key
- `LTC__AUTH__API_KEYS` - API Key 白名单（JSON 数组字符串）
- `LTC__SIGNING_PRESET__BASE_URL` - 签署地预设值服务基础地址
- `LTC__SIGNING_PRESET__PATH` - 签署地预设值按主体名称查询路径
- `LTC__SIGNING_PRESET__TIMEOUT` - 签署地预设值查询超时时间（秒）

配置加载实现见 `app/core/config.py`，使用 Pydantic Settings 自定义 `YamlSettingsSource`。

### 错误处理

统一错误码体系（`app/core/errors.py`）：
- `0` - 成功
- `1xxxx` - 客户端错误（`10001` 参数校验、`10002` 鉴权失败）
- `2xxxx` - 服务端错误（`20001` 模型调用失败重试耗尽、`20002` 超时、`20003` 格式异常、`29999` 未知）

所有响应包含 `traceId` 和 `duration_seconds` 字段，由 `TraceIdMiddleware` 注入。

### 中间件执行顺序

中间件注册顺序决定执行顺序（后 add 的更外层）：

1. `TraceIdMiddleware`（最外层）- 生成/透传 traceId，计时，注入响应字段
2. `AuthMiddleware` - API Key 校验，`/health` 与 `/metrics` 放行

### 模型调用与重试

- 模型调用封装在 `app/models/llm.py`，返回 `(content, token_usage)`
- 重试逻辑仅在 service 层实现（指数退避 + 抖动），最多 3 次尝试
- 可重试错误：超时、5xx、429；不可重试：格式错误等

### 单例模式与测试

配置（`get_settings()`）和模型（`get_chat_model()`）使用模块级单例。测试通过 `conftest.py` 中的 fixture 自动重置单例状态。

### Prompt 管理

Prompt 模板存放在 `prompts/` 目录下的 YAML 文件，通过 `app/capabilities/translate/prompts.py` 加载并构造 LangChain 消息列表。

## 接口清单

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/health` | 否 | 存活探针 |
| GET | `/metrics` | 否 | Prometheus 指标 |
| POST | `/api/v1/translate` | 是 | 文本翻译 |
| POST | `/api/v1/contract-review` | 是 | 合同组织评审 |
| POST | `/api/v1/contract-review/upload-md` | 是 | 上传解析后的 Markdown 合同与附件进行组织评审 |

## 测试策略

- 模型层边界统一 mock，CI 不依赖 vLLM 可用性
- 使用 `TestClient` 测试 API 契约
- 中间件测试使用 `create_app(register_middleware=False)` 禁用中间件以隔离测试

## 合同评审两阶段升级

任务涉及下列任一范围时，必须先完整读取 `app/capabilities/contract_review/two_stage/AGENTS.md`：

- `app/capabilities/contract_review/two_stage/**`；
- 两阶段升级相关的 API 注册、配置或公共错误码；
- 两阶段升级相关测试；
- `contract-review-context-foundation`、`contract-review-prepare-api`、`contract-review-evaluate-api`、`contract-review-two-stage-pilot` OpenSpec 变更；
- 两阶段升级方案或合同系统协作文档。

该专用文件只约束两阶段升级。未明确纳入升级范围的现有合同评审代码继续遵循本文件和当前已生效契约，不因未来方案草稿自动改变行为。

## 变更编排流程（Skill + Script）

仓库提供两阶段变更编排：`Explore -> Propose`。

- Skill（大脑）：`.agents/skills/change-orchestrator/SKILL.md`
- Script（手脚）：`scripts/change_orchestrator.ps1`
- Playbook：`docs/superpowers/playbooks/change-orchestrator.md`

推荐命令：

```powershell
# 1) 先讨论，判断是否需要创建 OpenSpec change
./scripts/change_orchestrator.ps1 -Mode explore -Title "B-1 reason wording" -Impact "api message wording" -Concern "avoid ambiguity"

# 2) 决定立项后，创建 change 骨架
./scripts/change_orchestrator.ps1 -Mode propose -ChangeName b1-reason-wording -Title "B-1 reason wording" -Capability contract-review

# 3) 提交流程前执行严格校验
./scripts/change_orchestrator.ps1 -Mode validate -ChangeName b1-reason-wording
```

执行约定：

- 先 explore 再 propose，避免先建 change 后改方向。
- 调用方可见行为变化，默认走 OpenSpec change。
- `design.md` 为可选工件，仅在多方案权衡或架构调整时补齐。
