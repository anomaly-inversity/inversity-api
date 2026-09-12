from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Document,
    DocumentVersion,
    RoleEnum,
    User,
    Workspace,
    WorkspaceUser,
)
from app.database.session import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.revisions import service
from app.modules.revisions.dependencies import (
    require_document_revision_viewer,
    require_interested,
    require_reviewer_or_admin,
    require_version,
)
from app.modules.revisions.schemas import (
    RevisionCreate,
    RevisionListResponse,
    RevisionResponse,
    RevisionUpdate,
)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/documents/{document_id}/versions/{version_id}/revisions",
    tags=["Revisions"],
)

document_router = APIRouter(
    prefix="/workspaces/{workspace_id}/documents/{document_id}/revisions",
    tags=["Revisions"],
)


@document_router.get("", response_model=RevisionListResponse)
async def list_document_revisions(
    workspace_id: str,
    document_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    doc_payload: tuple[Document, Workspace, WorkspaceUser] = Depends(
        require_document_revision_viewer
    ),
) -> RevisionListResponse:
    """List menyeluruh revisions sebuah document dari semua versions.

    Hanya owner, reviewer manapun, atau admin workspace.
    Urut newest first, sertakan document_version_id per item.
    """
    document, _, _ = doc_payload
    revisions, total = await service.list_document_revisions(
        db, str(document.id), skip, limit
    )
    return RevisionListResponse(revisions=revisions, total=total)


@router.post("", response_model=RevisionResponse, status_code=status.HTTP_201_CREATED)
async def create_revision(
    workspace_id: str,
    document_id: str,
    version_id: str,
    payload: RevisionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ctx: tuple[Document, DocumentVersion, Workspace, WorkspaceUser] = Depends(
        require_reviewer_or_admin
    ),
) -> RevisionResponse:
    """Buat revisi (reviewer document / admin). Set document + version menjadi REVISE."""
    document, version, _, _ = ctx
    return await service.create_revision(
        db, document, version, str(current_user.id), payload
    )


@router.get("", response_model=RevisionListResponse)
async def list_revisions(
    workspace_id: str,
    document_id: str,
    version_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    ctx: tuple[Document, DocumentVersion, Workspace, WorkspaceUser] = Depends(
        require_interested
    ),
) -> RevisionListResponse:
    """List revisi aktif (owner / reviewer / admin)."""
    _, version, _, _ = ctx
    revisions, total = await service.list_revisions(db, str(version.id), skip, limit)
    return RevisionListResponse(revisions=revisions, total=total)


@router.get("/{revision_id}", response_model=RevisionResponse)
async def get_revision_detail(
    workspace_id: str,
    document_id: str,
    version_id: str,
    revision_id: str,
    db: AsyncSession = Depends(get_db),
    ctx: tuple[Document, DocumentVersion, Workspace, WorkspaceUser] = Depends(
        require_interested
    ),
) -> RevisionResponse:
    """Detail satu revisi (owner / reviewer / admin)."""
    _, version, _, _ = ctx
    revision = await service.get_revision(db, str(version.id), revision_id)
    return service._to_response(revision)


@router.put("/{revision_id}", response_model=RevisionResponse)
async def update_revision(
    workspace_id: str,
    document_id: str,
    version_id: str,
    revision_id: str,
    payload: RevisionUpdate,
    db: AsyncSession = Depends(get_db),
    ctx: tuple[Document, DocumentVersion, Workspace, WorkspaceUser] = Depends(
        require_reviewer_or_admin
    ),
) -> RevisionResponse:
    """Update catatan revisi (reviewer document / admin)."""
    _, version, _, _ = ctx
    revision = await service.get_revision(db, str(version.id), revision_id)
    return await service.update_revision(db, revision, payload)


@router.delete("/{revision_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_revision(
    workspace_id: str,
    document_id: str,
    version_id: str,
    revision_id: str,
    db: AsyncSession = Depends(get_db),
    ctx: tuple[Document, DocumentVersion, Workspace, WorkspaceUser] = Depends(
        require_reviewer_or_admin
    ),
) -> None:
    """Soft delete revisi (reviewer document / admin). Data tetap ada di database."""
    _, version, _, _ = ctx
    revision = await service.get_revision(db, str(version.id), revision_id)
    await service.delete_revision(db, revision)
    return None


@router.post("/{revision_id}/resolve", response_model=RevisionResponse)
async def resolve_revision(
    workspace_id: str,
    document_id: str,
    version_id: str,
    revision_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ctx: tuple[Document, DocumentVersion, Workspace, WorkspaceUser] = Depends(
        require_version
    ),
) -> RevisionResponse:
    """Resolve revisi. Hanya reviewer pembuat atau admin workspace."""
    _, version, _, membership = ctx
    revision = await service.get_revision(db, str(version.id), revision_id)
    return await service.resolve_revision(
        db, revision, str(current_user.id), membership.role == RoleEnum.ADMIN
    )
