from app.capabilities.contract_review.preset_client import fetch_preset, identify_our_party
from app.capabilities.contract_review.schemas import ContractParty, SystemPreset


def test_identify_our_party_stops_after_first_hit():
    calls: list[str] = []

    def fake_fetch(entity_name: str) -> SystemPreset | None:
        calls.append(entity_name)
        if entity_name == "我方公司":
            return SystemPreset(entity_name="我方公司", legal_rep_name="张三")
        return None

    parties = [
        ContractParty(role="甲方", name="客户公司"),
        ContractParty(role="乙方", name="我方公司"),
        ContractParty(role="第三方", name="中性公司"),
    ]
    context, preset = identify_our_party(parties, fake_fetch)
    assert context is not None
    assert context.name == "我方公司"
    assert preset is not None
    assert calls == ["我方公司"]


def test_identify_our_party_tries_neutral_when_supplier_misses():
    calls: list[str] = []

    def fake_fetch(entity_name: str) -> SystemPreset | None:
        calls.append(entity_name)
        if entity_name == "中性公司":
            return SystemPreset(entity_name="中性公司")
        return None

    parties = [
        ContractParty(role="乙方", name="供应商未命中"),
        ContractParty(role="合作方二", name="中性公司"),
    ]
    context, preset = identify_our_party(parties, fake_fetch)
    assert context is not None
    assert context.name == "中性公司"
    assert preset is not None
    assert calls == ["供应商未命中", "中性公司"]


def test_identify_our_party_returns_none_when_all_candidates_miss():
    def fake_fetch(entity_name: str) -> SystemPreset | None:
        return None

    context, preset = identify_our_party([ContractParty(role="乙方", name="未命中公司")], fake_fetch)
    assert context is None
    assert preset is None


def test_fetch_preset_posts_entity_name_and_parses_response():
    calls = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "code": 0,
                "data": {
                    "entity_name": "我方公司",
                    "legal_rep_name": "张三",
                    "legal_rep_id_number": "210102197001010011",
                    "authorized_reps": [{"name": "李四", "id_number": "210102197001010022"}],
                    "bank_name": "招商银行",
                    "bank_account": "123456",
                    "account_holder": "我方公司",
                    "address": "地址",
                    "phone": "024-12345678",
                    "fax": "",
                    "website": "",
                    "postal_code": "110000",
                },
            }

    class FakeClient:
        def post(self, url, json, timeout):
            calls.append((url, json, timeout))
            return FakeResponse()

        def close(self):
            pass

    preset = fetch_preset(
        "我方公司",
        client_factory=FakeClient,
        base_url="http://preset.local",
        path="/api/v1/signature-presets/by-entity-name",
        timeout=2.0,
    )
    assert preset is not None
    assert preset.entity_name == "我方公司"
    assert preset.authorized_reps[0].name == "李四"
    assert calls == [
        (
            "http://preset.local/api/v1/signature-presets/by-entity-name",
            {"entity_name": "我方公司"},
            2.0,
        )
    ]


def test_fetch_preset_returns_none_when_not_configured():
    assert fetch_preset("我方公司", base_url="") is None
