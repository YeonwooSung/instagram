"""
FastAPI dependencies
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthCredential
from typing import Optional, Dict, Any

from infrastructure.database.connection import db_connection, DatabaseConnection
from infrastructure.database.repositories import UserRepository, RefreshTokenRepository
from application.services import AuthService, UserService
from infrastructure.auth import decode_token


# Security scheme
security = HTTPBearer(auto_error=False)


async def get_db_connection_dep() -> DatabaseConnection:
    """Get database connection dependency"""
    return db_connection


async def get_user_repository(db: DatabaseConnection = Depends(get_db_connection_dep)) -> UserRepository:
    """Get user repository dependency"""
    return UserRepository(db)


async def get_token_repository(db: DatabaseConnection = Depends(get_db_connection_dep)) -> RefreshTokenRepository:
    """Get refresh token repository dependency"""
    return RefreshTokenRepository(db)


async def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repository),
    token_repo: RefreshTokenRepository = Depends(get_token_repository)
) -> AuthService:
    """Get auth service dependency"""
    return AuthService(user_repo, token_repo)


async def get_user_service(
    user_repo: UserRepository = Depends(get_user_repository),
    token_repo: RefreshTokenRepository = Depends(get_token_repository)
) -> UserService:
    """Get user service dependency"""
    return UserService(user_repo, token_repo)


async def get_current_user(
    credentials: HTTPAuthCredential = Depends(security),
    user_repo: UserRepository = Depends(get_user_repository)
) -> Dict[str, Any]:
    """
    Get current authenticated user from JWT token

    Raises:
        HTTPException: If token is invalid or user not found
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Decode token
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user ID from token
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from database
    user = await user_repo.find_by_id(int(user_id))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Return user as dict (without password hash)
    user_dict = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "bio": user.bio,
        "profile_image_url": user.profile_image_url,
        "website": user.website,
        "phone_number": user.phone_number,
        "is_verified": user.is_verified,
        "is_private": user.is_private,
        "is_active": user.is_active,
        "follower_count": user.follower_count,
        "following_count": user.following_count,
        "post_count": user.post_count,
        "created_at": user.created_at,
        "last_seen_at": user.last_seen_at
    }

    return user_dict


async def get_current_user_optional(
    credentials: HTTPAuthCredential = Depends(security),
    user_repo: UserRepository = Depends(get_user_repository)
) -> Optional[Dict[str, Any]]:
    """
    Get current authenticated user from JWT token (optional)

    Returns None if not authenticated instead of raising exception
    """
    if not credentials:
        return None

    try:
        return await get_current_user(credentials, user_repo)
    except HTTPException:
        return None
