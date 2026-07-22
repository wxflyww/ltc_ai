# 变更编排器设计说明（Skill + Script）

## 背景

团队协作存在“先改后补文档”与“入口描述不一致”的问题，需要将变更治理流程产品化。

## 设计原则

1. 先探索后立项
- 通过 Explore 输出决策卡，明确是否创建 OpenSpec change。

2. 决策与执行分层
- Skill 负责理解与判定。
- Script 负责执行与校验。

3. 入口一致
- 在 README、AGENTS、CLAUDE、playbook 中给出相同命令与约定。

## 关键能力

### Explore

输入：`Title`、`Impact`、`Concern`

输出：
- `should_create_change`
- `impact_level`
- `reason`
- `recommended_path`
- `acceptance_hint`

### Propose

行为：
- 调用 `openspec new change <name>`
- 补齐 proposal/tasks/spec（design 可选）骨架
- 输出下一步 validate 命令

### Validate

行为：
- 调用 `openspec validate <name> --strict`
- 输出文档与脚本相关变更范围

## 非目标

- 不处理业务代码改动本身。
- 不替代 OpenSpec 的规范语义定义。
