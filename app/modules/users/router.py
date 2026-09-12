from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, Workspace
from app.database.session import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.users import service
from app.modules.users.dependencies import require_workspace_admin
from app.modules.users.schemas import (
    UserCreateByAdmin,
    UserListResponse,
    UserUpdateByAdmin,
    UserWorkspaceResponse,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/users", tags=["Users"])


@router.get("", response_model=UserListResponse)
async def list_users(
    workspace_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _workspace: Workspace = Depends(require_workspace_admin),
) -> UserListResponse:
    """Get list user dari workspace yang sama (admin only)."""
    users, total = await service.list_workspace_users(db, workspace_id, skip, limit)
    return UserListResponse(users=users, total=total)


@router.get("/{user_id}", response_model=UserWorkspaceResponse)
async def get_user_detail(
    user_id: str,
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    _workspace: Workspace = Depends(require_workspace_admin),
) -> UserWorkspaceResponse:
    """Get detail satu user dalam workspace yang sama (admin only)."""
    return await service.get_workspace_user_detail(db, workspace_id, user_id)


@router.post(
    "", response_model=UserWorkspaceResponse, status_code=status.HTTP_201_CREATED
)
async def create_user(
    payload: UserCreateByAdmin,
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    _workspace: Workspace = Depends(require_workspace_admin),
) -> UserWorkspaceResponse:
    """Admin registrasi user baru langsung ke workspace-nya."""
    return await service.create_workspace_user(db, workspace_id, payload)


@router.put("/{user_id}", response_model=UserWorkspaceResponse)
async def update_user(
    user_id: int,
    payload: UserUpdateByAdmin,
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    _workspace: Workspace = Depends(require_workspace_admin),
) -> UserWorkspaceResponse:
    """Admin update user dalam workspace yang sama."""
    return await service.update_workspace_user(db, workspace_id, user_id, payload)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    _workspace: Workspace = Depends(require_workspace_admin),
    current_user: User = Depends(get_current_user),
) -> None:
    """Admin hapus user dari workspace (remove membership, data user tetap ada)."""
    await service.delete_workspace_user(db, workspace_id, user_id, str(current_user.id))
    return None
