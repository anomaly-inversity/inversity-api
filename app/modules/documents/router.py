from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Document, User, Workspace, WorkspaceUser
from app.database.session import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.documents import service
from app.modules.documents.dependencies import require_document, require_document_owner
from app.modules.documents.schemas import (
    DocumentCreate,
    DocumentListResponse,
    DocumentResponse,
    DocumentReviewerCreate,
    DocumentReviewerListResponse,
    DocumentReviewerResponse,
    DocumentUpdate,
    NeedReviewListResponse,
)
from app.modules.workspaces.dependencies import (
    require_workspace_admin,
    require_workspace_member,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/documents", tags=["Documents"])


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    workspace_id: str,
    payload: DocumentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _member: tuple[Workspace, WorkspaceUser] = Depends(require_workspace_member),
) -> DocumentResponse:
    """Buat document baru. Owner = current_user, status awal draft."""
    return await service.create_document(
        db, workspace_id, str(current_user.id), payload
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    workspace_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _member: tuple[Workspace, WorkspaceUser] = Depends(require_workspace_member),
) -> DocumentListResponse:
    """List document dalam workspace (member only)."""
    documents, total = await service.list_documents(db, workspace_id, skip, limit)
    return DocumentListResponse(documents=documents, total=total)


@router.get("/need-requests", response_model=NeedReviewListResponse)
async def list_need_requests(
    workspace_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _member: tuple[Workspace, WorkspaceUser] = Depends(require_workspace_member),
) -> NeedReviewListResponse:
    """List document yang perlu current_user approve/reject (pending request miliknya, dokumen belum punya mentor)."""
    documents, total = await service.list_need_reviews(
        db, workspace_id, str(current_user.id), skip, limit
    )
    return NeedReviewListResponse(documents=documents, total=total)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document_detail(
    payload: tuple[Document, Workspace, WorkspaceUser] = Depends(require_document),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Detail satu document (member workspace)."""
    document, _, _ = payload
    return await service.get_document(db, document)


@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: str,
    payload: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
    document: Document = Depends(require_document_owner),
) -> DocumentResponse:
    """Update title/status document (owner only)."""
    return await service.update_document(db, document, payload)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    document: Document = Depends(require_document_owner),
) -> None:
    """Hapus document beserta review request & reviewer-nya (owner only)."""
    await service.delete_document(db, document)
    return None


@router.get("/{document_id}/reviewers", response_model=DocumentReviewerListResponse)
async def list_reviewers(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    payload: tuple[Document, Workspace, WorkspaceUser] = Depends(require_document),
) -> DocumentReviewerListResponse:
    """List reviewer/pembimbing sebuah document (member only)."""
    reviewers, total = await service.list_reviewers(db, str(payload[0].id))
    return DocumentReviewerListResponse(reviewers=reviewers, total=total)


@router.post(
    "/{document_id}/reviewers",
    response_model=DocumentReviewerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_reviewer_manual(
    workspace_id: str,
    payload: DocumentReviewerCreate,
    db: AsyncSession = Depends(get_db),
    doc_payload: tuple[Document, Workspace, WorkspaceUser] = Depends(require_document),
    _admin: tuple[Workspace, WorkspaceUser] = Depends(require_workspace_admin),
) -> DocumentReviewerResponse:
    """Admin input manual reviewer/pembimbing (is_mentor default True)."""
    document, _, _ = doc_payload
    return await service.add_reviewer_manual(db, workspace_id, document, payload)


@router.delete(
    "/{document_id}/reviewers/{reviewer_row_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_reviewer(
    document_id: str,
    reviewer_row_id: int,
    db: AsyncSession = Depends(get_db),
    _doc: tuple[Document, Workspace, WorkspaceUser] = Depends(require_document),
    _admin: tuple[Workspace, WorkspaceUser] = Depends(require_workspace_admin),
) -> None:
    """Admin hapus reviewer dari document."""
    await service.remove_reviewer(db, document_id, reviewer_row_id)
    return None
