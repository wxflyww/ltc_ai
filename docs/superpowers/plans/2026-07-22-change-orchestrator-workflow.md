# 变更编排器（Skill + Script）落地计划

## 目标

把“先讨论、再立项、再执行”的协作流程沉淀为可复用能力，降低变更过程中的漏项与歧义。

## 交付范围

- `.agents/skills/change-orchestrator/SKILL.md`
- `scripts/change_orchestrator.ps1`
- `docs/superpowers/playbooks/change-orchestrator.md`
- `README.md` / `AGENTS.md` / `CLAUDE.md` 同步入口
- `openspec/changes/change-orchestrator-workflow/*` 规范工件

## 执行步骤

- [x] 新建 Skill 文档，定义 Explore -> Propose 两阶段
- [x] 新建脚本，提供 `explore/propose/validate` 三模式
- [x] 新建 playbook，补齐团队使用手册
- [x] 同步 README 入口
- [x] 同步 AGENTS 与 CLAUDE
- [ ] 运行 OpenSpec validate
- [ ] 输出最终变更范围与下一步建议

## 验证命令

```powershell
./scripts/change_orchestrator.ps1 -Mode explore -Title "B-1 reason wording" -Impact "api message wording" -Concern "avoid ambiguity"
openspec.cmd validate change-orchestrator-workflow --strict
git status --short README.md AGENTS.md CLAUDE.md .agents scripts docs/superpowers openspec/changes/change-orchestrator-workflow
```
