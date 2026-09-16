from langchain_openai import ChatOpenAI

from app.capabilities.contract_review import service as svc

_THINK_OFF = {"chat_template_kwargs": {"enable_thinking": False}}


def _fake_model() -> ChatOpenAI:
    return ChatOpenAI(model="qwen3.6-35b-a3b", base_url="http://127.0.0.1:1/v1", api_key="k")


def _settings_stub(disable_thinking: bool):
    llm = type("Llm", (), {"disable_thinking": disable_thinking})()
    return type("Settings", (), {"llm": llm})()


def test_model_for_json_prompt_binds_disable_thinking(monkeypatch):
    model = _fake_model()
    monkeypatch.setattr(svc, "get_chat_model", lambda: model)
    monkeypatch.setattr(svc, "get_settings", lambda: _settings_stub(True))

    bound = svc._model_for_json_prompt()

    assert bound is not model
    assert bound.kwargs.get("extra_body") == _THINK_OFF


def test_model_for_json_prompt_returns_plain_model_when_switch_off(monkeypatch):
    model = _fake_model()
    monkeypatch.setattr(svc, "get_chat_model", lambda: model)
    monkeypatch.setattr(svc, "get_settings", lambda: _settings_stub(False))

    assert svc._model_for_json_prompt() is model


def test_invoke_json_prompt_actually_sends_thinking_off(monkeypatch):
    """最强判据：走真实 _invoke_json_prompt，捕获真正交给 invoke_model 的模型对象。"""
    seen = {}

    def fake_invoke(model, messages, response_format=None):
        seen["model"] = model
        seen["response_format"] = response_format
        return ('{"header": {}, "signature_parties": [], "sections": []}', {})

    monkeypatch.setattr(svc, "invoke_model", fake_invoke)

    svc._invoke_json_prompt("a1a_party_extraction", full_text="合同正文")

    assert seen["model"].kwargs.get("extra_body") == _THINK_OFF
    assert seen["response_format"] is not None


def test_bound_model_keeps_model_name_for_metrics(monkeypatch):
    """bind 后仍能取到 model_name，Prometheus 指标标签不退化。"""
    model = _fake_model()
    monkeypatch.setattr(svc, "get_chat_model", lambda: model)
    monkeypatch.setattr(svc, "get_settings", lambda: _settings_stub(True))

    assert getattr(svc._model_for_json_prompt(), "model_name", "") == "qwen3.6-35b-a3b"
