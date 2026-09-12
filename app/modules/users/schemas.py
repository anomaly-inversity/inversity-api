from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.database.models import RoleEnum


class UserCreateByAdmin(BaseModel):
    """Payload admin untuk mendaftarkan user baru ke workspace-nya."""

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: RoleEnum = RoleEnum.USER


class UserUpdateByAdmin(BaseModel):
    """Payload admin untuk update user dalam workspace yang sama."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: RoleEnum | None = None


class UserWorkspaceResponse(BaseModel):
    """User + membership info dalam satu workspace."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: RoleEnum
    joined_at: datetime | None = None


class UserListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    users: list[UserWorkspaceResponse]
    total: int
