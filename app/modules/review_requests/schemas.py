from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.database.models import ReviewStatusEnum


class ReviewRequestCreate(BaseModel):
    """Payload owner untuk meminta review ke satu reviewer."""

    reviewer_id: str = Field(min_length=1)


class ReviewRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str | uuid.UUID
    document_id: str | uuid.UUID
    reviewer_id: str | uuid.UUID
    status: ReviewStatusEnum
    created_at: datetime | None = None


class ReviewRequestListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    requests: list[ReviewRequestResponse]
    total: int
