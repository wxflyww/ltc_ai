# 合同评审接口临时联调文档

> 版本：legacy-temporary-integration-v1
>
> 更新日期：2026-08-03
>
> 适用范围：当前非两阶段合同评审接口，仅供合同系统临时搭建测试工程使用。
>

## 1. 接口概览

合同系统可以选择以下任一入口：

| 入口 | 方法与路径 | 请求类型 | 适用场景 |
|---|---|---|---|
| JSON 入口（推荐临时联调） | `POST /api/v1/contract-review` | `application/json` | 文档解析服务已经生成 Markdown，合同系统直接传文本 |
| Markdown 文件入口 | `POST /api/v1/contract-review/upload-md` | `multipart/form-data` | 测试工程需要直接上传主合同 Markdown 和附件 Markdown |

两个入口最终进入同一条评审流水线，返回结构一致。

服务基础地址由部署环境提供，以下以 `<AI_BASE_URL>` 表示。例如：

```text
<AI_BASE_URL>/api/v1/contract-review
```

## 2. 鉴权与请求头

API Key 是否必填取决于服务启动配置：

- 本地 `dev/test` 环境如果没有配置 `LTC__AUTH__API_KEYS`，鉴权中间件会放行，测试可以不传 API Key。
- 任意环境一旦配置了 `LTC__AUTH__API_KEYS`，业务请求就必须传入白名单中的 API Key。
- `prod` 环境必须配置 `LTC__AUTH__API_KEYS`；没有配置时服务拒绝启动，因此生产请求实际必须带 API Key。

服务启用鉴权时，任选一种方式传递：

```http
X-API-Key: <API_KEY>
```

或：

```http
Authorization: Bearer <API_KEY>
```

未启用鉴权时，以下请求头可以省略。可选传入链路追踪号：

```http
X-Trace-Id: <调用方生成的追踪号>
```

如果未传 `X-Trace-Id`，服务会自动生成。响应中的 `traceId` 应由合同系统记录，便于联调排查。

## 3. JSON 入口

### 3.1 请求

```http
POST <AI_BASE_URL>/api/v1/contract-review
Content-Type: application/json
X-API-Key: <API_KEY>
```

请求体：

```json
{
  "contract_md": "# 软件采购合同\n\n合同正文 Markdown 全文",
  "attachments": [
    {
      "index": 1,
      "filename": "附件一-技术协议.docx",
      "file_type": "docx",
      "text": "附件已经由上游解析得到的 Markdown 或文本"
    }
  ]
}
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `contract_md` | string | 是 | 主合同 Markdown。最短 1 个字符；建议传完整解析结果，不要只传摘要。 |
| `attachments` | array | 否 | 单独上传并已解析的附件文本；不传时默认为空数组。 |
| `attachments[].index` | integer 或 null | 否 | 附件序号。接口不依赖其唯一性；建议按合同系统展示顺序从 1 开始。 |
| `attachments[].filename` | string | 是 | 附件文件名，不能为空。 JSON 入口不强制 `.md` 后缀。 |
| `attachments[].file_type` | string 或 null | 否 | 原始文件类型或自定义类型，接口只透传使用，不做固定枚举校验。 |
| `attachments[].text` | string | 否 | 附件解析后的文本；省略时默认为空字符串。 |

 JSON 入口当前没有以下字段：

```text
contract_id
revision_id
document_id
attachment_id
source_file_sha256
parsed_content_sha256
document_set_hash
parser_meta
```

不要把两阶段 `prepare` 请求字段混入此接口。

### 3.2 请求示例

无附件：

```json
{
  "contract_md": "# 服务合同\n\n合同正文……",
  "attachments": []
}
```

带两个附件：

```json
{
  "contract_md": "# 软件采购合同\n\n甲方：客户公司\n乙方：我方公司\n\n正文……",
  "attachments": [
    {
      "index": 1,
      "filename": "附件一-报价清单.xlsx",
      "file_type": "xlsx",
      "text": "# 报价清单\n\n总价：100,000 元"
    },
    {
      "index": 2,
      "filename": "附件二-技术协议.docx",
      "file_type": "docx",
      "text": "# 技术协议\n\n技术要求……"
    }
  ]
}
```

### 3.3 JSON 调用注意事项

- `contract_md` 应传完整正文。流程会尝试从主 Markdown 中识别并拆出正文内嵌附件，再对正文和附件分别执行相关检查。
- 正文内嵌附件不要重复放入 `attachments`；接口没有稳定附件身份，重复输入可能导致重复检查或标题/数量结果异常。
- JSON 入口对附件 `text` 为空不做入口级拒绝，但空附件可能导致附件数量、标题或内容检查出现失败/提示。测试工程应尽量不要传空附件。
- JSON 入口对 `contract_md` 只做最短长度校验；纯空白正文不应作为有效合同提交。multipart 入口对纯空白主文件会明确拒绝。
- 接口没有跨请求版本控制。合同或附件发生变化时，合同系统应重新提交完整的当前主合同和附件集合，并自行管理结果对应的业务版本。

## 4. Markdown 文件入口

### 4.1 请求

```http
POST <AI_BASE_URL>/api/v1/contract-review/upload-md
Content-Type: multipart/form-data
X-API-Key: <API_KEY>
```

multipart 字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `contract_file` | file | 是 | 主合同 Markdown 文件；文件名必须以 `.md` 结尾，内容必须是 UTF-8，内容不能为空白。 |
| `attachment_files` | file[] | 否 | 可重复上传的附件 Markdown 文件；每个文件名必须以 `.md` 结尾，内容必须是 UTF-8。 |

附件字段应重复使用同一个字段名 `attachment_files`，不要提交 JSON 数组字符串。

### 4.2 curl 示例

```bash
curl -X POST "<AI_BASE_URL>/api/v1/contract-review/upload-md" \
  -H "X-API-Key: <API_KEY>" \
  -H "X-Trace-Id: legacy-test-001" \
  -F "contract_file=@./合同正文.md;type=text/markdown" \
  -F "attachment_files=@./附件一.md;type=text/markdown" \
  -F "attachment_files=@./附件二.md;type=text/markdown"
