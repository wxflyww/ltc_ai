from collections.abc import Callable
from urllib.parse import urljoin

import httpx

from app.capabilities.contract_review.party import build_candidate_parties
from app.capabilities.contract_review.schemas import ContractParty, OurPartyContext, SystemPreset
from app.core.config import get_settings

FetchPreset = Callable[[str], SystemPreset | None]


def _join_url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def fetch_preset(
    entity_name: str,
    *,
    client_factory: Callable[[], httpx.Client] = httpx.Client,
    base_url: str | None = None,
    path: str | None = None,
    timeout: float | None = None,
) -> SystemPreset | None:
    settings = get_settings().signing_preset
    resolved_base_url = settings.base_url if base_url is None else base_url
    if not resolved_base_url:
        return None

    resolved_path = settings.path if path is None else path
    resolved_timeout = settings.timeout if timeout is None else timeout
    client = client_factory()
    try:
        response = client.post(
            _join_url(resolved_base_url, resolved_path),
            json={"entity_name": entity_name},
            timeout=resolved_timeout,
        )
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            close()

    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        return None

    payload = response.json()
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(data, dict):
        return None
    return SystemPreset.model_validate(data)


def identify_our_party(
    parties: list[ContractParty],
    fetch_preset: FetchPreset,
) -> tuple[OurPartyContext | None, SystemPreset | None]:
    for candidate in build_candidate_parties(parties):
        if candidate.name is None:
            continue
        preset = fetch_preset(candidate.name)
        if preset is None:
            continue
        return (
            OurPartyContext(role=candidate.role or "", name=candidate.name, preset_available=True),
            preset,
        )
    return None, None
