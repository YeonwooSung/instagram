"""
FastAPI dependencies for authentication
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from auth import decode_token
from database import get_db, Database
import asyncpg


security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Database = Depends(get_db)
) -> dict:
    """
    Dependency to get the current authenticated user

    Args:
        credentials: HTTP Bearer token
        db: Database instance

    Returns:
        User data dictionary

    Raises:
        HTTPException: If token is invalid or user not found
    """
    token = credentials.credentials

    # Decode token
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check token type
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user ID from payload
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch user from database
    try:
        user = await db.fetch_one(
            """
            SELECT id, username, email, full_name, bio, profile_image_url,
                   website, phone_number, is_verified, is_private, is_active,
                   follower_count, following_count, post_count,
                   created_at, last_seen_at
            FROM users
            WHERE id = $1 AND is_active = true
            """,
            int(user_id)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return dict(user)


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: Database = Depends(get_db)
) -> Optional[dict]:
    """
    Dependency to get the current user if token is provided, None otherwise

    Args:
        credentials: Optional HTTP Bearer token
        db: Database instance

    Returns:
        User data dictionary or None
    """
    if not credentials:
        return None

    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None