```

该入口会把文件转换成与 JSON 入口等价的请求：

```text
contract_md = contract_file 的 UTF-8 文本
attachments[].index = 按上传顺序从 1 开始
attachments[].filename = 上传文件名
attachments[].file_type = "md"
attachments[].text = 附件文件的 UTF-8 文本
```

### 4.3 文件入口的校验行为

- `contract_file` 缺失：参数校验失败。
- 主合同文件名不是 `.md`：HTTP 400，错误码 `10001`。
- 主合同不是 UTF-8：HTTP 400，错误码 `10001`。
- 主合同内容为空白：HTTP 400，错误码 `10001`。
- 附件文件名不是 `.md`：HTTP 400，错误码 `10001`。
- 附件不是 UTF-8：HTTP 400，错误码 `10001`。
- 附件内容为空：当前入口不会在上传层拒绝，但不建议提交空附件。

## 5. 成功响应

HTTP 状态码为 `200` 时，统一响应外层如下：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "overall_result": "PASS",
    "check_time": "2026-08-03T14:30:00",
    "checks": [
      {
        "id": "序号1",
        "name": "合同首页完整性",
        "result": "PASS",
        "block_level": "通过",
        "reason": null
      }
    ],
    "metrics": []
  },
  "traceId": "legacy-test-001",
  "duration_seconds": 12.345
}
```

### 5.1 `data` 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `overall_result` | `PASS` 或 `BLOCK` | 只要任一检查项同时为 `result=FAIL` 且 `block_level=硬阻断`，就是 `BLOCK`；否则为 `PASS`。 |
| `check_time` | string | 服务生成的检查时间，当前格式为 `YYYY-MM-DDTHH:MM:SS`，未带时区。 |
| `checks` | array | 所有检查项结果。数组顺序为当前流水线产生顺序，合同系统不要按 `id` 覆盖记录。 |
| `metrics` | array | 模型步骤耗时和 token 用量。可能为空。 |

`checks[]`：

| 字段 | 类型 | 取值 |
|---|---|---|
| `id` | string | 检查项标识，如 `序号1`、`B-1-合同正文`、`模型上下文长度`。 |
| `name` | string | 检查项名称。 |
| `result` | string | `PASS`、`WARN`、`FAIL`、`NA`。 |
| `block_level` | string | `通过`、`提示`、`硬阻断`、`不适用`。 |
| `reason` | string 或 null | 原因说明；通过且无说明时通常为 `null`。 |

同一个检查点可能出现多条记录。例如同时存在硬阻断和提示时，`checks` 中会保留两条相同 `id` 的记录，合同系统必须按数组逐条展示或保存。

常见检查项包括：

