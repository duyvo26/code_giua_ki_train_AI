"""
File: response.py
Chức năng: Chuẩn API Response - ApiSuccess, ApiError và Global Exception Handler
Vai trò: Util - mọi endpoint phải trả về ApiSuccess/ApiError, không trả raw dict
File liên quan: app/routers/sentiment_router.py, app/main.py
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.logger import get_logger

logger = get_logger(__name__)


class ApiSuccess(BaseModel):
    """Response chuẩn khi xử lý thành công."""

    success: bool = True
    message: str = "Thanh cong"
    data: Any | None = None


class ApiError(BaseModel):
    """Response chuẩn khi gặp lỗi (nghiệp vụ hoặc hệ thống)."""

    success: bool = False
    message: str
    error_code: str | None = None


def register_exception_handlers(app: FastAPI) -> None:
    """
    Đăng ký handler toàn cục để mọi lỗi đều trả JSON chuẩn ApiError.

    Logic:
      - RequestValidationError (lỗi Pydantic 422): trả 422 kèm chi tiết field lỗi
      - Exception tổng quát: log ERROR với exc_info để truy vết, trả 500
    """

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.warning("Validation loi tai %s %s: %s", request.method, request.url, exc.errors()[:3])
        return JSONResponse(
            status_code=422,
            content=ApiError(
                message="Du lieu khong hop le",
                error_code="VALIDATION_ERROR",
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Loi he thong tai %s %s: %s",
            request.method,
            request.url,
            exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content=ApiError(
                message="Loi he thong",
                error_code="INTERNAL_ERROR",
            ).model_dump(),
        )
