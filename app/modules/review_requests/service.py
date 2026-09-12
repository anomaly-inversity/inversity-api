import uuid
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.database.models import (
    Document,
    DocumentReviewer,
    DocumentStatusEnum,
    ReviewRequest,
    ReviewStatusEnum,
    WorkspaceUser,
)
from app.modules.review_requests.schemas import (
    ReviewRequestCreate,
    ReviewRequestResponse,
)

logger = structlog.get_logger()


def _to_response(req: ReviewRequest) -> ReviewRequestResponse:
    return ReviewRequestResponse(
        id=str(req.id),
        document_id=str(req.document_id),
        reviewer_id=str(req.reviewer_id),
        status=req.status,
        created_at=req.created_at,
    )


async def _ensure_reviewer_is_member(
    db: AsyncSession, workspace_id: str, reviewer_id: str | uuid.UUID
) -> None:
    stmt = select(WorkspaceUser).where(
        WorkspaceUser.workspace_id == workspace_id,
        WorkspaceUser.user_id == reviewer_id,
    )
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reviewer not found in this workspace",
        )


async def create_review_request(
    db: AsyncSession,
    workspace_id: str,
    document: Document,
    owner_id: str,
    payload: ReviewRequestCreate,
) -> ReviewRequestResponse:
    """Owner membuat review request. Validasi: bukan diri sendiri, reviewer member, anti-duplikat pending, dokumen belum punya mentor."""
    if str(payload.reviewer_id) == str(owner_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot request review from yourself",
        )

    await _ensure_reviewer_is_member(db, workspace_id, payload.reviewer_id)

    stmt = select(DocumentReviewer).where(
        DocumentReviewer.document_id == document.id,
        DocumentReviewer.is_mentor.is_(True),
    )
    if (await db.execute(stmt)).scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document already approved by another reviewer",
        )

    stmt = select(ReviewRequest).where(
        ReviewRequest.document_id == document.id,
        ReviewRequest.reviewer_id == payload.reviewer_id,
        ReviewRequest.status == ReviewStatusEnum.PENDING,
    )
    if (await db.execute(stmt)).scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pending review request already exists for this reviewer",
        )

    req = ReviewRequest(
        document_id=document.id,
        reviewer_id=payload.reviewer_id,
        status=ReviewStatusEnum.PENDING,
    )
    db.add(req)

    await db.commit()
    await db.refresh(req)
    logger.info(
        "create_review_request_success",
        document_id=document.id,
        reviewer_id=payload.reviewer_id,
    )
    return _to_response(req)


async def list_review_requests(
    db: AsyncSession, document_id: str, skip: int = 0, limit: int = 100
) -> tuple[list[ReviewRequestResponse], int]:
    """List semua review request sebuah document (member workspace)."""
    count_stmt = (
        select(func.count())
        .select_from(ReviewRequest)
        .where(ReviewRequest.document_id == document_id)
    )
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(ReviewRequest)
        .where(ReviewRequest.document_id == document_id)
        .order_by(ReviewRequest.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_response(r) for r in rows], total


async def get_review_request(
    db: AsyncSession, request_id: str, document_id: str | uuid.UUID
) -> ReviewRequest:
    """Detail satu review request. 404 jika tidak milik document ini."""
    stmt = select(ReviewRequest).where(
        ReviewRequest.id == request_id,
        ReviewRequest.document_id == document_id,
    )
    req = (await db.execute(stmt)).scalar_one_or_none()
    if req is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Review request not found"
        )
    return req


async def cancel_review_request(
    db: AsyncSession, req: ReviewRequest, owner_id: str, document: Document
) -> None:
    """Owner batalkan request pending. Hanya pending yang bisa di-cancel."""
    if str(document.user_id) != str(owner_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only document owner can cancel this request",
        )
    if req.status != ReviewStatusEnum.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending requests can be cancelled",
        )
    await db.delete(req)

    stmt = select(ReviewRequest).where(
        ReviewRequest.document_id == document.id,
        ReviewRequest.status == ReviewStatusEnum.PENDING,
        ReviewRequest.id != req.id,
    )
    remaining = (await db.execute(stmt)).scalars().all()
    document.status = DocumentStatusEnum.PENDING

    await db.commit()
    logger.info("cancel_review_request_success", request_id=req.id)


async def accept_review_request(
    db: AsyncSession, req: ReviewRequest, reviewer_id: str, document: Document
) -> ReviewRequestResponse:
    """Reviewer menyetujui. Guard: hanya reviewer bersangkutan, hanya pending, dokumen belum punya mentor. Transaksi: accepted + insert document_reviewers(is_mentor=True) + document approved."""
    if str(req.reviewer_id) != str(reviewer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the requested reviewer can accept this request",
        )
    if req.status != ReviewStatusEnum.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending requests can be accepted",
        )

    stmt = select(DocumentReviewer).where(
        DocumentReviewer.document_id == document.id,
        DocumentReviewer.is_mentor.is_(True),
    )
    if (await db.execute(stmt)).scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document already approved by another reviewer",
        )

    req.status = ReviewStatusEnum.ACCEPTED
    mentor = DocumentReviewer(
        document_id=document.id,
        reviewer_id=req.reviewer_id,
        is_mentor=True,
    )
    db.add(mentor)
    document.status = DocumentStatusEnum.ACCEPTED

    await db.commit()
    await db.refresh(req)
    logger.info(
        "accept_review_request_success",
        request_id=req.id,
        reviewer_id=reviewer_id,
    )
    return _to_response(req)


async def reject_review_request(
    db: AsyncSession, req: ReviewRequest, reviewer_id: str | uuid.UUID
) -> ReviewRequestResponse:
    """Reviewer menolak. Hanya reviewer bersangkutan, hanya pending. Tanpa insert reviewer."""
    if str(req.reviewer_id) != str(reviewer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the requested reviewer can reject this request",
        )
    if req.status != ReviewStatusEnum.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending requests can be rejected",
        )

    req.status = ReviewStatusEnum.REJECTED
    await db.commit()
    await db.refresh(req)
    logger.info(
        "reject_review_request_success",
        request_id=req.id,
        reviewer_id=reviewer_id,
    )
    return _to_response(req)
