import pytest

from app.capabilities.contract_review.prefill_prompts import normalize_contract_text


def test_normalize_single_line_with_literal_backslash_n():
    raw = "第一条 总则\\n第二条 付款方式\\n（一）合同签订后支付30%"
    assert normalize_contract_text(raw) == "第一条 总则\n第二条 付款方式\n（一）合同签订后支付30%"


def test_normalize_keeps_text_with_real_newlines_untouched():
    raw = "第一条 总则\n第二条 付款方式\n"
    assert normalize_contract_text(raw) == raw


def test_normalize_is_idempotent():
    once = normalize_contract_text("甲\\n乙")
    assert normalize_contract_text(once) == once


from app.capabilities.contract_review.prefill_schemas import PrefillData, PrefillPayload


def test_prefill_payload_defaults_are_all_null_and_empty():
    payload = PrefillPayload()
    assert payload.contract_info.payment_terms is None
    assert payload.contract_info.inspection_count is None
    assert payload.contract_plan == []
    assert payload.finance_info.contract_amount is None
    assert payload.guarantee == []


def test_prefill_payload_has_exactly_four_top_level_keys():
    assert list(PrefillPayload().model_dump().keys()) == [
        "contract_info",
        "contract_plan",
        "finance_info",
        "guarantee",
    ]


def test_prefill_data_failed_keeps_full_structure():
    data = PrefillData(prefill_status="failed")
    dumped = data.model_dump()
    assert dumped["mode"] == "prefill"
    assert dumped["prefill_status"] == "failed"
    assert dumped["prefill"]["contract_plan"] == []
    assert dumped["prefill"]["guarantee"] == []


def test_prefill_evidence_requires_quote_allows_null_section():
    from app.capabilities.contract_review.prefill_schemas import PrefillEvidence

    assert PrefillEvidence(quote="合同签订后7个工作日内").section is None
    assert PrefillEvidence(section="第四条 付款方式及条件", quote="…").section == "第四条 付款方式及条件"


from app.capabilities.contract_review.prefill_response_formats import (
    SCOPE_GROUPS,
    get_prefill_response_format,
    get_prefill_top_level_keys,
)

_EXPECTED = {
    "contract_info": [
        "payment_terms", "payment_method", "service_content", "service_valid_months",
        "service_sla", "service_start_date", "service_end_date",
        "onsite_service_count", "inspection_count",
    ],
    "contract_plan": [
        "milestone_name", "milestone_code", "milestone_text", "milestone_seq",
        "plan_finish_date", "plan_payment_date", "payment_amount", "evidence",
    ],
    "finance_info": ["contract_amount", "currency"],
    "guarantee": [
        "type", "amount", "payee", "bank_name", "bank_account", "return_clause", "evidence",
    ],
}


def _schema_of(scope: str) -> dict:
    return get_prefill_response_format(scope)["json_schema"]["schema"]


def test_scope_groups_match_with_design():
    assert SCOPE_GROUPS["d02"] == ("contract_info", "contract_plan")
    assert SCOPE_GROUPS["d03"] == ("finance_info", "guarantee")
    assert SCOPE_GROUPS["all"] == ("contract_info", "contract_plan", "finance_info", "guarantee")
    assert get_prefill_top_level_keys("d03") == ["finance_info", "guarantee"]


def test_schema_scope_only_exposes_requested_groups():
    assert list(_schema_of("d02")["properties"].keys()) == ["contract_info", "contract_plan"]
    assert list(_schema_of("d03")["properties"].keys()) == ["finance_info", "guarantee"]
    assert list(_schema_of("all")["properties"].keys()) == [
        "contract_info", "contract_plan", "finance_info", "guarantee",
    ]
    assert _schema_of("d02")["required"] == ["contract_info", "contract_plan"]


def test_schema_fields_match_design_field_list_exactly():
    props = _schema_of("all")["properties"]
    assert list(props["contract_info"]["properties"].keys()) == _EXPECTED["contract_info"]
    assert list(props["contract_plan"]["items"]["properties"].keys()) == _EXPECTED["contract_plan"]
    assert list(props["finance_info"]["properties"].keys()) == _EXPECTED["finance_info"]
    assert list(props["guarantee"]["items"]["properties"].keys()) == _EXPECTED["guarantee"]


_VERBATIM_FIELDS = {
    "contract_info": [
        "service_valid_months", "onsite_service_count", "inspection_count",
        "service_start_date", "service_end_date",
    ],
    "contract_plan": ["payment_amount", "plan_finish_date", "plan_payment_date"],
    "finance_info": ["contract_amount"],
    "guarantee": ["amount"],
}


