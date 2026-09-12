from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Document, DocumentVersion, Workspace, WorkspaceUser
from app.database.session import get_db
from app.modules.document_versions import service
from app.modules.document_versions.schemas import (
    DocumentVersionCreate,
    DocumentVersionListResponse,
    DocumentVersionResponse,
    DocumentVersionUpdate,
)
from app.modules.documents.dependencies import (
    require_document,
    require_document_owner,
)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/documents/{document_id}/versions",
    tags=["DocumentVersions"],
)


@router.post(
    "", response_model=DocumentVersionResponse, status_code=status.HTTP_201_CREATED
)
async def create_version(
    workspace_id: str,
    document_id: str,
    payload: DocumentVersionCreate,
    db: AsyncSession = Depends(get_db),
    document: Document = Depends(require_document_owner),
) -> DocumentVersionResponse:
    """Buat version baru (owner document only). file_path hanyalah string path."""
    return await service.create_version(db, document, payload)


@router.get("", response_model=DocumentVersionListResponse)
async def list_versions(
    workspace_id: str,
    document_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    doc_payload: tuple[Document, Workspace, WorkspaceUser] = Depends(require_document),
) -> DocumentVersionListResponse:
    """List versi aktif sebuah document (member workspace)."""
    document, _, _ = doc_payload
    versions, total = await service.list_versions(db, str(document.id), skip, limit)
    return DocumentVersionListResponse(versions=versions, total=total)


@router.get("/{version_id}", response_model=DocumentVersionResponse)
async def get_version_detail(
    workspace_id: str,
    document_id: str,
    version_id: str,
    db: AsyncSession = Depends(get_db),
    doc_payload: tuple[Document, Workspace, WorkspaceUser] = Depends(require_document),
) -> DocumentVersionResponse:
    """Detail satu versi aktif (member workspace)."""
    document, _, _ = doc_payload
    version = await service.get_version(db, str(document.id), version_id)
    return service._to_response(version)


@router.put("/{version_id}", response_model=DocumentVersionResponse)
async def update_version(
    workspace_id: str,
    document_id: str,
    version_id: str,
    payload: DocumentVersionUpdate,
    db: AsyncSession = Depends(get_db),
    document: Document = Depends(require_document_owner),
) -> DocumentVersionResponse:
    """Update file_path versi (owner document only)."""
    version: DocumentVersion = await service.get_version(
        db, str(document.id), version_id
    )
    return await service.update_version(db, version, payload)


@router.delete("/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_version(
    workspace_id: str,
    document_id: str,
    version_id: str,
    db: AsyncSession = Depends(get_db),
    document: Document = Depends(require_document_owner),
) -> None:
    """Soft delete versi (owner document only). Row + revisions tetap ada di database."""
    version: DocumentVersion = await service.get_version(
        db, str(document.id), version_id
    )
    await service.delete_version(db, version)
    return None