```text
序号1       合同首页完整性
序号2       签章页完整性
序号3       签署日期
序号7       总价大小写一致性
序号8       货币条款
序号9       付款方式
序号10      付款阶段
序号11      账户信息
序号12      合同份数
附件检查-数量标题
B-1-<检查范围>
B-4-<附件范围>
模型上下文长度
模型输出长度
```

检查项清单不是请求方可传入的参数，也不应由合同系统自行补造。

### 5.2 `metrics` 字段

当服务收集到模型步骤指标时，`metrics[]` 可能包含：

```json
{
  "id": "A-1a",
  "name": "首页/签约方提取",
  "duration_seconds": 1.234,
  "token_usage": {
    "prompt_tokens": 1000,
    "completion_tokens": 300,
    "total_tokens": 1300
  },
  "segments": []
}
```

`metrics` 只用于技术观测，不作为合同业务结论。合同系统不要依赖某个具体模型步骤一定存在。

## 6. 错误响应

错误仍使用统一响应壳：

```json
{
  "code": 10001,
  "message": "参数校验失败",
  "data": null,
  "traceId": "legacy-test-001",
  "duration_seconds": 0.012
}
```

主要错误：

| HTTP | `code` | 含义 | 典型场景 |
|---:|---:|---|---|
| 422 | `10001` | 参数校验失败 | JSON 缺少 `contract_md`、字段类型不正确、`filename` 为空 |
| 400 | `10001` | 文件/业务参数错误 | multipart 非 `.md`、非 UTF-8、主文件为空 |
| 401 | `10002` | API Key 无效或缺失 | 未传有效 `X-API-Key` 或 Bearer Token |
| 500 | `20001` | 模型调用失败重试耗尽 | 可重试的模型调用错误最终失败 |
| 504 | `20002` | 模型调用超时 | 模型调用超时 |
| 500 | `20003` | 模型输出格式异常 | 非 JSON、JSON 解析失败、缺少必填字段或字段结构不合法 |
| 500 | `29999` | 内部错误 | 未捕获异常 |

### 6.1 模型长度问题的特殊行为

模型输入过长或输出被截断时，服务不会返回 HTTP 错误，而是返回 HTTP `200`、`code=0`，把问题放入业务检查项：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "overall_result": "BLOCK",
    "check_time": "2026-08-03T14:30:00",
    "checks": [
      {
        "id": "模型上下文长度",
        "name": "模型上下文长度",
        "result": "FAIL",
        "block_level": "硬阻断",
        "reason": "B-1-附件一内容过长，超过模型单次处理长度限制，请拆分该部分内容或减少单次上传内容后重试"
      }
    ],
    "metrics": []
  },
  "traceId": "legacy-test-001",
  "duration_seconds": 0.321
}
```

合同系统应同时检查 HTTP 状态码和 `data.overall_result`，不能只按 HTTP `200` 判断评审成功。

## 7. 处理边界

接口收到请求后会同步执行：

1. 从主合同 Markdown 中识别正文内嵌附件；
2. 提取合同首页、签约方、签章、金额、付款、份数和附件声明；
3. 查询签署地预设值服务以识别我方主体；
4. 执行序号 1、2、3、7、8、9、10、11、12；
5. 执行 B-1 称谓一致性和 B-4 附件内容一致性；
6. 汇总为同步 JSON 结果。

合同系统临时测试工程应把每次请求的完整输入、响应、`traceId` 和自身业务测试编号保存到自己的测试记录中。

## 8. 最小联调验收

建议至少验证以下场景：

1. JSON 入口仅传主合同，返回 HTTP 200 且 `code=0`。
2. JSON 入口传一个带文本附件，响应 `checks[]` 中出现附件相关检查结果。
3. multipart 入口上传主合同 `.md` 和两个附件 `.md`，服务能正常返回。
4. 缺少 JSON `contract_md`，返回 HTTP 422、`code=10001`。
5. multipart 主合同使用 `.txt`，返回 HTTP 400、`code=10001`。
6. multipart 主合同使用非 UTF-8 编码，返回 HTTP 400、`code=10001`。
7. 在服务开启鉴权时不传 API Key，返回 HTTP 401、`code=10002`；本地未配置 API Key 白名单时则应正常进入业务处理。
8. 识别到模型上下文过长时，确认 HTTP 仍为 200，但 `data.overall_result=BLOCK` 且检查项为 `模型上下文长度`。
9. 确认合同系统不会把同一 `id` 的多条 `checks[]` 记录覆盖成一条。


