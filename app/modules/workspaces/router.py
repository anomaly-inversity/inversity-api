from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, Workspace, WorkspaceUser
from app.database.session import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.workspaces import service
from app.modules.workspaces.dependencies import (
    require_workspace_admin,
    require_workspace_member,
)
from app.modules.workspaces.schemas import (
    WorkspaceCreate,
    WorkspaceListResponse,
    WorkspaceResponse,
    WorkspaceUpdate,
)

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


@router.get("", response_model=WorkspaceListResponse)
async def list_workspaces(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> WorkspaceListResponse:
    """List workspace di mana current user adalah member."""
    workspaces, total = await service.list_user_workspaces(
        db, current_user.id, skip, limit
    )
    return WorkspaceListResponse(workspaces=workspaces, total=total)


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace_detail(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    _member: tuple[Workspace, WorkspaceUser] = Depends(  # noqa: B008
        require_workspace_member
    ),
) -> WorkspaceResponse:
    """Detail satu workspace. 404 jika bukan member."""
    return await service.get_workspace_detail(db, workspace_id, current_user.id)


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreate,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> WorkspaceResponse:
    """Buat workspace baru. Creator otomatis jadi ADMIN."""
    return await service.create_workspace(db, current_user.id, payload)


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: int,
    payload: WorkspaceUpdate,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    _admin: tuple[Workspace, WorkspaceUser] = Depends(  # noqa: B008
        require_workspace_admin
    ),
) -> WorkspaceResponse:
    """Update nama workspace (admin only)."""
    return await service.update_workspace(db, workspace_id, current_user.id, payload)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    _admin: tuple[Workspace, WorkspaceUser] = Depends(  # noqa: B008
        require_workspace_admin
    ),
) -> None:
    """Hapus workspace beserta membership-nya (admin only)."""
    await service.delete_workspace(db, workspace_id)
    return None
