## ADDED Requirements

### Requirement: 变更编排流程必须先探索再立项
系统 SHALL 提供 Explore 与 Propose 两阶段流程，确保在创建 OpenSpec change 前先完成问题澄清与立项判断。

#### Scenario: Explore 输出决策卡
- **WHEN** 用户提出一个新变更并要求按默认流程推进
- **THEN** 系统 SHALL 输出包含 `should_create_change`、`impact_level`、`reason`、`recommended_path`、`acceptance_hint` 的决策卡

#### Scenario: Explore 判定为需要立项
- **WHEN** Explore 判定 `should_create_change=yes`
- **THEN** 系统 SHALL 推荐进入 OpenSpec propose 流程而不是直接修改代码

### Requirement: 编排脚本必须提供标准执行入口
系统 SHALL 提供可重复执行的脚本命令，用于 explore、propose、validate 三种动作。

#### Scenario: 运行 explore 命令
- **WHEN** 执行 `scripts/change_orchestrator.ps1 -Mode explore ...`
- **THEN** 系统 SHALL 输出决策卡且不修改仓库文件

#### Scenario: 运行 propose 命令
- **WHEN** 执行 `scripts/change_orchestrator.ps1 -Mode propose ...`
- **THEN** 系统 SHALL 创建 change 骨架并输出后续待补全文档清单

#### Scenario: 运行 validate 命令
- **WHEN** 执行 `scripts/change_orchestrator.ps1 -Mode validate -ChangeName <name>`
- **THEN** 系统 SHALL 执行 `openspec validate <name> --strict` 并输出文档/脚本相关变更范围

### Requirement: 入口文档必须保持流程一致性
系统 SHALL 在 README、AGENTS、CLAUDE 与 Superpowers playbook 中对同一编排流程给出一致描述。

#### Scenario: 主入口文档可发现编排流程
- **WHEN** 维护者阅读 README 或 AGENTS 或 CLAUDE
- **THEN** 系统 SHALL 提供统一的编排器位置、命令示例与执行约定
