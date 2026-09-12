from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    """Payload untuk membuat document baru. Status awal selalu draft."""

    title: str = Field(min_length=1, max_length=200)


class DocumentUpdate(BaseModel):
    """Payload untuk update document (owner only)."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = Field(default=None, min_length=1, max_length=50)


class DocumentResponse(BaseModel):
    """Document + identitas owner/workspace."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    user_id: str
    title: str
    status: str
    created_at: datetime | None = None


class DocumentListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    documents: list[DocumentResponse]
    total: int


class NeedReviewItem(BaseModel):
    """Satu document yang perlu direviewer approve/reject + info request-nya."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    user_id: str
    title: str
    status: str
    created_at: datetime | None = None
    review_request_id: str
    review_requested_at: datetime | None = None


class NeedReviewListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    documents: list[NeedReviewItem]
    total: int


class DocumentReviewerCreate(BaseModel):
    """Payload admin untuk input manual reviewer/pembimbing."""

    reviewer_id: str = Field(min_length=1)
    is_mentor: bool = True


class DocumentReviewerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: str
    reviewer_id: str
    is_mentor: bool


class DocumentReviewerListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reviewers: list[DocumentReviewerResponse]
    total: int
