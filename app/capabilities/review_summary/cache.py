"""规范化输入 hash 缓存（一期：进程内内存实现，零新增依赖、零 config 键）。

设计文档 §6：对规范化后的请求体计算内容哈希作为缓存键；
`opinions` / `risk_register` 任何变更自动失效，合同系统无需通知。
缓存值为整包面板 `data`（不含 traceId / duration_seconds 等逐请求字段）。
"""
import hashlib
import json
from typing import Any

from app.capabilities.review_summary.schemas import ReviewSummaryRequest

# 进程内缓存：规范化输入 hash -> 面板 data。多副本部署下各自命中，正确性不受影响。
_CACHE: dict[str, Any] = {}


def normalize_request(request: ReviewSummaryRequest) -> dict:
    """规范化：按模型定义展开全部键，缺省与显式 null 归一为同一形态。"""
    return request.model_dump(mode="json")


def make_cache_key(request: ReviewSummaryRequest) -> str:
    """稳定缓存键：键排序 + 紧凑分隔符序列化后取 sha256；数组按传入顺序参与。"""
    canonical = json.dumps(
        normalize_request(request),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_cached(key: str) -> Any | None:
    """命中返回缓存的面板 data，未命中返回 None。"""
    return _CACHE.get(key)


def set_cached(key: str, value: Any) -> None:
    """写入缓存（值为整包面板 data，调用方保证不含逐请求字段）。"""
    _CACHE[key] = value


def clear_cache() -> None:
    """清空进程内缓存（测试与运维使用）。"""
    _CACHE.clear()
