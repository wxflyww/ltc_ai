## 1. 领域模型

- [x] 1.1 在独立测试目录中为来源快照判别联合、唯一文档键、事实状态、证据定位和可选字段省略编写失败测试
- [x] 1.2 实现 `two_stage/schemas.py` 及公开导出，使领域模型测试通过

## 2. 确定性摘要

- [x] 2.1 为 Markdown 规范化、文件名规范化、确定性 JSON、内容摘要、文档集合排序和上下文摘要编写固定测试向量并验证失败
- [x] 2.2 实现 `two_stage/hashing.py`，使摘要契约测试通过

## 3. 上下文校验

- [x] 3.1 为不支持的 Schema、文档集合被修改、上下文被修改、证据指向快照外文档和合同版本不一致编写失败测试
- [x] 3.2 实现领域异常和 `validate_review_context`，使摘要、证据来源关联和版本校验测试通过

## 4. 集成与验证

- [x] 4.1 更新 `pyproject.toml` 打包清单，并确认新模块不注册 API、不依赖旧流水线
- [x] 4.2 运行两阶段定点测试、现有合同评审回归测试和全量测试
- [x] 4.3 更新实施计划执行状态，运行 `openspec.cmd validate contract-review-context-foundation --strict` 和 `git diff --check`
