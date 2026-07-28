"""B-1/B-4 输出预算治理测试：Schema、Prompt、服务端防御。"""
from unittest.mock import patch

import pytest

from app.capabilities.contract_review.response_formats import RESPONSE_FORMATS
from app.capabilities.contract_review.prompts import build_prompt
from app.capabilities.contract_review.service import (
    _finalize_structured_b1_observations,
    _finalize_b4_items,
    _run_b1,
    _run_b4,
)
from app.core.errors import ModelFormatError


# ---------------------------------------------------------------------------
# 1. B-1 Schema 约束
# ---------------------------------------------------------------------------

class TestB1SchemaBudget:
    def setup_method(self):
        self.schema = RESPONSE_FORMATS["b1_appellation"]["json_schema"]["schema"]
        self.checks = self.schema["properties"]["checks"]
        self.item_props = self.checks["items"]["properties"]

    def test_b1_checks_max_items_is_3(self):
        assert self.checks.get("maxItems") == 3

    def test_b1_checks_result_only_warn_fail(self):
        result_enum = self.item_props["result"]["enum"]
        assert set(result_enum) == {"WARN", "FAIL"}

    def test_b1_empty_checks_is_valid(self):
        # maxItems=3 允许 0 条
        assert self.checks.get("maxItems") == 3
        assert "minItems" not in self.checks or self.checks["minItems"] == 0

    def test_b1_string_fields_have_max_length(self):
        assert self.item_props["role"].get("maxLength") == 20
        assert self.item_props["baseline_appellation"].get("maxLength") == 100
        assert self.item_props["found_appellation"].get("maxLength") == 100
        assert self.item_props["evidence_quote"].get("maxLength") == 200


# ---------------------------------------------------------------------------
# 2. B-4 Schema 约束
# ---------------------------------------------------------------------------

class TestB4SchemaBudget:
    def setup_method(self):
        self.schema = RESPONSE_FORMATS["b4_attachment_content"]["json_schema"]["schema"]
        self.checks = self.schema["properties"]["checks"]
        self.item_props = self.checks["items"]["properties"]

    def test_b4_checks_max_items_is_3(self):
        assert self.checks.get("maxItems") == 3

    def test_b4_checks_result_only_warn_fail(self):
        result_enum = self.item_props["result"]["enum"]
        assert set(result_enum) == {"WARN", "FAIL"}

    def test_b4_empty_checks_is_valid(self):
        assert self.checks.get("maxItems") == 3
        assert "minItems" not in self.checks or self.checks["minItems"] == 0

    def test_b4_string_fields_have_max_length(self):
        assert self.item_props["attachment_evidence"].get("maxLength") == 200
        assert self.item_props["reason"].get("maxLength") == 200


# ---------------------------------------------------------------------------
# 3. Prompt 约束
# ---------------------------------------------------------------------------

class TestPromptBudget:
    def test_b1_prompt_requires_max_3_checks(self):
        messages = build_prompt(
            "b1_appellation",
            parties=[],
            scope_label="合同正文",
            segment_text="合同内容",
        )
        content = messages[1].content
        assert "最多" in content and "3" in content

    def test_b1_prompt_only_warn_fail(self):
        messages = build_prompt(
            "b1_appellation",
            parties=[],
            scope_label="合同正文",
            segment_text="合同内容",
        )
        content = messages[1].content
        assert "WARN" in content and "FAIL" in content
        assert "空" in content or "[]" in content

    def test_b1_prompt_sort_and_dedup(self):
        messages = build_prompt(
            "b1_appellation",
            parties=[],
            scope_label="合同正文",
            segment_text="合同内容",
        )
        content = messages[1].content
        assert "FAIL" in content
        assert "排序" in content or "优先" in content
        assert "去重" in content or "重复" in content

    def test_b1_prompt_excludes_non_party_appellations(self):
        messages = build_prompt(
            "b1_appellation",
            parties=[],
            scope_label="合同正文",
            segment_text="合同内容",
        )
        content = messages[1].content
        assert "部门" in content
        assert "品牌" in content
        assert "项目团队" in content or "团队" in content
        assert "产品" in content
        assert "系统" in content

    def test_b4_prompt_requires_max_3_checks(self):
        messages = build_prompt(
            "b4_attachment_content",
            baseline={},
            attachment_text="附件内容",
        )
        content = messages[1].content
        assert "最多" in content and "3" in content

    def test_b4_prompt_only_warn_fail_and_empty_checks(self):
        messages = build_prompt(
            "b4_attachment_content",
            baseline={},
            attachment_text="附件内容",
        )
        content = messages[1].content
        assert "WARN" in content and "FAIL" in content
        assert "空" in content or "[]" in content