def test_only_milestone_seq_is_not_a_string():
    """取值契约：除 milestone_seq 外不得再出现 JSON number。

    一旦声明成 number，模型为了满足 JSON 语法就必须去掉货币符号与千分位、
    并按类型补齐或截断小数位 —— 那是**语法约束冒充业务约束**，是本机加工误差的来源。
    """
    props = _schema_of("all")["properties"]
    for group, fields in _VERBATIM_FIELDS.items():
        node = (
            props[group]["items"]["properties"]
            if group in ("contract_plan", "guarantee")
            else props[group]["properties"]
        )
        for name in fields:
            assert node[name]["type"] == ["string", "null"], f"{group}.{name}"
    seq = props["contract_plan"]["items"]["properties"]["milestone_seq"]
    assert seq["type"] == ["integer", "null"]


def test_verbatim_fields_keep_the_original_wording():
    """金额 / 日期保留原文写法：货币符号、千分位、比例、非 ISO 日期一律照抄，不换算。"""
    dumped = PrefillPayload.model_validate({
        "contract_info": {"service_start_date": "2025年3月1日", "service_valid_months": "13.5个月"},
        "contract_plan": [{"milestone_seq": 1, "payment_amount": "¥10,492,500.00"}],
        "finance_info": {"contract_amount": "¥4690000元"},
        "guarantee": [{"amount": "5%"}],
    }).model_dump()
    assert dumped["contract_info"]["service_start_date"] == "2025年3月1日"
    assert dumped["contract_info"]["service_valid_months"] == "13.5个月"
    assert dumped["contract_plan"][0]["payment_amount"] == "¥10,492,500.00"
    assert dumped["finance_info"]["contract_amount"] == "¥4690000元"
    assert dumped["guarantee"][0]["amount"] == "5%"


def test_model_emitted_number_is_stringified_not_failed():
    """兜底：模型违反 strict schema 吐数字时按原值字符串化，不让 26 个字段一起降级 failed。"""
    payload = PrefillPayload.model_validate({
        "contract_info": {"service_valid_months": 13},
        "finance_info": {"contract_amount": 10492500.0},
    })
    assert payload.contract_info.service_valid_months == "13"
    assert payload.finance_info.contract_amount == "10492500.0"


def test_evidence_is_object_array_with_section_and_quote():
    evidence = _schema_of("all")["properties"]["contract_plan"]["items"]["properties"]["evidence"]
    assert evidence["type"] == "array"
    assert list(evidence["items"]["properties"].keys()) == ["section", "quote"]


def test_schema_is_strict_and_named_per_scope():
    for scope in ("all", "d02", "d03"):
        fmt = get_prefill_response_format(scope)
        assert fmt["type"] == "json_schema"
        assert fmt["json_schema"]["strict"] is True
        assert fmt["json_schema"]["name"] == f"contract_review_prefill_{scope}"


def test_get_prefill_response_format_returns_independent_copies():
    first = get_prefill_response_format("all")
    first["json_schema"]["schema"]["properties"]["contract_info"]["properties"]["payment_terms"] = {}
    assert _schema_of("all")["properties"]["contract_info"]["properties"]["payment_terms"] != {}


def test_prefill_prompt_renders_for_every_scope():
    from app.capabilities.contract_review.prefill_prompts import build_prefill_messages

    for scope in ("all", "d02", "d03"):
        messages = build_prefill_messages(scope, "第一条 总则")
        assert len(messages) == 2
        text = messages[1].content
        assert "第一条 总则" in text
        for key in get_prefill_top_level_keys(scope):
            assert key in text


def test_prefill_prompt_carries_the_time_source_rules():
    """两个时间字段的来源规则必须落在 prompt 里 —— 这是第十一轮的口径契约，删掉即回归。"""
    from app.capabilities.contract_review.prefill_prompts import build_prefill_messages

    text = "".join(m.content for m in build_prefill_messages("d02", "第一条 总则"))
    for phrase in ("plan_finish_date", "plan_payment_date", "合同计划", "交付", "不要自己算"):
        assert phrase in text


def test_prefill_prompt_renders_literal_braces_once():
    """user 模板要过 `.format()`：模板里的 `{{...}}` 必须还原成单个 `{...}`。

    踩坑记录：模板里写裸的 `{"section": ...}` 会让 `.format()` 去找名为 "section" 的
    占位符并抛 KeyError；`run_prefill` 的兜底又把异常吞成 `prefill_status=failed`，
    于是**一次 prompt 手误会静默降级成整份预填失败**。这条断言把坑钉死。
    """
    from app.capabilities.contract_review.prefill_prompts import build_prefill_messages

    text = "".join(m.content for m in build_prefill_messages("d02", "正文"))
    assert '{"section": null, "quote": "无"}' in text
    assert "{{" not in text


from app.capabilities.contract_review.schemas import ContractReviewRequest


