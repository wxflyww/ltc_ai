# Design: B-1 evidence semantics

Use the existing B-1 structured observation. The backend accepts only conclusions independently verifiable from `evidence_quote`.

## Party definition

For `party_definition`, extract the actual entity after the current role and a colon or “为”. In `项目单位（以下简称甲方）：浙江吉利汽车工程技术开发有限公司`, the actual entity is the full company name, not `项目单位`.

Compare the extracted entity with the header legal name and aliases. Drop a matching observation; report a mismatch using the extracted entity. Drop an observation without an explicit mapping, rather than trusting a model-provided label.

## Party appellation

Keep the existing role, header baseline, scope, evidence, and found-text checks. Add a category-based rejection when the found text itself or its immediate context denotes a department, business center, brand, project team, product, system, vehicle model, or project. Do not blacklist a sample company or brand name.

## Acceptance

- Matching `项目单位（以下简称甲方）：<header party>` and `施工单位（以下简称乙方）：<header party>` result in PASS.
- Department and system observations result in PASS even when the model emits WARN.
- A genuinely different explicit attachment definition and an undefined attachment role remain WARN/FAIL.
- Existing B-1 three-item budget and B-4 behavior remain unchanged.