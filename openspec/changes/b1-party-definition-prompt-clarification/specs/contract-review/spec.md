## MODIFIED Requirements

### Requirement: B-1 observations require verifiable party evidence

The system SHALL emit a B-1 WARN/FAIL only for a party inconsistency independently verifiable from the current scope evidence.

#### Scenario: attachment label maps to the matching party

- WHEN an attachment defines a role as `项目单位（以下简称甲方）：<header party name>` or an equivalent form
- THEN the system SHALL compare the actual entity after the role mapping with the header baseline
- AND SHALL ignore the leading business label such as `项目单位` or `施工单位`
- AND SHALL emit PASS

#### Scenario: explicit attachment definition differs

- WHEN an attachment explicitly defines a role as an entity outside the header legal-name-and-alias set
- THEN the system SHALL emit WARN or FAIL
- AND the reason SHALL identify the actual defined entity

#### Scenario: model mislabels non-party context

- WHEN the model labels a department, business center, brand, project team, product, system, vehicle model, or project as `party_appellation`
- THEN the system SHALL discard the observation and emit PASS
- AND SHALL not depend on a company-specific sample blacklist