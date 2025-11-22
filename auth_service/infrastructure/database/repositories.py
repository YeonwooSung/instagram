"""
Repository implementations - Data access layer
"""
from typing import Optional, Dict, Any
from datetime import datetime
import asyncpg

from domain.models import User, RefreshToken
from domain.repositories import IUserRepository, IRefreshTokenRepository
from .connection import DatabaseConnection


class UserRepository(IUserRepository):
    """User repository implementation using PostgreSQL"""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def _row_to_user(self, row: Optional[asyncpg.Record]) -> Optional[User]:
        """Convert database row to User model"""
        if not row:
            return None
        return User(**dict(row))

    async def create(self, username: str, email: str, password_hash: str,
                    full_name: Optional[str] = None,
                    phone_number: Optional[str] = None) -> User:
        """Create a new user"""
        row = await self.db.fetch_one(
            """
            INSERT INTO users (username, email, password_hash, full_name, phone_number)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, username, email, password_hash, full_name, bio, profile_image_url,
                      website, phone_number, is_verified, is_private, is_active,
                      follower_count, following_count, post_count,
                      created_at, updated_at, last_seen_at
            """,
            username,
            email,
            password_hash,
            full_name,
            phone_number
        )
        return self._row_to_user(row)

    async def find_by_id(self, user_id: int) -> Optional[User]:
        """Find user by ID"""
        row = await self.db.fetch_one(
            """
            SELECT id, username, email, password_hash, full_name, bio, profile_image_url,
                   website, phone_number, is_verified, is_private, is_active,
                   follower_count, following_count, post_count,
                   created_at, updated_at, last_seen_at
            FROM users
            WHERE id = $1
            """,
            user_id
        )
        return self._row_to_user(row)

    async def find_by_username(self, username: str) -> Optional[User]:
        """Find user by username"""
        row = await self.db.fetch_one(
            """
            SELECT id, username, email, password_hash, full_name, bio, profile_image_url,
                   website, phone_number, is_verified, is_private, is_active,
                   follower_count, following_count, post_count,
                   created_at, updated_at, last_seen_at
            FROM users
            WHERE username = $1 AND is_active = true
            """,
            username.lower()
        )
        return self._row_to_user(row)

    async def find_by_email(self, email: str) -> Optional[User]:
        """Find user by email"""
        row = await self.db.fetch_one(
            """
            SELECT id, username, email, password_hash, full_name, bio, profile_image_url,
                   website, phone_number, is_verified, is_private, is_active,
                   follower_count, following_count, post_count,
                   created_at, updated_at, last_seen_at
            FROM users
            WHERE email = $1 AND is_active = true
            """,
            email.lower()
        )
        return self._row_to_user(row)

    async def find_by_username_or_email(self, username_or_email: str) -> Optional[User]:
        """Find user by username or email"""
        row = await self.db.fetch_one(
            """
            SELECT id, username, email, password_hash, full_name, bio, profile_image_url,
                   website, phone_number, is_verified, is_private, is_active,
                   follower_count, following_count, post_count,
                   created_at, updated_at, last_seen_at
            FROM users
            WHERE (username = $1 OR email = $1) AND is_active = true
            """,
            username_or_email.lower()
        )
        return self._row_to_user(row)

    async def exists_by_username_or_email(self, username: str, email: str) -> bool:
        """Check if user exists by username or email"""
        row = await self.db.fetch_one(
            "SELECT id FROM users WHERE username = $1 OR email = $2",
            username,
            email
        )
        return row is not None

    async def update(self, user_id: int, updates: Dict[str, Any]) -> User:
        """Update user information"""
        # Build dynamic update query
        update_fields = []
        values = []
        param_count = 1

        for field, value in updates.items():
            update_fields.append(f"{field} = ${param_count}")
            values.append(value)
            param_count += 1

        # Add updated_at
        update_fields.append(f"updated_at = ${param_count}")
        values.append(datetime.utcnow())
        param_count += 1

        # Add user_id
        values.append(user_id)

        query = f"""
            UPDATE users
            SET {", ".join(update_fields)}
            WHERE id = ${param_count}
            RETURNING id, username, email, password_hash, full_name, bio, profile_image_url,
                      website, phone_number, is_verified, is_private, is_active,
                      follower_count, following_count, post_count,
                      created_at, updated_at, last_seen_at
        """

        row = await self.db.fetch_one(query, *values)
        return self._row_to_user(row)

    async def update_password(self, user_id: int, password_hash: str) -> None:
        """Update user password"""
        await self.db.execute(
            "UPDATE users SET password_hash = $1, updated_at = $2 WHERE id = $3",
            password_hash,
            datetime.utcnow(),
            user_id
        )

    async def update_last_seen(self, user_id: int) -> None:
        """Update user's last seen timestamp"""
        await self.db.execute(
            "UPDATE users SET last_seen_at = $1 WHERE id = $2",
            datetime.utcnow(),
            user_id
        )

    async def deactivate(self, user_id: int) -> None:
        """Deactivate user account"""
        await self.db.execute(
            "UPDATE users SET is_active = false, updated_at = $1 WHERE id = $2",
            datetime.utcnow(),
            user_id
        )


class RefreshTokenRepository(IRefreshTokenRepository):
    """Refresh token repository implementation using PostgreSQL"""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def _row_to_refresh_token(self, row: Optional[asyncpg.Record]) -> Optional[RefreshToken]:
        """Convert database row to RefreshToken model"""
        if not row:
            return None
        return RefreshToken(**dict(row))

    async def create(self, user_id: int, token_hash: str, expires_at: datetime) -> RefreshToken:
        """Create a new refresh token"""
        row = await self.db.fetch_one(
            """
            INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
            VALUES ($1, $2, $3)
            RETURNING id, user_id, token_hash, expires_at, is_revoked, created_at, last_used_at
            """,
            user_id,
            token_hash,
            expires_at
        )
        return self._row_to_refresh_token(row)

    async def find_by_token_hash(self, token_hash: str, user_id: int) -> Optional[RefreshToken]:
        """Find refresh token by hash and user ID"""
        row = await self.db.fetch_one(
            """
            SELECT id, user_id, token_hash, expires_at, is_revoked, created_at, last_used_at
            FROM refresh_tokens
            WHERE token_hash = $1 AND user_id = $2
            """,
            token_hash,
            user_id
        )
        return self._row_to_refresh_token(row)

    async def update_last_used(self, token_id: int) -> None:
        """Update token's last used timestamp"""
        await self.db.execute(
            "UPDATE refresh_tokens SET last_used_at = $1 WHERE id = $2",
            datetime.utcnow(),
            token_id
        )

    async def revoke(self, token_hash: str, user_id: int) -> None:
        """Revoke a specific refresh token"""
        await self.db.execute(
            """
            UPDATE refresh_tokens
            SET is_revoked = true
            WHERE token_hash = $1 AND user_id = $2
            """,
            token_hash,
            user_id
        )

    async def revoke_all_for_user(self, user_id: int) -> None:
        """Revoke all refresh tokens for a user"""
        await self.db.execute(
            "UPDATE refresh_tokens SET is_revoked = true WHERE user_id = $1",
            user_id
        )
