## 1. Schema 约束

- [x] 1.1 B-1 checks 添加 maxItems=3，result 枚举收紧为 WARN/FAIL，字符串字段添加 maxLength。
- [x] 1.2 B-4 checks 添加 maxItems=3，result 枚举收紧为 WARN/FAIL，字符串字段添加 maxLength。

## 2. Prompt 约束

- [x] 2.1 B-1 prompt 增加最多 3 条、只输出 WARN/FAIL、排序去重规则，明确排除部门/品牌/项目团队/产品/系统等非签约主体称谓。
- [x] 2.2 B-4 prompt 增加最多 3 条、只输出 WARN/FAIL、无问题返回空 checks。

## 3. 服务端防御

- [x] 3.1 B-1 结构化观察处理增加确定性排序（FAIL 优先）+ 去重 + 截取前 3 条。
- [x] 3.2 B-4 结果处理增加确定性排序 + 去重 + 截取前 3 条。

## 4. 测试

- [x] 4.1 Schema 测试：B-1/B-4 maxItems、result enum、maxLength。
- [x] 4.2 Prompt 测试：最多 3 条、只输出 WARN/FAIL、排序去重、非签约主体排除。
- [x] 4.3 B-1 回归：正确通过、附件角色未定义、主体不一致、部门品牌不触发、多问题最多 3 条。
- [x] 4.4 B-4 回归：无证据不臆造、附件证据校验、多问题最多 3 条、无问题 PASS。
- [x] 4.5 防御性：超 3 条确定性截取、重复不占名额、格式异常不静默 PASS。
- [x] 4.6 非目标回归：attachment_title_matching 完整性、A-1a/A-3/A-4 不受影响、诊断日志测试通过。

## 5. 验证

- [x] 5.1 运行受影响范围测试、全量测试、git diff --check、openspec validate --strict。