# ---------------------------------------------------------------------------
# 4. B-1 回归
# ---------------------------------------------------------------------------

class TestB1Regression:
    def test_b1_correct_party_definition_passes(self):
        outputs = ['{"checks":[]}']

        def fake_invoke(model, messages, response_format=None):
            return outputs.pop(0), {"total_tokens": 1}

        with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
            with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
                items = _run_b1(
                    "甲方：客户公司\n乙方：我方公司",
                    [],
                    [{"role": "甲方", "name": "客户公司", "aliases": []}],
                )

        assert items[0].result == "PASS"
        assert items[0].reason is None

    def test_b1_attachment_role_without_definition_warns(self):
        outputs = [
            '{"checks":[]}',
            '{"checks":[{"result":"WARN","block_level":"提示","role":"乙方","baseline_appellation":"我方公司","found_appellation":null,"evidence_quote":"乙方应按约定交付。","evidence_type":"role_without_definition"}]}',
        ]

        def fake_invoke(model, messages, response_format=None):
            return outputs.pop(0), {"total_tokens": 1}

        with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
            with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
                items = _run_b1(
                    "合同正文",
                    [{"title": "附件1", "text": "乙方应按约定交付。"}],
                    [{"role": "乙方", "name": "我方公司", "aliases": []}],
                )

        attachment_item = next(item for item in items if "附件1" in item.name)
        assert attachment_item.result == "WARN"

    def test_b1_department_brand_does_not_trigger_warn(self):
        """吉利座舱中心、吉利等作为部门/品牌出现时，Prompt 约束模型不输出 WARN。

        本测试验证：当模型遵循 Prompt 约束返回空 checks 时，服务端生成 PASS。
        部门/品牌的语义识别主要依靠 Prompt 约束，而非服务端黑名单。
        """
        # 模型遵循 Prompt 约束，识别出"吉利座舱中心"是部门而非签约方，返回空 checks
        outputs = ['{"checks":[]}']

        def fake_invoke(model, messages, response_format=None):
            return outputs.pop(0), {"total_tokens": 1}

        with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
            with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
                items = _run_b1(
                    "吉利座舱中心负责本次项目开发。",
                    [],
                    [{"role": "甲方", "name": "吉利控股集团", "aliases": []}],
                )

        assert items[0].result == "PASS"
        assert items[0].reason is None

    def test_b1_prompt_excludes_department_brand_semantically(self):
        """验证 Prompt 明确排除部门/品牌/项目团队/产品/系统。"""
        messages = build_prompt(
            "b1_appellation",
            parties=[{"role": "甲方", "name": "吉利控股集团", "aliases": []}],
            scope_label="合同正文",
            segment_text="吉利座舱中心负责本次项目开发。",
        )
        content = messages[1].content
        # Prompt 必须明确排除这些非签约主体称谓
        assert "部门" in content
        assert "品牌" in content
        assert "产品" in content
        assert "系统" in content
        # Prompt 必须说明只有指代签约方才输出 WARN
        assert "指代" in content or "权利义务" in content

    def test_b1_multiple_issues_max_3_stable_order(self):
        """多个不同真实问题时，最终最多 3 条且 FAIL 优先。"""
        outputs = [
            '{"checks":['
            '{"result":"WARN","block_level":"提示","role":"甲方","baseline_appellation":"客户公司","found_appellation":"客户","evidence_quote":"客户应付款。","evidence_type":"party_appellation"},'
            '{"result":"FAIL","block_level":"硬阻断","role":"乙方","baseline_appellation":"我方公司","found_appellation":"供应商X","evidence_quote":"供应商X应交付。","evidence_type":"party_appellation"},'
            '{"result":"WARN","block_level":"提示","role":"甲方","baseline_appellation":"客户公司","found_appellation":"甲方公司","evidence_quote":"甲方公司确认。","evidence_type":"party_appellation"},'
            '{"result":"WARN","block_level":"提示","role":"乙方","baseline_appellation":"我方公司","found_appellation":"乙方公司","evidence_quote":"乙方公司同意。","evidence_type":"party_appellation"}'
            ']}',
        ]

        def fake_invoke(model, messages, response_format=None):
            return outputs.pop(0), {"total_tokens": 1}

        with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
            with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
                items = _run_b1(
                    "客户应付款。供应商X应交付。甲方公司确认。乙方公司同意。",
                    [],
                    [
                        {"role": "甲方", "name": "客户公司", "aliases": []},
                        {"role": "乙方", "name": "我方公司", "aliases": []},
                    ],
                )

        warn_fail_items = [item for item in items if item.result in {"WARN", "FAIL"}]
        assert len(warn_fail_items) <= 3
        # FAIL 应排在 WARN 前面
        if len(warn_fail_items) >= 2:
            fail_indices = [i for i, item in enumerate(warn_fail_items) if item.result == "FAIL"]
            warn_indices = [i for i, item in enumerate(warn_fail_items) if item.result == "WARN"]
            if fail_indices and warn_indices:
                assert max(fail_indices) < min(warn_indices)

    def test_b1_pass_reason_is_null(self):
        outputs = ['{"checks":[]}']

        def fake_invoke(model, messages, response_format=None):
            return outputs.pop(0), {"total_tokens": 1}

        with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
            with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
                items = _run_b1("合同正文", [], [])

        assert items[0].result == "PASS"
        assert items[0].reason is None


