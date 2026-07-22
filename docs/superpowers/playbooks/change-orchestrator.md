# 变更编排器使用手册（Skill + Script）

本手册提供一个“先讨论、再立项、再执行”的统一流程。

- Skill 作为大脑：判定与文档策略。
- Script 作为手脚：命令执行与校验输出。

脚本位置：`scripts/change_orchestrator.ps1`
Skill 位置：`.agents/skills/change-orchestrator/SKILL.md`

## 一、Explore（先讨论，不建 change）

```powershell
./scripts/change_orchestrator.ps1 -Mode explore -Title "B-1 reason 文案从范围前缀改为自然语句" -Impact "调用方可见文案变化" -Concern "避免误解为范围字段"
```

输出决策卡：
- should_create_change: yes/no
- impact_level: tiny/small/major
- recommended_path: quick-fix/openspec

## 二、Propose（确认立项后）

```powershell
./scripts/change_orchestrator.ps1 -Mode propose -ChangeName b1-reason-wording -Title "B-1 reason wording" -Capability contract-review
```

脚本会：
- 执行 `openspec.cmd new change <name>`
- 确保存在 proposal/tasks/spec 以及 optional design 骨架
- 输出下一步校验命令

## 三、Validate（提交流程前）

```powershell
./scripts/change_orchestrator.ps1 -Mode validate -ChangeName b1-reason-wording
```

脚本会：
- 执行 `openspec.cmd validate <name> --strict`
- 输出 `openspec/docs/superpowers/scripts/.agents` 相关变更范围

## 四、推荐团队约定

1. 只要是调用方可见行为变化，默认走 OpenSpec change。
2. 先 explore 再 propose，避免“先建后改方向”。
3. design 仅在多方案权衡或架构调整时补齐。
4. 每次完成后都执行 validate。

## 五、与日常协作配合

你可以直接对助手说：

```text
新变更：<一句话>，按默认流程自动执行
```

助手默认动作：
1. 先 explore，给出 should_create_change。
2. 若 yes，进入 propose，生成规范骨架。
3. 同步 superpowers 计划文档并给出下一步命令。
