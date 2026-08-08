"""
File: sentiment_router.py
Chức năng: Định nghĩa endpoint API cho module sentiment, tiếp nhận request và gọi service
Vai trò: Router - chỉ validate (Pydantic) + dispatch xuống service + trả ApiSuccess/ApiError
File liên quan: app/schemas/sentiment_schema.py, app/services/sentiment_service.py, app/utils/response.py
"""

from fastapi import APIRouter, HTTPException

from app.schemas.sentiment_schema import (
    HealthResponse,
    PredictRequest,
    PredictResponse,
)
from app.services.sentiment_service import ModelNotFoundError, sentiment_service
from app.utils.response import ApiError, ApiSuccess

router = APIRouter(tags=["sentiment"])


@router.post("/predict", response_model=ApiSuccess)
async def predict(request: PredictRequest) -> ApiSuccess:
    """
    Phân loại cảm xúc 1 bình luận tiếng Việt.

    Logic:
      - Validate text qua PredictRequest (Pydantic) - Rule 1: router không chứa logic
      - Gọi sentiment_service.predict() để chạy inference (Service chứa logic AI)
      - Lỗi thiếu model -> HTTPException 500 với ApiError chuẩn
    """
    try:
        result = sentiment_service.predict(request.text)
    except ModelNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail=ApiError(
                message=str(exc),
                error_code="MODEL_NOT_FOUND",
            ).model_dump(),
        ) from exc
    return ApiSuccess(data=result)


@router.get("/health", response_model=ApiSuccess)
async def health() -> ApiSuccess:
    """
    Kiểm tra trạng thái server và mô hình.
    Dùng cho dashboard giám sát nội bộ kiểm tra model đã nạp chưa.
    """
    return ApiSuccess(
        data=HealthResponse(
            status="ok",
            model_loaded=sentiment_service.is_loaded,
            model_path=str(sentiment_service.model_path),
        )
    )
