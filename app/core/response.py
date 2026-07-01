"""统一响应包装。"""
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ApiResponse(BaseModel):
    """统一响应：{ code, message, data, traceId, duration_seconds }。"""

    # 字段用 snake_case 存储与构造，序列化输出 camelCase（traceId / duration_seconds）。
    model_config = ConfigDict(populate_by_name=True)

    code: int = 0
    message: str = "ok"
    data: Optional[Any] = None
    trace_id: str = Field(default="", alias="traceId")
    duration_seconds: float = Field(default=0.0)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "data": self.data,
            "traceId": self.trace_id,
            "duration_seconds": round(self.duration_seconds, 3),
        }
