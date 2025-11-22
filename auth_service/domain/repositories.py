"""
Repository interfaces - Define contracts for data access
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from datetime import datetime
from .models import User, RefreshToken


class IUserRepository(ABC):
    """User repository interface"""

    @abstractmethod
    async def create(self, username: str, email: str, password_hash: str,
                    full_name: Optional[str] = None,
                    phone_number: Optional[str] = None) -> User:
        """Create a new user"""
        pass

    @abstractmethod
    async def find_by_id(self, user_id: int) -> Optional[User]:
        """Find user by ID"""
        pass

    @abstractmethod
    async def find_by_username(self, username: str) -> Optional[User]:
        """Find user by username"""
        pass

    @abstractmethod
    async def find_by_email(self, email: str) -> Optional[User]:
        """Find user by email"""
        pass

    @abstractmethod
    async def find_by_username_or_email(self, username_or_email: str) -> Optional[User]:
        """Find user by username or email"""
        pass

    @abstractmethod
    async def exists_by_username_or_email(self, username: str, email: str) -> bool:
        """Check if user exists by username or email"""
        pass

    @abstractmethod
    async def update(self, user_id: int, updates: Dict[str, Any]) -> User:
        """Update user information"""
        pass

    @abstractmethod
    async def update_password(self, user_id: int, password_hash: str) -> None:
        """Update user password"""
        pass

    @abstractmethod
    async def update_last_seen(self, user_id: int) -> None:
        """Update user's last seen timestamp"""
        pass

    @abstractmethod
    async def deactivate(self, user_id: int) -> None:
        """Deactivate user account"""
        pass


class IRefreshTokenRepository(ABC):
    """Refresh token repository interface"""

    @abstractmethod
    async def create(self, user_id: int, token_hash: str, expires_at: datetime) -> RefreshToken:
        """Create a new refresh token"""
        pass

    @abstractmethod
    async def find_by_token_hash(self, token_hash: str, user_id: int) -> Optional[RefreshToken]:
        """Find refresh token by hash and user ID"""
        pass

    @abstractmethod
    async def update_last_used(self, token_id: int) -> None:
        """Update token's last used timestamp"""
        pass

    @abstractmethod
    async def revoke(self, token_hash: str, user_id: int) -> None:
        """Revoke a specific refresh token"""
        pass

    @abstractmethod
    async def revoke_all_for_user(self, user_id: int) -> None:
        """Revoke all refresh tokens for a user"""
        pass
