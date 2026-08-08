"""
File: sentiment_schema.py
Chức năng: Pydantic schemas cho module sentiment (request/response validation)
Vai trò: Schema - chỉ khai báo dữ liệu, không chứa logic
File liên quan: app/routers/sentiment_router.py, app/services/sentiment_service.py
"""

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    """Dữ liệu đầu vào: bình luận tiếng Việt cần phân loại cảm xúc."""

    text: str = Field(..., min_length=1, max_length=1024, description="Binh luan can phan tich cam xuc")


class PredictResponse(BaseModel):
    """Kết quả dự báo: nhãn cảm xúc + xác suất % 3 lớp."""

    text: str
    sentiment: str
    sentiment_vi: str
    confidence: float
    probabilities: dict[str, float]


class HealthResponse(BaseModel):
    """Trạng thái sức khoẻ của API và mô hình."""

    status: str
    model_loaded: bool
    model_path: str
