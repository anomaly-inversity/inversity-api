from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.database.models import RoleEnum


class WorkspaceCreate(BaseModel):
    """Payload untuk membuat workspace baru."""

    name: str = Field(min_length=1, max_length=100)


class WorkspaceUpdate(BaseModel):
    """Payload untuk update workspace."""

    name: str = Field(min_length=1, max_length=100)


class WorkspaceResponse(BaseModel):
    """Workspace + membership info milik current user."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    invite_code: str | None = None
    created_by: int | None = None
    created_at: datetime | None = None
    role: RoleEnum
    member_count: int = 0


class WorkspaceListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workspaces: list[WorkspaceResponse]
    total: int
