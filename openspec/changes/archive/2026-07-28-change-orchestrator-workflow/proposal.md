## Why

当前仓库已经引入了 OpenSpec 与 Superpowers，但缺少统一入口来支持“先讨论、再立项、再执行”的稳定流程。实际协作中容易出现以下问题：

- 直接改代码后才补规范，导致变更边界不清晰；
- 不同入口文档描述不一致（README、AGENTS、CLAUDE）；
- 每次手工执行命令步骤不一致，容易漏掉 validate。

需要将“Skill 作为大脑 + 脚本作为手脚”的混合编排流程明确为团队标准能力。

## What Changes

- 新增两阶段编排能力：Explore -> Propose。
- 定义 Explore 决策卡输出，统一“是否创建 change”的判定口径。
- 新增编排脚本入口，固化 explore/propose/validate 常用命令。
- 同步主入口文档（README、AGENTS、CLAUDE）和 Superpowers playbook，确保描述一致。
- 将本能力纳入 OpenSpec change，形成可追踪规范记录。

## Capabilities

### New Capabilities
- `change-orchestration`: 规范“先探索再立项”的编排流程，提供决策与执行双层机制。

### Modified Capabilities
- 无。

## Impact

- 新增文件：
  - `.agents/skills/change-orchestrator/SKILL.md`
  - `scripts/change_orchestrator.ps1`
  - `docs/superpowers/playbooks/change-orchestrator.md`
  - `openspec/changes/change-orchestrator-workflow/*`
- 更新文件：
  - `README.md`
  - `AGENTS.md`
  - `CLAUDE.md`
- 对业务 API 行为无直接影响，仅增强工程流程与文档治理能力。
