"""
User routes
"""
from fastapi import APIRouter, Depends, status
from typing import Optional

from schemas import UserProfile, UpdateProfile, ChangePassword, MessageResponse
from application.services import UserService
from api.dependencies import get_user_service, get_current_user, get_current_user_optional


router = APIRouter(prefix="/api/v1/users", tags=["Users"])


@router.get("/me", response_model=UserProfile)
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    """
    Get current user's profile

    Requires authentication.
    """
    return UserProfile(**current_user)


@router.get("/{username}", response_model=UserProfile)
async def get_user_profile(
    username: str,
    user_service: UserService = Depends(get_user_service),
    current_user: Optional[dict] = Depends(get_current_user_optional)
):
    """
    Get user profile by username

    Public endpoint (authentication optional).
    """
    requester_id = current_user["id"] if current_user else None
    user = await user_service.get_user_by_username(username, requester_id)

    return UserProfile(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        bio=user.bio,
        profile_image_url=user.profile_image_url,
        website=user.website,
        phone_number=user.phone_number,
        is_verified=user.is_verified,
        is_private=user.is_private,
        is_active=user.is_active,
        follower_count=user.follower_count,
        following_count=user.following_count,
        post_count=user.post_count,
        created_at=user.created_at,
        last_seen_at=user.last_seen_at
    )


@router.put("/me", response_model=UserProfile)
async def update_my_profile(
    profile_data: UpdateProfile,
    current_user: dict = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service)
):
    """
    Update current user's profile

    Requires authentication.
    """
    # Build updates dict from non-None fields
    updates = {}
    if profile_data.full_name is not None:
        updates["full_name"] = profile_data.full_name
    if profile_data.bio is not None:
        updates["bio"] = profile_data.bio
    if profile_data.website is not None:
        updates["website"] = profile_data.website
    if profile_data.phone_number is not None:
        updates["phone_number"] = profile_data.phone_number
    if profile_data.is_private is not None:
        updates["is_private"] = profile_data.is_private

    updated_user = await user_service.update_profile(current_user["id"], updates)

    return UserProfile(
        id=updated_user.id,
        username=updated_user.username,
        email=updated_user.email,
        full_name=updated_user.full_name,
        bio=updated_user.bio,
        profile_image_url=updated_user.profile_image_url,
        website=updated_user.website,
        phone_number=updated_user.phone_number,
        is_verified=updated_user.is_verified,
        is_private=updated_user.is_private,
        is_active=updated_user.is_active,
        follower_count=updated_user.follower_count,
        following_count=updated_user.following_count,
        post_count=updated_user.post_count,
        created_at=updated_user.created_at,
        last_seen_at=updated_user.last_seen_at
    )


@router.post("/me/change-password", response_model=MessageResponse)
async def change_password(
    password_data: ChangePassword,
    current_user: dict = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service)
):
    """
    Change current user's password

    Requires authentication.
    """
    await user_service.change_password(
        user_id=current_user["id"],
        old_password=password_data.old_password,
        new_password=password_data.new_password
    )

    return MessageResponse(message="Password changed successfully. Please login again.")


@router.delete("/me", response_model=MessageResponse)
async def deactivate_account(
    current_user: dict = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service)
):
    """
    Deactivate current user's account

    Requires authentication.
    """
    await user_service.deactivate_account(current_user["id"])

    return MessageResponse(message="Account deactivated successfully")