def test_request_defaults_to_review_mode():
    req = ContractReviewRequest(contract_md="正文")
    assert req.mode == "review"
    assert req.prefill_scope == "all"


def test_request_accepts_prefill_scope_values():
    for scope in ("all", "d02", "d03"):
        assert ContractReviewRequest(contract_md="正文", mode="prefill", prefill_scope=scope).prefill_scope == scope


from unittest.mock import patch

from app.capabilities.contract_review.prefill_service import run_prefill


def _request(scope="all", md="正文"):
    return ContractReviewRequest(contract_md=md, mode="prefill", prefill_scope=scope)


def _ok_payload():
    """模拟新取值口径下模型的输出：除 milestone_seq 外一律原文原样字符串。"""
    return {
        "contract_info": {"payment_terms": "分期", "payment_method": "电汇"},
        "contract_plan": [
            {"milestone_name": "终验", "milestone_seq": 3, "payment_amount": "10%"},
            {"milestone_name": "启动", "milestone_seq": 1, "payment_amount": "50%"},
        ],
        "finance_info": {"contract_amount": "¥10,492,500.00", "currency": "CNY"},
        "guarantee": [{"type": "履约保证金", "amount": "5%"}],
    }


def test_run_prefill_all_returns_four_groups_ok():
    with patch("app.capabilities.contract_review.prefill_service._invoke_json_prompt", return_value=_ok_payload()):
        data = run_prefill(_request("all"))
    dumped = data.model_dump()
    assert dumped["prefill_status"] == "ok"
    assert dumped["prefill"]["finance_info"]["contract_amount"] == "¥10,492,500.00"
    assert dumped["prefill"]["contract_plan"][0]["payment_amount"] == "50%"
    assert dumped["prefill"]["guarantee"][0]["amount"] == "5%"
    assert len(dumped["prefill"]["guarantee"]) == 1


def test_run_prefill_d03_blanks_unrequested_groups():
    with patch("app.capabilities.contract_review.prefill_service._invoke_json_prompt", return_value=_ok_payload()):
        dumped = run_prefill(_request("d03")).model_dump()
    assert dumped["prefill"]["contract_info"]["payment_terms"] is None
    assert dumped["prefill"]["contract_plan"] == []
    assert dumped["prefill"]["finance_info"]["currency"] == "CNY"


def test_run_prefill_sorts_plan_by_milestone_seq():
    with patch("app.capabilities.contract_review.prefill_service._invoke_json_prompt", return_value=_ok_payload()):
        dumped = run_prefill(_request("d02")).model_dump()
    assert [row["milestone_seq"] for row in dumped["prefill"]["contract_plan"]] == [1, 3]


def test_run_prefill_asks_model_for_scope_specific_schema_and_keys():
    with patch("app.capabilities.contract_review.prefill_service._invoke_json_prompt", return_value=_ok_payload()) as mocked:
        run_prefill(_request("d03"))
    kwargs = mocked.call_args.kwargs
    assert kwargs["required_keys"] == ["finance_info", "guarantee"]
    assert kwargs["response_format"]["json_schema"]["name"] == "contract_review_prefill_d03"


def test_run_prefill_normalizes_newlines_before_prompt():
    captured = {}

    def fake(prompt_name, **kwargs):
        captured.update(kwargs)
        return _ok_payload()

    with patch("app.capabilities.contract_review.prefill_service._invoke_json_prompt", side_effect=fake):
        run_prefill(_request("d03", md="第一条 总则\\n第二条 付款"))
    assert captured["contract_md"] == "第一条 总则\n第二条 付款"


def test_run_prefill_returns_failed_on_model_error():
    with patch(
        "app.capabilities.contract_review.prefill_service._invoke_json_prompt",
        side_effect=RuntimeError("boom"),
    ):
        dumped = run_prefill(_request("all")).model_dump()
    assert dumped["prefill_status"] == "failed"
    assert dumped["prefill"]["contract_plan"] == []
    assert dumped["prefill"]["finance_info"]["contract_amount"] is None


def _client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app(register_middleware=False))


def test_router_routes_prefill_by_mode():
    with patch("app.capabilities.contract_review.router.run_prefill") as prefill, patch(
        "app.capabilities.contract_review.router.review_contract"
    ) as review:
        prefill.return_value = PrefillData(prefill_status="ok")
        _client().post("/api/v1/contract-review", json={"contract_md": "正文", "mode": "prefill"})
    assert prefill.call_count == 1
    assert review.call_count == 0


def test_router_keeps_review_path_for_default_mode():
    from app.capabilities.contract_review.schemas import CheckItem, ContractReviewData

    fake = ContractReviewData(
        overall_result="PASS",
        check_time="2026-09-16T10:00:00",
        checks=[CheckItem(id="序号1", name="合同首页完整性", result="PASS", block_level="通过")],
    )
    with patch("app.capabilities.contract_review.router.review_contract", return_value=fake) as review, patch(
        "app.capabilities.contract_review.router.run_prefill"
    ) as prefill:
        _client().post("/api/v1/contract-review", json={"contract_md": "正文"})
    assert review.call_count == 1
    assert prefill.call_count == 0


