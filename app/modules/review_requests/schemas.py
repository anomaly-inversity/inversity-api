from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.database.models import ReviewStatusEnum


class ReviewRequestCreate(BaseModel):
    """Payload owner untuk meminta review ke satu reviewer."""

    reviewer_id: str = Field(min_length=1)


class ReviewRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    reviewer_id: str
    status: ReviewStatusEnum
    created_at: datetime | None = None


class ReviewRequestListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    requests: list[ReviewRequestResponse]
    total: int
