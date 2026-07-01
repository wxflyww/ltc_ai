"""统一错误码与业务异常基类。"""


class ErrorCode:
    SUCCESS = 0

    # 客户端错误 1xxxx
    PARAM_INVALID = 10001
    AUTH_INVALID = 10002

    # 服务端错误 2xxxx
    MODEL_INVOCATION = 20001  # 调用失败（重试耗尽）
    MODEL_TIMEOUT = 20002
    MODEL_FORMAT = 20003
    UNKNOWN = 29999


class AppError(Exception):
    """业务异常基类。异常处理器据此转成统一响应。"""

    code: int = ErrorCode.UNKNOWN
    http_status: int = 500

    def __init__(self, message: str = ""):
        self.message = message or self.__class__.__name__
        super().__init__(self.message)


class ValidationError(AppError):
    code = ErrorCode.PARAM_INVALID
    http_status = 400


class AuthError(AppError):
    code = ErrorCode.AUTH_INVALID
    http_status = 401


class ModelInvocationError(AppError):
    code = ErrorCode.MODEL_INVOCATION
    http_status = 500


class ModelTimeoutError(AppError):
    code = ErrorCode.MODEL_TIMEOUT
    http_status = 504


class ModelFormatError(AppError):
    code = ErrorCode.MODEL_FORMAT
    http_status = 500
