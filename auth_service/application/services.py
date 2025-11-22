"""
Application services - Business logic layer
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from fastapi import HTTPException, status
import asyncpg

from domain.models import User, RefreshToken
from domain.repositories import IUserRepository, IRefreshTokenRepository
from infrastructure.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_token_hash,
    validate_password_strength
)
from config import settings


class AuthService:
    """Authentication service - handles authentication logic"""

    def __init__(
        self,
        user_repository: IUserRepository,
        token_repository: IRefreshTokenRepository
    ):
        self.user_repo = user_repository
        self.token_repo = token_repository

    async def register(
        self,
        username: str,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        phone_number: Optional[str] = None
    ) -> Tuple[str, str, int]:
        """
        Register a new user

        Returns:
            Tuple of (access_token, refresh_token, expires_in)
        """
        # Validate password strength
        is_valid, error_msg = validate_password_strength(password)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )

        # Check if username or email already exists
        if await self.user_repo.exists_by_username_or_email(username, email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username or email already registered"
            )

        # Hash password
        password_hash = hash_password(password)

        # Create user
        try:
            user = await self.user_repo.create(
                username=username,
                email=email,
                password_hash=password_hash,
                full_name=full_name,
                phone_number=phone_number
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username or email already registered"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create user: {str(e)}"
            )

        # Create tokens
        access_token = create_access_token(
            data={"sub": str(user.id), "username": user.username}
        )
        refresh_token = create_refresh_token(data={"sub": str(user.id)})

        # Store refresh token
        token_hash = generate_token_hash(refresh_token)
        expires_at = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        await self.token_repo.create(user.id, token_hash, expires_at)

        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        return access_token, refresh_token, expires_in

    async def login(self, username_or_email: str, password: str) -> Tuple[str, str, int]:
        """
        Login with username/email and password

        Returns:
            Tuple of (access_token, refresh_token, expires_in)
        """
        # Find user by username or email
        user = await self.user_repo.find_by_username_or_email(username_or_email)

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        # Verify password
        if not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        # Update last seen
        await self.user_repo.update_last_seen(user.id)

        # Create tokens
        access_token = create_access_token(
            data={"sub": str(user.id), "username": user.username}
        )
        refresh_token = create_refresh_token(data={"sub": str(user.id)})

        # Store refresh token
        token_hash = generate_token_hash(refresh_token)
        expires_at = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        await self.token_repo.create(user.id, token_hash, expires_at)

        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        return access_token, refresh_token, expires_in

    async def refresh_access_token(self, refresh_token_str: str) -> Tuple[str, str, int]:
        """
        Refresh access token using refresh token

        Returns:
            Tuple of (access_token, refresh_token, expires_in)
        """
        # Decode refresh token
        payload = decode_token(refresh_token_str)
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload"
            )

        # Verify refresh token in database
        token_hash = generate_token_hash(refresh_token_str)
        stored_token = await self.token_repo.find_by_token_hash(token_hash, int(user_id))

        if not stored_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )

        # Validate token
        if not stored_token.is_valid():
            if stored_token.is_revoked:
                detail = "Refresh token has been revoked"
            else:
                detail = "Refresh token has expired"
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=detail
            )

        # Get user info
        user = await self.user_repo.find_by_id(int(user_id))
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )

        # Update last used
        await self.token_repo.update_last_used(stored_token.id)

        # Create new access token
        access_token = create_access_token(
            data={"sub": str(user.id), "username": user.username}
        )

        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        return access_token, refresh_token_str, expires_in

    async def logout(self, refresh_token_str: str, user_id: int) -> None:
        """Logout and revoke refresh token"""
        token_hash = generate_token_hash(refresh_token_str)
        await self.token_repo.revoke(token_hash, user_id)

    async def verify_access_token(self, token: str) -> Dict[str, Any]:
        """Verify access token and return payload"""
        payload = decode_token(token)
        if not payload or payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )
        return payload


class UserService:
    """User service - handles user-related business logic"""

    def __init__(
        self,
        user_repository: IUserRepository,
        token_repository: IRefreshTokenRepository
    ):
        self.user_repo = user_repository
        self.token_repo = token_repository

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        return await self.user_repo.find_by_id(user_id)

    async def get_user_by_username(
        self,
        username: str,
        requester_id: Optional[int] = None
    ) -> User:
        """
        Get user profile by username

        Hides private information if requester is not the owner
        """
        user = await self.user_repo.find_by_username(username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Hide private information if not the owner
        if not user.can_view_private_info(requester_id):
            user.hide_private_info()

        return user

    async def update_profile(
        self,
        user_id: int,
        updates: Dict[str, Any]
    ) -> User:
        """Update user profile"""
        if not updates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update"
            )

        return await self.user_repo.update(user_id, updates)

    async def change_password(
        self,
        user_id: int,
        old_password: str,
        new_password: str
    ) -> None:
        """Change user password"""
        # Get current user
        user = await self.user_repo.find_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Verify old password
        if not verify_password(old_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid current password"
            )

        # Validate new password strength
        is_valid, error_msg = validate_password_strength(new_password)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )

        # Hash new password
        new_password_hash = hash_password(new_password)

        # Update password
        await self.user_repo.update_password(user_id, new_password_hash)

        # Revoke all refresh tokens for security
        await self.token_repo.revoke_all_for_user(user_id)

    async def deactivate_account(self, user_id: int) -> None:
        """Deactivate user account"""
        await self.user_repo.deactivate(user_id)
        await self.token_repo.revoke_all_for_user(user_id)
