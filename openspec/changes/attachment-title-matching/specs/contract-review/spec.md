## MODIFIED Requirements

### Requirement: 附件数量和标题一致性

系统 SHALL 对合同正文声明附件和实际上传附件进行数量/标题检查，并以确定性规范化和私有化模型语义判断建立附件标题关联。

#### Scenario: 合同声明附件数量多于实际上传附件

- WHEN 合同声明附件 3 份
- AND 实际上传附件 2 份
- THEN 系统 SHALL 输出 FAIL

#### Scenario: 格式差异后的标题唯一完全一致

- WHEN 声明标题和上传文件名去除路径、扩展名、明确附件序号前缀及格式符号后唯一完全一致
- THEN 系统 SHALL 将两者关联
- AND 系统 SHALL 不因该名称差异输出标题未匹配提示

#### Scenario: 私有化模型确认语义同一

- WHEN 规范化后仍存在未匹配的声明附件和上传附件
- AND 私有化模型返回经后端校验的一对一 `MATCH` 映射
- THEN 系统 SHALL 将该映射关联为同一附件

#### Scenario: 语义判断无法唯一确认

- WHEN 私有化模型返回 `UNCERTAIN`、`MISMATCH` 或无效的一对一映射
- THEN 系统 SHALL 不建立该附件标题关联
- AND 系统 SHALL 输出提示，请业务确认附件对应关系

#### Scenario: 未匹配附件仍参与内容检查

- WHEN 实际附件未匹配到合同声明附件
- THEN 系统 SHALL 仍将该附件进入 B-4 内容检查