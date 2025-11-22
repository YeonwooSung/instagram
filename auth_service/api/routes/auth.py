"""
Authentication routes
"""
from fastapi import APIRouter, Depends, status

from schemas import (
    UserRegister, UserLogin, TokenResponse,
    RefreshTokenRequest, MessageResponse
)
from application.services import AuthService
from api.dependencies import get_auth_service, get_current_user


router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Register a new user

    - **username**: Unique username (3-50 characters, alphanumeric with _ and .)
    - **email**: Valid email address
    - **password**: Strong password (min 8 characters, must contain uppercase, lowercase, and digit)
    - **full_name**: Optional full name
    - **phone_number**: Optional phone number
    """
    access_token, refresh_token, expires_in = await auth_service.register(
        username=user_data.username,
        email=user_data.email,
        password=user_data.password,
        full_name=user_data.full_name,
        phone_number=user_data.phone_number
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: UserLogin,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Login with username/email and password

    - **username_or_email**: Username or email address
    - **password**: User password
    """
    access_token, refresh_token, expires_in = await auth_service.login(
        username_or_email=credentials.username_or_email,
        password=credentials.password
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Refresh access token using refresh token

    - **refresh_token**: Valid refresh token
    """
    access_token, refresh_token, expires_in = await auth_service.refresh_access_token(
        refresh_token_str=request.refresh_token
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    refresh_token_data: RefreshTokenRequest,
    current_user: dict = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Logout and revoke refresh token

    - **refresh_token**: Refresh token to revoke
    """
    await auth_service.logout(
        refresh_token_str=refresh_token_data.refresh_token,
        user_id=current_user["id"]
    )

    return MessageResponse(message="Successfully logged out")