def test_prefill_response_data_has_only_three_keys():
    with patch("app.capabilities.contract_review.router.run_prefill", return_value=PrefillData(prefill_status="ok")):
        body = _client().post(
            "/api/v1/contract-review", json={"contract_md": "正文", "mode": "prefill"}
        ).json()
    assert body["code"] == 0
    assert set(body["data"].keys()) == {"mode", "prefill_status", "prefill"}
    assert body["data"]["mode"] == "prefill"
    assert set(body["data"]["prefill"].keys()) == {
        "contract_info", "contract_plan", "finance_info", "guarantee",
    }


def test_prefill_response_never_contains_review_keys():
    with patch("app.capabilities.contract_review.router.run_prefill", return_value=PrefillData(prefill_status="failed")):
        body = _client().post(
            "/api/v1/contract-review", json={"contract_md": "正文", "mode": "prefill"}
        ).json()
    for key in ("overall_result", "check_time", "checks", "metrics"):
        assert key not in body["data"]
    assert body["data"]["prefill_status"] == "failed"


def test_prefill_scope_d03_returns_blank_unrequested_groups():
    with patch("app.capabilities.contract_review.router.run_prefill", return_value=PrefillData(prefill_status="ok")):
        body = _client().post(
            "/api/v1/contract-review",
            json={"contract_md": "正文", "mode": "prefill", "prefill_scope": "d03"},
        ).json()
    assert body["data"]["prefill"]["contract_plan"] == []
    assert body["data"]["prefill"]["contract_info"]["payment_terms"] is None


def test_review_response_shape_is_unchanged_and_has_no_mode_key():
    from app.capabilities.contract_review.schemas import CheckItem, ContractReviewData

    fake = ContractReviewData(
        overall_result="PASS",
        check_time="2026-09-16T10:00:00",
        checks=[CheckItem(id="序号1", name="合同首页完整性", result="PASS", block_level="通过")],
    )
    with patch("app.capabilities.contract_review.router.review_contract", return_value=fake):
        body = _client().post("/api/v1/contract-review", json={"contract_md": "正文"}).json()
    assert set(body["data"].keys()) == {"overall_result", "check_time", "checks", "metrics"}
    assert "mode" not in body["data"]


def test_invalid_mode_returns_10001():
    response = _client().post(
        "/api/v1/contract-review", json={"contract_md": "正文", "mode": "review_prefill"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == 10001


def test_invalid_prefill_scope_returns_10001():
    response = _client().post(
        "/api/v1/contract-review", json={"contract_md": "正文", "mode": "prefill", "prefill_scope": "d01"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == 10001


def test_prefill_ignores_attachments():
    with patch("app.capabilities.contract_review.router.run_prefill", return_value=PrefillData(prefill_status="ok")):
        response = _client().post(
            "/api/v1/contract-review",
            json={
                "contract_md": "正文",
                "mode": "prefill",
                "attachments": [{"filename": "附件一.md", "text": "附件正文"}],
            },
        )
    assert response.status_code == 200


def test_prefill_call_carries_strict_schema_and_thinking_off():
    from app.capabilities.contract_review import service as svc

    seen = {}

    def fake_invoke(model, messages, response_format=None):
        seen["model"] = model
        seen["response_format"] = response_format
        return ('{"finance_info": {"contract_amount": "¥1.00", "currency": "CNY"}, "guarantee": []}', {})

    with patch("app.capabilities.contract_review.service.invoke_model", fake_invoke):
        run_prefill(_request("d03"))

    assert seen["response_format"]["json_schema"]["strict"] is True
    assert seen["response_format"]["json_schema"]["name"] == "contract_review_prefill_d03"
    assert seen["model"].kwargs.get("extra_body") == {"chat_template_kwargs": {"enable_thinking": False}}


def test_prefill_requires_all_scope_top_level_keys():
    from app.capabilities.contract_review.service import _invoke_json_prompt
    from app.core.errors import ModelFormatError

    with patch(
        "app.capabilities.contract_review.service.invoke_model",
        return_value=('{"finance_info": {"contract_amount": "¥1.00", "currency": "CNY"}}', {}),
    ):
        with pytest.raises(ModelFormatError):
            _invoke_json_prompt(
                "prefill",
                required_keys=["finance_info", "guarantee"],
                response_format=get_prefill_response_format("d03"),
                field_spec="x", json_example="y", top_level_keys="a", scope_note="z",
                contract_md="正文",
            )