# ---------------------------------------------------------------------------
# 5. B-4 回归
# ---------------------------------------------------------------------------

class TestB4Regression:
    def test_b4_no_evidence_no_fabrication(self):
        """合同正文金额没有可核验证据时，不得臆造金额差异。"""
        outputs = [
            '{"checks":[{"result":"FAIL","block_level":"硬阻断","check_type":"total_amount","attachment_value":100,"attachment_evidence":"附件总价100元。","reason":null}]}'
        ]

        def fake_invoke(model, messages, response_format=None):
            return outputs.pop(0), {"total_tokens": 1}

        with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
            with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
                items = _run_b4(
                    [{"title": "附件1", "text": "附件总价100元。"}],
                    {},  # 无 amount_payment baseline
                )

        assert items[0].result == "PASS"

    def test_b4_attachment_evidence_must_be_from_current_attachment(self):
        outputs = [
            '{"checks":[{"result":"FAIL","block_level":"硬阻断","check_type":"total_amount","attachment_value":200,"attachment_evidence":"其他附件总价200元。","reason":null}]}'
        ]

        def fake_invoke(model, messages, response_format=None):
            return outputs.pop(0), {"total_tokens": 1}

        with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
            with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
                items = _run_b4(
                    [{"title": "附件1", "text": "附件总价100元。"}],
                    {"amount_payment": {"total_amount_numeric": "100", "total_amount_evidence": "合同总价100元。"}},
                )

        assert items[0].result == "PASS"

    def test_b4_multiple_issues_max_3(self):
        """多个不同真实问题时最多 3 条。"""
        outputs = [
            '{"checks":['
            '{"result":"FAIL","block_level":"硬阻断","check_type":"total_amount","attachment_value":200,"attachment_evidence":"附件总价200元。","reason":null},'
            '{"result":"WARN","block_level":"提示","check_type":"other","attachment_value":null,"attachment_evidence":null,"reason":"问题1"},'
            '{"result":"WARN","block_level":"提示","check_type":"other","attachment_value":null,"attachment_evidence":null,"reason":"问题2"},'
            '{"result":"WARN","block_level":"提示","check_type":"other","attachment_value":null,"attachment_evidence":null,"reason":"问题3"}'
            ']}'
        ]

        def fake_invoke(model, messages, response_format=None):
            return outputs.pop(0), {"total_tokens": 1}

        with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
            with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
                items = _run_b4(
                    [{"title": "附件1", "text": "附件总价200元。"}],
                    {"amount_payment": {"total_amount_numeric": "100", "total_amount_evidence": "合同总价100元。"}},
                )

        warn_fail_items = [item for item in items if item.result in {"WARN", "FAIL"}]
        assert len(warn_fail_items) <= 3

    def test_b4_no_issues_generates_pass_with_null_reason(self):
        outputs = ['{"checks":[]}']

        def fake_invoke(model, messages, response_format=None):
            return outputs.pop(0), {"total_tokens": 1}

        with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
            with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
                items = _run_b4([{"title": "附件1", "text": "附件内容"}], {})

        assert items[0].result == "PASS"
        assert items[0].reason is None


