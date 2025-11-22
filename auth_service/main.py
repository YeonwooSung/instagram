"""
Instagram Clone - Auth Service
Main FastAPI application with JWT authentication
"""
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import timedelta, datetime
import asyncpg

from config import settings
from database import db, get_db, Database
from schemas import (
    UserRegister, UserLogin, TokenResponse, RefreshTokenRequest,
    UserProfile, UpdateProfile, ChangePassword, MessageResponse, ErrorResponse
)
from auth import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    decode_token, generate_token_hash, validate_password_strength
)
from dependencies import get_current_user, get_current_user_optional


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    print("🚀 Starting Auth Service...")
    await db.connect()
    print(f"✓ Auth Service started on {settings.APP_NAME} v{settings.APP_VERSION}")

    yield

    # Shutdown
    print("👋 Shutting down Auth Service...")
    await db.disconnect()


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Authentication service for Instagram clone with JWT tokens",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)


@app.get("/", tags=["Health"])
async def root():
    """Root endpoint"""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/api/v1/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED, tags=["Authentication"])
async def register(user_data: UserRegister, database: Database = Depends(get_db)):
    """
    Register a new user

    - **username**: Unique username (3-50 characters, alphanumeric with _ and .)
    - **email**: Valid email address
    - **password**: Strong password (min 8 characters, must contain uppercase, lowercase, and digit)
    - **full_name**: Optional full name
    - **phone_number**: Optional phone number
    """
    # Validate password strength
    is_valid, error_msg = validate_password_strength(user_data.password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )

    # Check if username already exists
    existing_user = await database.fetch_one(
        "SELECT id FROM users WHERE username = $1 OR email = $2",
        user_data.username,
        user_data.email
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )

    # Hash password
    hashed_password = hash_password(user_data.password)

    # Insert user into database
    try:
        user = await database.fetch_one(
            """
            INSERT INTO users (username, email, password_hash, full_name, phone_number)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, username, email, created_at
            """,
            user_data.username,
            user_data.email,
            hashed_password,
            user_data.full_name,
            user_data.phone_number
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
    access_token = create_access_token(data={"sub": str(user["id"]), "username": user["username"]})
    refresh_token = create_refresh_token(data={"sub": str(user["id"])})

    # Store refresh token
    token_hash = generate_token_hash(refresh_token)
    expires_at = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    await database.execute(
        """
        INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
        VALUES ($1, $2, $3)
        """,
        user["id"],
        token_hash,
        expires_at
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@app.post("/api/v1/auth/login", response_model=TokenResponse, tags=["Authentication"])
async def login(credentials: UserLogin, database: Database = Depends(get_db)):
    """
    Login with username/email and password

    - **username_or_email**: Username or email address
    - **password**: User password
    """
    # Find user by username or email
    user = await database.fetch_one(
        """
        SELECT id, username, email, password_hash, is_active
        FROM users
        WHERE (username = $1 OR email = $1) AND is_active = true
        """,
        credentials.username_or_email.lower()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    # Verify password
    if not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    # Update last seen
    await database.execute(
        "UPDATE users SET last_seen_at = $1 WHERE id = $2",
        datetime.utcnow(),
        user["id"]
    )

    # Create tokens
    access_token = create_access_token(data={"sub": str(user["id"]), "username": user["username"]})
    refresh_token = create_refresh_token(data={"sub": str(user["id"])})

    # Store refresh token
    token_hash = generate_token_hash(refresh_token)
    expires_at = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    await database.execute(
        """
        INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
        VALUES ($1, $2, $3)
        """,
        user["id"],
        token_hash,
        expires_at
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@app.post("/api/v1/auth/refresh", response_model=TokenResponse, tags=["Authentication"])
async def refresh_token(request: RefreshTokenRequest, database: Database = Depends(get_db)):
    """
    Refresh access token using refresh token

    - **refresh_token**: Valid refresh token
    """
    # Decode refresh token
    payload = decode_token(request.refresh_token)
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
    token_hash = generate_token_hash(request.refresh_token)
    stored_token = await database.fetch_one(
        """
        SELECT id, user_id, expires_at, is_revoked
        FROM refresh_tokens
        WHERE token_hash = $1 AND user_id = $2
        """,
        token_hash,
        int(user_id)
    )

    if not stored_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    if stored_token["is_revoked"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked"
        )

    if stored_token["expires_at"] < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired"
        )

    # Get user info
    user = await database.fetch_one(
        "SELECT id, username, is_active FROM users WHERE id = $1",
        int(user_id)
    )

    if not user or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    # Update last used
    await database.execute(
        "UPDATE refresh_tokens SET last_used_at = $1 WHERE id = $2",
        datetime.utcnow(),
        stored_token["id"]
    )

    # Create new access token
    access_token = create_access_token(data={"sub": str(user["id"]), "username": user["username"]})

    return TokenResponse(
        access_token=access_token,
        refresh_token=request.refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@app.post("/api/v1/auth/logout", response_model=MessageResponse, tags=["Authentication"])
async def logout(
    refresh_token_data: RefreshTokenRequest,
    current_user: dict = Depends(get_current_user),
    database: Database = Depends(get_db)
):
    """
    Logout and revoke refresh token

    - **refresh_token**: Refresh token to revoke
    """
    token_hash = generate_token_hash(refresh_token_data.refresh_token)

    # Revoke refresh token
    result = await database.execute(
        """
        UPDATE refresh_tokens
        SET is_revoked = true
        WHERE token_hash = $1 AND user_id = $2
        """,
        token_hash,
        current_user["id"]
    )

    return MessageResponse(message="Successfully logged out")


@app.get("/api/v1/auth/me", response_model=UserProfile, tags=["Users"])
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    """
    Get current user's profile

    Requires authentication.
    """
    return UserProfile(**current_user)


@app.get("/api/v1/users/{username}", response_model=UserProfile, tags=["Users"])
async def get_user_profile(
    username: str,
    database: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user_optional)
):
    """
    Get user profile by username

    Public endpoint (authentication optional).
    """
    user = await database.fetch_one(
        """
        SELECT id, username, email, full_name, bio, profile_image_url,
               website, phone_number, is_verified, is_private, is_active,
               follower_count, following_count, post_count,
               created_at, last_seen_at
        FROM users
        WHERE username = $1 AND is_active = true
        """,
        username.lower()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Hide private information if not the owner
    user_dict = dict(user)
    if not current_user or current_user["id"] != user["id"]:
        user_dict["email"] = None
        user_dict["phone_number"] = None

    return UserProfile(**user_dict)


@app.put("/api/v1/users/me", response_model=UserProfile, tags=["Users"])
async def update_my_profile(
    profile_data: UpdateProfile,
    current_user: dict = Depends(get_current_user),
    database: Database = Depends(get_db)
):
    """
    Update current user's profile

    Requires authentication.
    """
    # Build update query dynamically
    updates = []
    values = []
    param_count = 1

    if profile_data.full_name is not None:
        updates.append(f"full_name = ${param_count}")
        values.append(profile_data.full_name)
        param_count += 1

    if profile_data.bio is not None:
        updates.append(f"bio = ${param_count}")
        values.append(profile_data.bio)
        param_count += 1

    if profile_data.website is not None:
        updates.append(f"website = ${param_count}")
        values.append(profile_data.website)
        param_count += 1

    if profile_data.phone_number is not None:
        updates.append(f"phone_number = ${param_count}")
        values.append(profile_data.phone_number)
        param_count += 1

    if profile_data.is_private is not None:
        updates.append(f"is_private = ${param_count}")
        values.append(profile_data.is_private)
        param_count += 1

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update"
        )

    updates.append(f"updated_at = ${param_count}")
    values.append(datetime.utcnow())
    param_count += 1

    values.append(current_user["id"])

    query = f"""
        UPDATE users
        SET {", ".join(updates)}
        WHERE id = ${param_count}
        RETURNING id, username, email, full_name, bio, profile_image_url,
                  website, phone_number, is_verified, is_private, is_active,
                  follower_count, following_count, post_count,
                  created_at, last_seen_at
    """

    updated_user = await database.fetch_one(query, *values)

    return UserProfile(**dict(updated_user))


@app.post("/api/v1/users/me/change-password", response_model=MessageResponse, tags=["Users"])
async def change_password(
    password_data: ChangePassword,
    current_user: dict = Depends(get_current_user),
    database: Database = Depends(get_db)
):
    """
    Change current user's password

    Requires authentication.
    """
    # Get current password hash
    user = await database.fetch_one(
        "SELECT password_hash FROM users WHERE id = $1",
        current_user["id"]
    )

    # Verify old password
    if not verify_password(password_data.old_password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid current password"
        )

    # Validate new password strength
    is_valid, error_msg = validate_password_strength(password_data.new_password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )

    # Hash new password
    new_password_hash = hash_password(password_data.new_password)

    # Update password
    await database.execute(
        "UPDATE users SET password_hash = $1, updated_at = $2 WHERE id = $3",
        new_password_hash,
        datetime.utcnow(),
        current_user["id"]
    )

    # Revoke all refresh tokens for security
    await database.execute(
        "UPDATE refresh_tokens SET is_revoked = true WHERE user_id = $1",
        current_user["id"]
    )

    return MessageResponse(message="Password changed successfully. Please login again.")


@app.delete("/api/v1/users/me", response_model=MessageResponse, tags=["Users"])
async def deactivate_account(
    current_user: dict = Depends(get_current_user),
    database: Database = Depends(get_db)
):
    """
    Deactivate current user's account

    Requires authentication.
    """
    await database.execute(
        "UPDATE users SET is_active = false, updated_at = $1 WHERE id = $2",
        datetime.utcnow(),
        current_user["id"]
    )

    # Revoke all refresh tokens
    await database.execute(
        "UPDATE refresh_tokens SET is_revoked = true WHERE user_id = $1",
        current_user["id"]
    )

    return MessageResponse(message="Account deactivated successfully")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True
    )
