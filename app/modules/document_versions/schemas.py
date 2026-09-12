from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field


class DocumentVersionCreate(BaseModel):
    """Payload untuk membuat version baru. file_path hanyalah string path, tanpa handle upload file."""

    file_path: str = Field(min_length=1, max_length=1024)


class DocumentVersionUpdate(BaseModel):
    """Payload untuk update version (owner only). Hanya file_path yang bisa diubah."""

    file_path: str = Field(min_length=1, max_length=1024)


class DocumentVersionResponse(BaseModel):
    """Satu version document + metadata AI."""

    model_config = ConfigDict(from_attributes=True)

    id: str | uuid.UUID
    document_id: str | uuid.UUID
    file_path: str
    ai_summary: str | None = None
    ai_detection_score: float | None = None
    status: str
    created_at: datetime | None = None


class DocumentVersionListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    versions: list[DocumentVersionResponse]
    total: int
