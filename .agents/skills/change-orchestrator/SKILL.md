---
name: change-orchestrator
description: 两阶段变更编排（Explore -> Propose），用于先讨论再立项；Skill 负责决策与文档，脚本负责执行命令。
---

# Change Orchestrator Skill

## 适用场景

当用户提出“新变更”且希望按统一流程推进时，使用本 Skill。

核心理念：
- Skill 作为大脑：澄清需求、判定是否立项、生成规范文本。
- 脚本作为手脚：执行 openspec 命令、生成骨架、校验与状态汇总。

## 两阶段流程

### 1) Explore（先讨论，不立刻建 change）

输入最少信息：
- 变更一句话
- 预期影响对象（调用方/内部实现）
- 风险顾虑

输出固定决策卡：
- `should_create_change`: yes/no
- `impact_level`: tiny/small/major
- `reason`: 为什么
- `recommended_path`: quick-fix / openspec
- `acceptance_hint`: 最小验收条件

判定规则（任一满足建议 yes）：
- 调用方可见行为变化（返回字段、文案、错误语义、阻断规则）。
- 跨模块变更或影响 2+ 文件并需要回归。
- 需要可审计追踪（规范、计划、验收链路）。

### 2) Propose（确认立项后执行）

执行顺序：
1. `openspec new change <name>`
2. 生成/完善：proposal、specs、tasks（design 按需）
3. 同步 superpowers plan（实施步骤+验证命令）
4. `openspec validate <name> --strict`

## 与脚本配合

使用脚本：`scripts/change_orchestrator.ps1`

- `explore` 模式：输出决策卡（不改仓库）。
- `propose` 模式：创建 change 骨架并输出待补全文档清单。
- `validate` 模式：执行 OpenSpec 严格校验并汇总 git 变更。

## 交互约定

当用户说“按默认流程走”时：
1. 默认先运行 explore。
2. 若 `should_create_change=yes`，再询问 change 名称并进入 propose。
3. 结束时输出：
   - 已完成清单
   - 下一步一键命令

## 输出模板

### Explore 决策卡

```text
Decision Card
- should_create_change: yes
- impact_level: small
- reason: 调用方可见文案变化，属于接口语义变更
- recommended_path: openspec
- acceptance_hint: proposal/spec/tasks + validate 通过
```

### Propose 完成回执

```text
Propose Initialized
- change: <name>
- created: proposal.md, tasks.md, specs/<capability>/spec.md
- optional: design.md (if needed)
- next: openspec validate <name> --strict
```