# ---------------------------------------------------------------------------
# 6. 防御性行为
# ---------------------------------------------------------------------------

class TestDefensiveBehavior:
    def test_b1_over_3_items_deterministic_truncation(self):
        """模拟供应端返回超过 3 条，验证服务端行为确定且符合设计。"""
        parties = [{"role": "甲方", "name": "客户公司", "aliases": []}]
        payload = {
            "checks": [
                {"result": "WARN", "block_level": "提示", "role": "甲方", "baseline_appellation": "客户公司", "found_appellation": f"称谓{i}", "evidence_quote": f"称谓{i}应付款。", "evidence_type": "party_appellation"}
                for i in range(5)
            ]
        }
        segment_text = "。".join(f"称谓{i}应付款" for i in range(5)) + "。"

        items = _finalize_structured_b1_observations(payload, "合同正文", segment_text, parties)

        warn_fail_items = [item for item in items if item.result in {"WARN", "FAIL"}]
        assert len(warn_fail_items) <= 3

    def test_b1_duplicates_do_not_fill_slots(self):
        """重复发现不会占满 3 个名额。"""
        parties = [{"role": "甲方", "name": "客户公司", "aliases": []}]
        payload = {
            "checks": [
                {"result": "WARN", "block_level": "提示", "role": "甲方", "baseline_appellation": "客户公司", "found_appellation": "客户", "evidence_quote": "客户应付款。", "evidence_type": "party_appellation"},
                {"result": "WARN", "block_level": "提示", "role": "甲方", "baseline_appellation": "客户公司", "found_appellation": "客户", "evidence_quote": "客户应付款。", "evidence_type": "party_appellation"},
                {"result": "WARN", "block_level": "提示", "role": "甲方", "baseline_appellation": "客户公司", "found_appellation": "甲方公司", "evidence_quote": "甲方公司确认。", "evidence_type": "party_appellation"},
            ]
        }
        segment_text = "客户应付款。甲方公司确认。"

        items = _finalize_structured_b1_observations(payload, "合同正文", segment_text, parties)

        warn_items = [item for item in items if item.result == "WARN"]
        # 去重后应有 2 条不同的 WARN
        assert len(warn_items) == 2

    def test_b1_format_error_not_silently_pass(self):
        """不能把模型格式异常静默转为 PASS。"""
        payload = {"checks": ["not_a_dict"]}

        with pytest.raises(ModelFormatError):
            _finalize_structured_b1_observations(payload, "合同正文", "合同内容", [])

    def test_b4_over_3_items_deterministic_truncation(self):
        """B-4 模拟超过 3 条，验证确定性截取。"""
        payload = {
            "checks": [
                {"result": "WARN", "block_level": "提示", "check_type": "other", "attachment_value": None, "attachment_evidence": None, "reason": f"问题{i}"}
                for i in range(5)
            ]
        }

        items = _finalize_b4_items(payload, "附件1", "附件内容", {})

        warn_fail_items = [item for item in items if item.result in {"WARN", "FAIL"}]
        assert len(warn_fail_items) <= 3

    def test_b4_fail_priority_over_warn(self):
        """B-4 FAIL 优先于 WARN。"""
        payload = {
            "checks": [
                {"result": "WARN", "block_level": "提示", "check_type": "other", "attachment_value": None, "attachment_evidence": None, "reason": "警告1"},
                {"result": "WARN", "block_level": "提示", "check_type": "other", "attachment_value": None, "attachment_evidence": None, "reason": "警告2"},
                {"result": "WARN", "block_level": "提示", "check_type": "other", "attachment_value": None, "attachment_evidence": None, "reason": "警告3"},
                {"result": "FAIL", "block_level": "硬阻断", "check_type": "other", "attachment_value": None, "attachment_evidence": None, "reason": "阻断1"},
            ]
        }

        items = _finalize_b4_items(payload, "附件1", "附件内容", {})

        warn_fail_items = [item for item in items if item.result in {"WARN", "FAIL"}]
        assert len(warn_fail_items) <= 3
        # FAIL 应在前面
        if warn_fail_items:
            assert warn_fail_items[0].result == "FAIL"


