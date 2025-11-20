"""
Authentication dependencies for Media Service
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import httpx
from config import settings

security = HTTPBearer()


async def verify_token_with_auth_service(token: str) -> Optional[dict]:
    """
    Verify token with Auth Service

    Args:
        token: JWT access token

    Returns:
        User data or None if invalid
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.AUTH_SERVICE_URL}/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
                timeout=5.0
            )

            if response.status_code == 200:
                return response.json()
            else:
                return None

    except Exception as e:
        print(f"Failed to verify token with auth service: {e}")
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Dependency to get the current authenticated user

    Args:
        credentials: HTTP Bearer token

    Returns:
        User data dictionary

    Raises:
        HTTPException: If token is invalid
    """
    token = credentials.credentials

    user = await verify_token_with_auth_service(token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[dict]:
    """
    Dependency to get the current user if token is provided, None otherwise

    Args:
        credentials: Optional HTTP Bearer token

    Returns:
        User data dictionary or None
    """
    if not credentials:
        return None

    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None
