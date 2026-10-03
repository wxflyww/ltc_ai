# Design — review-summary-api

> 可选工件。仅记录立项过程中的方案权衡与实现收口决策；产品契约、输入输出字段与规则的完整定义以 `docs/integration/2026-10-02-review-summary-design.md` 为唯一事实源，不在此重复。

## D1 整包输出 vs 只出 AI 部分（已拍板：整包）

- 接口交付物 = 「评审智能总结」面板这个产品，而非裸模型能力；响应含原文装配字段，合同系统可整包渲染，也可对自有组件覆盖的模块忽略对应字段。
- 理由：① AI 总述本就需全量输入上下文，"传进来"省不掉，整包只多回传一步、代价≈0；② 空态矩阵、事实单点归属、source_refs 校验等展示规则归接口侧单一实现；③ 缓存与溯源以整包为单位最简单；④ 避免双数据源时序问题（原文即时、AI 数秒）。

## D2 spec 归挂方式（已拍板：新 capability `review-summary`）

- 本仓此前只有 `contract-review` 一个 capability。归挂进 `contract-review` 会与其"整包冻结"红线自相矛盾，且违反能力间零依赖的架构约定。
- 决策：delta spec 落 `specs/review-summary/spec.md`（全 ADDED），archive 后提升为 `openspec/specs/review-summary/`，本仓正式第二个 capability。

## D3 配置与依赖一期零改动

- 超时、模型参数等一期硬编码默认值，不新增 `config/*.yaml` 键；不新增第三方依赖（hash 用标准库、缓存用进程内实现）；不动 `tests/conftest.py`。
- 缓存为一期进程内内存实现（输入 hash → 响应体），无持久化组件；多副本部署下各自命中，正确性不受影响（输入 hash 即版本键）。

## D4 source_refs 校验失败的兜底（实现收口）

- 设计 §2.3 第 3 条只规定"无引用或引用悬空的结论直接丢弃"。收口：校验失败的 AI 结论（总述句/单条意见摘要）SHALL NOT 出现在响应中；丢弃不阻塞装配区返回。
- 意见摘要被丢弃时该条 `summary` 输出 `null`，前端可回落展示 `comment` 原文截断；总述被丢弃时 `review_summary.text` 输出 `null`。两者 SHALL 在 `degraded_sections` 标记（`review_summary.model` / `opinion_details.model`），与设计既有标记风格一致。

## D5 服务端超时与耗时预算

- 生成规模小于现行评审接口逐项检查，服务端超时建议 120s 口径；实测预期缓存命中 <100ms、新生成 3–10s。真实端点耗时联调不作为首版验收前置条件（沿用 `DEC-LTC-20261001-001` 的最小完整链路验收精神），登记为上线前补验。