# ---------------------------------------------------------------------------
# 7. 非目标能力回归
# ---------------------------------------------------------------------------

class TestNonTargetRegression:
    def test_attachment_title_matching_schema_unchanged(self):
        """attachment_title_matching 仍为每个上传附件返回 decision，不受 checks 限制。"""
        schema = RESPONSE_FORMATS["attachment_title_matching"]["json_schema"]["schema"]
        decisions = schema["properties"]["decisions"]
        # 不应有 maxItems=3
        assert decisions.get("maxItems") != 3
        # judgement 仍包含 MATCH
        assert "MATCH" in decisions["items"]["properties"]["judgement"]["enum"]

    def test_a1a_extraction_schema_unchanged(self):
        """A-1a 提取行为不因 checks 限制受到破坏。"""
        schema = RESPONSE_FORMATS["a1a_party_extraction"]["json_schema"]["schema"]
        # parties 不应有 maxItems=3
        parties = schema["properties"]["header"]["properties"]["parties"]
        assert parties.get("maxItems") != 3
        # sections 不应有 maxItems=3
        sections = schema["properties"]["sections"]
        assert sections.get("maxItems") != 3

    def test_a3_extraction_schema_unchanged(self):
        """A-3 提取行为不因 checks 限制受到破坏。"""
        schema = RESPONSE_FORMATS["a3_amount_payment"]["json_schema"]["schema"]
        stages = schema["properties"]["payment_stages"]
        assert stages.get("maxItems") != 3

    def test_a4_extraction_schema_unchanged(self):
        """A-4 提取行为不因 checks 限制受到破坏。"""
        schema = RESPONSE_FORMATS["a4_copies_attachments"]["json_schema"]["schema"]
        attachments = schema["properties"]["attachments_declared"]
        assert attachments.get("maxItems") != 3


