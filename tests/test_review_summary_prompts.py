"""Prompt 加载与 JSON 解析用例（tasks.md §2.2）。

review_summary 自带独立的 yaml 加载器与 JSON 抽取实现，与 `contract_review` 零依赖。
"""
import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from app.capabilities.review_summary import prompts as p
from app.core.errors import ModelFormatError


@pytest.fixture(autouse=True)
def _reset_template():
    p._reset_template()
    yield
    p._reset_template()


# ------------------------------------------------------------------ yaml 加载


def test_template_defines_both_generation_tasks():
    tpl = p._load_template()
    assert set(tpl.keys()) >= {"summary", "opinion"}
    for task in ("summary", "opinion"):
        assert tpl[task]["system"].strip(), f"{task}.system 不得为空占位"
        assert tpl[task]["user"].strip(), f"{task}.user 不得为空占位"


def test_build_prompt_returns_system_and_human_messages():
    messages = p.build_prompt("summary", contract_meta_block="（无）", route_reason_block="（无）",
                              risk_register_block="（无）", opinions_block="（无）",
                              distribution_note="无评审意见", coverage_note="（无）",
                              valid_refs_block="（无）", retry_note="")
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)
    assert len(messages) == 2
    assert "（无）" in messages[1].content
    # 首发的定向修正块是空的：不得留下空标题之类的噪音
    assert "【定向修正要求" in messages[1].content
    assert "【有字意见清单" in messages[1].content  # D16：覆盖范围由服务端列出


def test_build_prompt_substitutes_all_placeholders():
    messages = p.build_prompt("opinion", opinions_block="[编号 0] 法务 · 陈某：建议补充仲裁地。",
                              valid_refs_block="opinions[0]")
    content = messages[1].content
    assert "[编号 0] 法务 · 陈某：建议补充仲裁地。" in content
    assert "opinions[0]" in content
    assert "{opinions_block}" not in content and "{valid_refs_block}" not in content


def test_summary_system_prompt_embeds_the_five_rules():
    system = p.build_prompt(
        "summary", contract_meta_block="x", route_reason_block="x", risk_register_block="x",
        opinions_block="x", distribution_note="x", coverage_note="x", valid_refs_block="x",
        retry_note="x",
    )[0].content
    assert "数字零生成" in system
    assert "事实单点归属" in system
    assert "溯源" in system
    assert "形容词" in system
    assert "中性" in system  # reject 时总述退化为中性陈述
    assert "建议通过" in system  # 不出具决策建议
    assert "客户" in system and "评价" in system  # CRM 暂缓期不写客户评价
    # D16 契约：模型只交主题句 + 指针，合同要素与结论分布由服务端装配
    assert "opinion_refs" in system
    assert "服务端装配" in system
    assert "未背书" in system  # G3 两档判定的口径要向模型说明白


def test_summary_retry_note_reaches_the_user_prompt():
    """定向重试话术只进 user 消息：每条违规都是服务端复检出的可核验事实。"""
    user = p.build_prompt(
        "summary", contract_meta_block="x", route_reason_block="x", risk_register_block="x",
        opinions_block="x", distribution_note="x", coverage_note="x", valid_refs_block="x",
        retry_note="主题 2 点名了未背书的节点：财经复核",
    )[1].content
    assert "主题 2 点名了未背书的节点：财经复核" in user


def test_opinion_system_prompt_requires_verbatim_numbers_and_conditions():
    system = p.build_prompt("opinion", opinions_block="x", valid_refs_block="x")[0].content
    assert "数字零生成" in system
    assert "条件" in system  # 保留主张与条件
    assert "index" in system  # 批量输出需按编号一一对应


def test_unknown_prompt_name_raises():
    with pytest.raises(KeyError):
        p.build_prompt("nonexistent_task", x="1")


# ------------------------------------------------------------- response_format


@pytest.mark.parametrize("task", ["summary", "opinion"])
def test_response_format_is_strict_json_schema(task):
    fmt = p.get_response_format(task)
    assert fmt["type"] == "json_schema"
    schema = fmt["json_schema"]
    assert schema["strict"] is True
    assert schema["schema"]["type"] == "object"
    assert schema["schema"]["additionalProperties"] is False
    assert schema["name"].startswith("review_summary")


def test_summary_response_format_shape():
    """D16 形状：`{overall, themes[{text, opinion_refs}]}`，旧 `{text, source_refs}` 已退役。"""
    schema = p.get_response_format("summary")["json_schema"]["schema"]
    props = schema["properties"]
    assert set(props.keys()) == {"overall", "themes"}
    assert props["overall"]["type"] == ["string", "null"]
    theme = props["themes"]["items"]
    assert theme["type"] == "object"
    assert set(theme["properties"].keys()) == {"text", "opinion_refs"}
    assert theme["properties"]["text"]["type"] == "string"  # 主题句不得为空字符串占位
    assert theme["properties"]["opinion_refs"]["type"] == "array"
    assert theme["additionalProperties"] is False
    assert set(theme["required"]) == {"text", "opinion_refs"}


def test_opinion_response_format_shape():
    props = p.get_response_format("opinion")["json_schema"]["schema"]["properties"]
    assert set(props.keys()) == {"summaries"}
    item = props["summaries"]["items"]
    assert set(item["properties"].keys()) == {"index", "summary", "source_refs"}
    assert item["additionalProperties"] is False


def test_response_formats_are_not_shared_mutable_state():
    """每次取到的对象互相独立，调用方改动不污染模板（对齐既有能力口径）。"""
    first = p.get_response_format("summary")
    first["json_schema"]["name"] = "被改坏"
    assert p.get_response_format("summary")["json_schema"]["name"] != "被改坏"


# ---------------------------------------------------------------- JSON 解析


def test_parse_plain_json_object():
    assert p.parse_json_object('{"text": "总述", "source_refs": []}') == {
        "text": "总述",
        "source_refs": [],
    }


def test_parse_fenced_json_block():
    content = '```json\n{"text": "总述", "source_refs": ["opinions[0]"]}\n```'
    assert p.parse_json_object(content)["text"] == "总述"


def test_parse_json_with_surrounding_prose():
    content = '好的，结果如下：\n{"text": "总述", "source_refs": []}\n以上。'
    assert p.parse_json_object(content)["text"] == "总述"


def test_parse_strips_paired_think_block():
    content = '<think>草稿 {"text": "坏"} </think>\n{"text": "好", "source_refs": []}'
    assert p.parse_json_object(content)["text"] == "好"


def test_parse_ignores_draft_before_lone_think_close_tag():
    """模型偶发只吐 `</think>` 闭标签：闭标签前的草稿 JSON 不得被当成结果。"""
    content = '思考中…{"text": "坏"}\n</think>\n{"text": "好", "source_refs": []}'
    assert p.parse_json_object(content)["text"] == "好"


def test_parse_invalid_json_raises_model_format_error():
    with pytest.raises(ModelFormatError) as exc:
        p.parse_json_object("完全不是 JSON")
    assert exc.value.code == 20003


def test_parse_json_array_raises_model_format_error():
    with pytest.raises(ModelFormatError):
        p.parse_json_object('[{"text": "总述"}]')


def test_parse_empty_content_raises_model_format_error():
    with pytest.raises(ModelFormatError):
        p.parse_json_object("   ")
