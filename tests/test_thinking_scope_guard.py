"""思考模式的跨能力边界守护。

固化 change `llm-disable-thinking` 任务 3.2 / 3.3 的断言：三个能力各自持有
独立的模型调用形态，任何一方都不得被"顺手统一"而改变行为。

- contract_review：按开关显式绑定 enable_thinking=false，且**返回新对象**
- translate：**裸调用**，不带 extra_body、不带 response_format
- two_stage：不读 disable_thinking，调用形态与开关无关

若将来有人把关思考绑定或结构化输出"下沉"到公共模型层（`app/models/llm.py`
或直接在单例上原地赋值），这些用例会立刻变红。

对象形态提示：`ChatOpenAI` 本身**没有** `.kwargs`，绑定后的 `RunnableBinding`
才有；原模型的参数在 `.model_kwargs` 里。故下面用两个 helper 分别取。
"""
from langchain_openai import ChatOpenAI

_THINK_OFF = {"chat_template_kwargs": {"enable_thinking": False}}


def _fake_model() -> ChatOpenAI:
    return ChatOpenAI(model="qwen3.6-35b-a3b", base_url="http://127.0.0.1:1/v1", api_key="k")


def _settings_stub(disable_thinking: bool):
    llm = type("Llm", (), {"disable_thinking": disable_thinking})()
    return type("Settings", (), {"llm": llm})()


def _bound_extra_body(runnable):
    """取绑定后对象（RunnableBinding）携带的 extra_body。"""
    return (getattr(runnable, "kwargs", None) or {}).get("extra_body")


def _plain_extra_body(model):
    """取原始模型对象携带的 extra_body（ChatOpenAI 走 model_kwargs）。"""
    kwargs = getattr(model, "model_kwargs", None) or {}
    return kwargs.get("extra_body") or getattr(model, "extra_body", None)


def _any_extra_body(model):
    """两种形态都查一遍，避免因对象形态差异而漏判。"""
    return _bound_extra_body(model) or _plain_extra_body(model)


def _contract_review_bound_and_singleton(monkeypatch):
    """走 contract_review 的真实取模型路径，返回 (bound, singleton)。"""
    from app.capabilities.contract_review import service as svc

    singleton = _fake_model()
    monkeypatch.setattr(svc, "get_chat_model", lambda: singleton)
    monkeypatch.setattr(svc, "get_settings", lambda: _settings_stub(True))
    return svc._model_for_json_prompt(), singleton


def test_contract_review_bind_returns_new_object(monkeypatch):
    bound, singleton = _contract_review_bound_and_singleton(monkeypatch)

    assert bound is not singleton
    assert _bound_extra_body(bound) == _THINK_OFF


def test_bind_does_not_pollute_the_shared_singleton(monkeypatch):
    """最关键的一条：绑定必须发生在副本上，原单例不得被写脏。

    这是三方隔离（review / two_stage / translate 共用同一单例）成立的前提。
    """
    _bound, singleton = _contract_review_bound_and_singleton(monkeypatch)

    assert _any_extra_body(singleton) is None


def test_repeated_binds_keep_singleton_clean(monkeypatch):
    """连做多次绑定，原单例仍干净 —— 排除"累积写脏"的可能。"""
    from app.capabilities.contract_review import service as svc

    singleton = _fake_model()
    monkeypatch.setattr(svc, "get_chat_model", lambda: singleton)
    monkeypatch.setattr(svc, "get_settings", lambda: _settings_stub(True))

    for _ in range(3):
        svc._model_for_json_prompt()

    assert _any_extra_body(singleton) is None


def test_translate_call_stays_bare(monkeypatch):
    """translate 的模型调用不得携带 extra_body / response_format。

    实测其无结构化输出时，25,782 字符里约 67% 是英文思考文本 —— 一旦被
    "统一"带上关思考或 schema，行为就变了（该能力由其他同事负责，本方案不修）。
    """
    from app.capabilities.translate import service as translate_service
    from app.capabilities.translate.schemas import TranslateRequest

    model = _fake_model()
    seen: dict = {}

    def fake_invoke(m, messages, **kwargs):
        seen["model"] = m
        seen["kwargs"] = kwargs
        return "译文", {}

    monkeypatch.setattr(translate_service, "get_chat_model", lambda: model)
    monkeypatch.setattr(translate_service, "invoke_model", fake_invoke)

    translate_service.translate(TranslateRequest(text="hello", target_lang="zh"))

    assert seen["model"] is model
    assert _any_extra_body(seen["model"]) is None
    assert seen["kwargs"].get("response_format") is None
