"""
FastAPI dependencies for authentication and authorization
"""
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import logging

from .config import settings
from .schemas import User

logger = logging.getLogger(__name__)

security = HTTPBearer()


async def verify_token_with_auth_service(token: str) -> Optional[dict]:
    """
    Verify JWT token with Auth Service

    Args:
        token: JWT access token

    Returns:
        User data if token is valid, None otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{settings.AUTH_SERVICE_URL}/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(
                    f"Token verification failed: {response.status_code} - {response.text}"
                )
                return None

    except httpx.TimeoutException:
        logger.error("Auth service timeout during token verification")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable",
        )
    except httpx.ConnectError:
        logger.error("Failed to connect to auth service")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is unavailable",
        )
    except Exception as e:
        logger.error(f"Error verifying token with auth service: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during authentication",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """
    Get current authenticated user

    Dependency that verifies JWT token and returns user information

    Args:
        credentials: HTTP Bearer token from Authorization header

    Returns:
        User object with user information

    Raises:
        HTTPException: If token is invalid or user not found
    """
    token = credentials.credentials

    # Verify token with Auth Service
    user_data = await verify_token_with_auth_service(token)

    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # Convert to User model
        user = User(**user_data)

        # Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive",
            )

        return user

    except Exception as e:
        logger.error(f"Error parsing user data: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user data",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    ),
) -> Optional[User]:
    """
    Get current user if authenticated, None otherwise

    Optional authentication dependency for endpoints that work with or without auth

    Args:
        credentials: Optional HTTP Bearer token

    Returns:
        User object if authenticated, None otherwise
    """
    if not credentials:
        return None

    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


async def check_user_exists(user_id: int) -> bool:
    """
    Check if user exists via Auth Service

    Args:
        user_id: User ID to check

    Returns:
        True if user exists, False otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # This assumes Auth Service has a public endpoint to check user existence
            # You may need to adjust this based on actual Auth Service API
            response = await client.get(
                f"{settings.AUTH_SERVICE_URL}/api/v1/users/{user_id}/exists"
            )
            return response.status_code == 200

    except Exception as e:
        logger.error(f"Error checking user existence: {e}")
        # In case of error, assume user exists to avoid blocking operations
        return True


async def get_user_info(user_id: int) -> Optional[dict]:
    """
    Get user information from Auth Service

    Args:
        user_id: User ID

    Returns:
        User data if found, None otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{settings.AUTH_SERVICE_URL}/api/v1/users/{user_id}"
            )

            if response.status_code == 200:
                return response.json()
            else:
                return None

    except Exception as e:
        logger.error(f"Error getting user info: {e}")
        return None


async def check_user_is_private(user_id: int) -> bool:
    """
    Check if user account is private

    Args:
        user_id: User ID to check

    Returns:
        True if account is private, False otherwise
    """
    user_info = await get_user_info(user_id)
    if user_info:
        return user_info.get("is_private", False)
    return False
