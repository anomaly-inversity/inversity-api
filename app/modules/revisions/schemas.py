from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RevisionCreate(BaseModel):
    """Payload untuk membuat revisi pada satu document version."""

    note: str = Field(min_length=1)


class RevisionUpdate(BaseModel):
    """Payload untuk update catatan revisi."""

    note: str = Field(min_length=1)


class RevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_version_id: str
    reviewer_id: str
    note: str
    status: str
    created_at: datetime | None = None


class RevisionListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    revisions: list[RevisionResponse]
    total: int
