# LTC AI 能力服务

LTC（Lead to Cash）系统的 AI 中台能力层。提供健康检查、文本翻译、合同组织评审接口，内部用 LangChain 调用私有化 vLLM 大模型（Qwen3.6-35B-A3B / DeepSeek V4-Flash）。

## 接口

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/health` | 否 | 存活探针 |
| GET | `/metrics` | 否 | Prometheus 指标 |
| POST | `/api/v1/translate` | 是 | 文本翻译 |
| POST | `/api/v1/contract-review` | 是 | 合同组织评审 |
| POST | `/api/v1/contract-review/upload-md` | 是 | 上传解析后的 Markdown 合同与附件进行组织评审 |

### 翻译示例

```bash
curl -X POST http://localhost:8000/api/v1/translate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{"text":"本合同自双方签字之日起生效","target_lang":"en"}'
```

成功响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {"translated_text": "...", "source_lang": "zh", "model": "qwen3.6-35b-a3b", "token_usage": {...}},
  "traceId": "a1b2c3...",
  "duration_seconds": 0.842
}
```

错误响应同样带 `traceId` 和 `duration_seconds`。错误码：`0` 成功；`1xxxx` 客户端错误（`10001` 参数校验、`10002` 鉴权失败）；`2xxxx` 服务端错误（`20001` 模型调用失败重试耗尽、`20002` 超时、`20003` 格式异常、`29999` 未知）。

### 合同组织评审示例

正式业务流程推荐上传解析后的 Markdown 文件：

```bash
curl -X POST http://localhost:8000/api/v1/contract-review/upload-md \
  -H "X-API-Key: <your-key>" \
  -F "contract_file=@合同正文.md;type=text/markdown" \
  -F "attachment_files=@附件一.md;type=text/markdown" \
  -F "attachment_files=@附件二.md;type=text/markdown"
```

系统会按上传顺序为附件生成 `index=1,2,3...`，并复用同一套合同组织评审规则。

JSON 调用保留用于自动化联调：

```bash
curl -X POST http://localhost:8000/api/v1/contract-review \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{"contract_md":"# 合同\n正文","attachments":[]}'
```

## 本地开发

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
LTC_ENV=dev .venv/Scripts/python -m uvicorn app.main:app --reload
```

如需鉴权可联调，设置 API Key：

```bash
$env:LTC_ENV="dev"; $env:LTC__AUTH__API_KEYS='["7C218CEA-1BD7-48B1-B839-62F03FB082AA"]'; python -m uvicorn app.main:app --reload
```

## 配置

加载优先级：环境变量 > `config-{LTC_ENV}.yaml` > `config.yaml` > 默认。

| 环境变量 | 说明 |
|---|---|
| `LTC_ENV` | `dev` / `test` / `prod` |
| `LTC__LLM__BASE_URL` | vLLM OpenAI 兼容端点 |
| `LTC__LLM__MODEL` | 模型名 |
| `LTC__AUTH__API_KEYS` | API Key 白名单（JSON 数组） |
| `LTC__SIGNING_PRESET__BASE_URL` | 签署地预设值服务基础地址 |
| `LTC__SIGNING_PRESET__PATH` | 签署地预设值按主体名称查询路径 |
| `LTC__SIGNING_PRESET__TIMEOUT` | 签署地预设值查询超时时间（秒） |

密钥通过环境变量注入，不入代码库。见 `.env.example`。

## 测试

```bash
.venv/Scripts/python -m pytest tests/ -v
```

测试在模型层边界 mock，CI 不依赖 vLLM 可用性。

## 变更编排器（Explore -> Propose）

仓库提供了“Skill 作为大脑 + 脚本作为手脚”的最小编排器：

- Skill: `.agents/skills/change-orchestrator/SKILL.md`
- Script: `scripts/change_orchestrator.ps1`
- Playbook: `docs/superpowers/playbooks/change-orchestrator.md`

常用命令：

```powershell
# 1) 先讨论，判断要不要建 OpenSpec change
./scripts/change_orchestrator.ps1 -Mode explore -Title "B-1 reason wording" -Impact "api message wording" -Concern "avoid ambiguity"

# 2) 确认立项后创建 change 骨架
./scripts/change_orchestrator.ps1 -Mode propose -ChangeName b1-reason-wording -Title "B-1 reason wording" -Capability contract-review

# 3) 执行严格校验
./scripts/change_orchestrator.ps1 -Mode validate -ChangeName b1-reason-wording
```

## 容器部署

```bash
# 构建
docker compose build

# 生产
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 测试
docker compose -f docker-compose.yml -f docker-compose.test.yml up -d
```

资源限制通过 `deploy.resources`（CPUs/内存）配置，环境靠 `LTC_ENV` 与挂载的 `config/` 切换，无需重建镜像。

## 架构

薄分层 + 能力包式结构：

```
API 层 (FastAPI Router + Pydantic)
  → 能力层 (capabilities/translate/, capabilities/contract_review/)   组装 prompt、规则检查、重试
    → 模型适配层 (models/llm.py)        LangChain ChatModel 适配 vLLM
    → 基础设施层 (core/)              配置/日志/错误/中间件
```

能力之间互不依赖，未来加 OCR/摘要只需在 `app/capabilities/` 下新增独立包并在 `main.py` 注册。详见 `docs/superpowers/specs/2026-07-01-ltc-ai-translate-service-design.md`。
