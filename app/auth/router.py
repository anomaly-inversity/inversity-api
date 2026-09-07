from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database.session import get_db
from app.database.models import User
from app.auth.schemas import (
    UserCreate,
    UserLogin,
    Token,
    RefreshTokenRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    UserResponse,
)
from app.auth import service
from app.auth.dependencies import get_current_user, oauth2_scheme

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    return await service.register_user(db, user_in)


@router.post("/login", response_model=Token)
async def login(user_in: UserLogin, db: AsyncSession = Depends(get_db)):
    return await service.login_user(db, user_in)


@router.post("/refresh", response_model=Token)
async def refresh_token(request_data: RefreshTokenRequest):
    return await service.refresh_user_token(request_data.refresh_token)


@router.post("/forgot-password")
async def forgot_password(request_data: ForgotPasswordRequest):
    return {"message": "Password reset email sent (mock)"}


@router.post("/reset-password")
async def reset_password(request_data: ResetPasswordRequest):
    return {"message": "Password has been reset (mock)"}


@router.get("/profile", response_model=UserResponse)
async def get_profile(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/logout")
async def logout(
    request_data: Optional[RefreshTokenRequest] = None,
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
):
    refresh_token = request_data.refresh_token if request_data else None
    await service.logout_user(current_user, token, refresh_token)
    return {"message": "Successfully logged out"}
