from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Document, User, Workspace, WorkspaceUser
from app.database.session import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.documents.dependencies import require_document
from app.modules.review_requests import service
from app.modules.review_requests.schemas import (
    ReviewRequestCreate,
    ReviewRequestListResponse,
    ReviewRequestResponse,
)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/documents/{document_id}/review-requests",
    tags=["ReviewRequests"],
)


@router.post(
    "", response_model=ReviewRequestResponse, status_code=status.HTTP_201_CREATED
)
async def create_review_request(
    workspace_id: str,
    document_id: str,
    payload: ReviewRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    doc_payload: tuple[Document, Workspace, WorkspaceUser] = Depends(require_document),
) -> ReviewRequestResponse:
    """Owner membuat review request ke satu reviewer (member workspace, bukan diri sendiri)."""
    document, _, _ = doc_payload
    if str(document.user_id) != str(current_user.id):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only document owner can create review requests",
        )
    return await service.create_review_request(
        db, workspace_id, document, str(current_user.id), payload
    )


@router.get("", response_model=ReviewRequestListResponse)
async def list_review_requests(
    document_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    doc_payload: tuple[Document, Workspace, WorkspaceUser] = Depends(require_document),
) -> ReviewRequestListResponse:
    """List review request sebuah document (member workspace)."""
    document, _, _ = doc_payload
    requests, total = await service.list_review_requests(
        db, str(document.id), skip, limit
    )
    return ReviewRequestListResponse(requests=requests, total=total)


@router.get("/{request_id}", response_model=ReviewRequestResponse)
async def get_review_request_detail(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    doc_payload: tuple[Document, Workspace, WorkspaceUser] = Depends(require_document),
) -> ReviewRequestResponse:
    """Detail satu review request (member workspace)."""
    document, _, _ = doc_payload
    req = await service.get_review_request(db, request_id, str(document.id))
    return service._to_response(req)


@router.post("/{request_id}/accept", response_model=ReviewRequestResponse)
async def accept_review_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    doc_payload: tuple[Document, Workspace, WorkspaceUser] = Depends(require_document),
) -> ReviewRequestResponse:
    """Reviewer menyetujui. 409 jika dokumen sudah punya mentor. Otomatis insert document_reviewers(is_mentor=True)."""
    document, _, _ = doc_payload
    req = await service.get_review_request(db, request_id, str(document.id))
    return await service.accept_review_request(db, req, str(current_user.id), document)


@router.post("/{request_id}/reject", response_model=ReviewRequestResponse)
async def reject_review_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    doc_payload: tuple[Document, Workspace, WorkspaceUser] = Depends(require_document),
) -> ReviewRequestResponse:
    """Reviewer menolak review request."""
    document, _, _ = doc_payload
    req = await service.get_review_request(db, request_id, str(document.id))
    return await service.reject_review_request(db, req, str(current_user.id))


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_review_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    doc_payload: tuple[Document, Workspace, WorkspaceUser] = Depends(require_document),
) -> None:
    """Owner batalkan review request yang masih pending."""
    document, _, _ = doc_payload
    req = await service.get_review_request(db, request_id, str(document.id))
    await service.cancel_review_request(db, req, str(current_user.id), document)
    return None