class TestB1EvidenceVerification:
    def test_matching_labeled_attachment_definition_is_pass(self):
        parties = [
            {"role": "\u7532\u65b9", "name": "\u6d59\u6c5f\u5409\u5229\u6c7d\u8f66\u5de5\u7a0b\u6280\u672f\u5f00\u53d1\u6709\u9650\u516c\u53f8", "aliases": []},
            {"role": "\u4e59\u65b9", "name": "\u4e1c\u8f6f\u96c6\u56e2\uff08\u4e0a\u6d77\uff09\u6709\u9650\u516c\u53f8", "aliases": []},
        ]
        segment = (
            "\u9879\u76ee\u5355\u4f4d\uff08\u4ee5\u4e0b\u7b80\u79f0\u7532\u65b9\uff09\uff1a\u6d59\u6c5f\u5409\u5229\u6c7d\u8f66\u5de5\u7a0b\u6280\u672f\u5f00\u53d1\u6709\u9650\u516c\u53f8\n"
            "\u65bd\u5de5\u5355\u4f4d\uff08\u4ee5\u4e0b\u7b80\u79f0\u4e59\u65b9\uff09\uff1a\u4e1c\u8f6f\u96c6\u56e2\uff08\u4e0a\u6d77\uff09\u6709\u9650\u516c\u53f8"
        )
        payload = {
            "checks": [
                {"result": "WARN", "block_level": "\u63d0\u793a", "role": "\u7532\u65b9", "baseline_appellation": "\u6d59\u6c5f\u5409\u5229\u6c7d\u8f66\u5de5\u7a0b\u6280\u672f\u5f00\u53d1\u6709\u9650\u516c\u53f8", "found_appellation": "\u9879\u76ee\u5355\u4f4d", "evidence_quote": "\u9879\u76ee\u5355\u4f4d\uff08\u4ee5\u4e0b\u7b80\u79f0\u7532\u65b9\uff09\uff1a\u6d59\u6c5f\u5409\u5229\u6c7d\u8f66\u5de5\u7a0b\u6280\u672f\u5f00\u53d1\u6709\u9650\u516c\u53f8", "evidence_type": "party_definition"},
                {"result": "WARN", "block_level": "\u63d0\u793a", "role": "\u4e59\u65b9", "baseline_appellation": "\u4e1c\u8f6f\u96c6\u56e2\uff08\u4e0a\u6d77\uff09\u6709\u9650\u516c\u53f8", "found_appellation": "\u65bd\u5de5\u5355\u4f4d", "evidence_quote": "\u65bd\u5de5\u5355\u4f4d\uff08\u4ee5\u4e0b\u7b80\u79f0\u4e59\u65b9\uff09\uff1a\u4e1c\u8f6f\u96c6\u56e2\uff08\u4e0a\u6d77\uff09\u6709\u9650\u516c\u53f8", "evidence_type": "party_definition"},
            ]
        }

        items = _finalize_structured_b1_observations(payload, "\u9644\u4ef64", segment, parties)

        assert [(item.result, item.reason) for item in items] == [("PASS", None)]

    @pytest.mark.parametrize(
        ("found", "evidence"),
        [
            ("\u5409\u5229\u5ea7\u8231\u4e2d\u5fc3", "\u5409\u5229\u5ea7\u8231\u4e2d\u5fc3\u5404\u6a21\u5757\u8d1f\u8d23\u4eba\u76f4\u63a5\u53c2\u4e0e\u7ba1\u63a7\u548c\u6279\u51c6\u3002"),
            ("\u5409\u5229", "\u9879\u76ee\u5f00\u53d1\u8303\u56f4\u5305\u542b\u6a2a\u5c55\u5409\u5229 Flyme OS \u4e3b\u7ebf\u6700\u65b0\u529f\u80fd\u3002"),
        ],
    )
    def test_non_party_context_is_pass_even_when_model_emits_warn(self, found, evidence):
        parties = [{"role": "\u7532\u65b9", "name": "\u6d59\u6c5f\u5409\u5229\u6c7d\u8f66\u5de5\u7a0b\u6280\u672f\u5f00\u53d1\u6709\u9650\u516c\u53f8", "aliases": []}]
        payload = {
            "checks": [
                {"result": "WARN", "block_level": "\u63d0\u793a", "role": "\u7532\u65b9", "baseline_appellation": "\u6d59\u6c5f\u5409\u5229\u6c7d\u8f66\u5de5\u7a0b\u6280\u672f\u5f00\u53d1\u6709\u9650\u516c\u53f8", "found_appellation": found, "evidence_quote": evidence, "evidence_type": "party_appellation"},
            ]
        }

        items = _finalize_structured_b1_observations(payload, "\u9644\u4ef62", evidence, parties)

        assert [(item.result, item.reason) for item in items] == [("PASS", None)]
