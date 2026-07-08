from typing import Literal

from app.capabilities.contract_review.schemas import ContractParty
from app.capabilities.contract_review.utils import is_empty

RoleType = Literal["customer", "supplier", "neutral"]

CUSTOMER_SIDE_ROLES = {
    "甲方", "买方", "采购方", "需方", "委托方",
    "发包方", "建设方", "出租方", "授权方", "许可方",
}

SUPPLIER_SIDE_ROLES = {
    "乙方", "卖方", "供应方", "供方", "服务方", "服务提供方",
    "受托方", "承包方", "施工方", "承租方", "被授权方", "被许可方", "受让方",
}


def classify_role(role: str | None) -> RoleType:
    if role in CUSTOMER_SIDE_ROLES:
        return "customer"
    if role in SUPPLIER_SIDE_ROLES:
        return "supplier"
    return "neutral"


def build_candidate_parties(parties: list[ContractParty]) -> list[ContractParty]:
    supplier_candidates: list[ContractParty] = []
    neutral_candidates: list[ContractParty] = []

    for party in parties:
        if is_empty(party.name):
            continue
        role_type = classify_role(party.role)
        if role_type == "supplier":
            supplier_candidates.append(party)
        elif role_type == "neutral":
            neutral_candidates.append(party)

    return supplier_candidates + neutral_candidates
