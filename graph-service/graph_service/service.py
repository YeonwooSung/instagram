"""
Graph Service business logic
"""
from typing import List, Optional, Tuple
from fastapi import HTTPException, status
import logging

from .database import Database
from .cache import RedisCache
from .kafka_producer import KafkaProducerManager
from .dependencies import check_user_is_private
from .schemas import (
    FollowStatus,
    RelationshipType,
    FollowResponse,
    UserFollowInfo,
    RelationshipResponse,
    GraphStatsResponse,
)
from .config import settings

logger = logging.getLogger(__name__)


class GraphService:
    """Business logic for graph operations"""

    def __init__(self, db: Database, cache: RedisCache, kafka: KafkaProducerManager):
        self.db = db
        self.cache = cache
        self.kafka = kafka

    async def follow_user(
        self, follower_id: int, following_id: int
    ) -> FollowResponse:
        """
        Follow a user

        Args:
            follower_id: User who is following
            following_id: User to be followed

        Returns:
            FollowResponse with status

        Raises:
            HTTPException: If follow operation fails
        """
        # Validate: Can't follow yourself
        if follower_id == following_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot follow yourself",
            )

        # Check if already following
        existing = await self.db.get_follow_relationship(follower_id, following_id)
        if existing:
            if existing["status"] == "accepted":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You are already following this user",
                )
            elif existing["status"] == "pending":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Follow request already pending",
                )

        # Check following limit
        following_count = await self.db.get_following_count(follower_id)
        if following_count >= settings.MAX_FOLLOWING_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You cannot follow more than {settings.MAX_FOLLOWING_LIMIT} users",
            )

        # Check if target user is private
        is_private = await check_user_is_private(following_id)

        # Determine status based on account privacy
        follow_status = FollowStatus.PENDING if is_private else FollowStatus.ACCEPTED

        # Create follow relationship
        success = await self.db.create_follow(
            follower_id, following_id, follow_status.value
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create follow relationship",
            )

        # Invalidate cache
        await self.cache.invalidate_user_cache(follower_id)
        await self.cache.invalidate_user_cache(following_id)
        await self.cache.invalidate_relationship_cache(follower_id, following_id)

        # Publish Kafka event
        await self.kafka.publish_follow_event(
            follower_id, following_id, follow_status.value
        )

        # Prepare response message
        if follow_status == FollowStatus.PENDING:
            message = "Follow request sent"
        else:
            message = "Successfully followed user"

        return FollowResponse(
            success=True, status=follow_status, message=message
        )

    async def unfollow_user(
        self, follower_id: int, following_id: int
    ) -> FollowResponse:
        """
        Unfollow a user

        Args:
            follower_id: User who is unfollowing
            following_id: User to be unfollowed

        Returns:
            FollowResponse with status

        Raises:
            HTTPException: If unfollow operation fails
        """
        # Check if following exists
        existing = await self.db.get_follow_relationship(follower_id, following_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You are not following this user",
            )

        # Delete follow relationship
        success = await self.db.delete_follow(follower_id, following_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to unfollow user",
            )

        # Invalidate cache
        await self.cache.invalidate_user_cache(follower_id)
        await self.cache.invalidate_user_cache(following_id)
        await self.cache.invalidate_relationship_cache(follower_id, following_id)

        # Publish Kafka event
        await self.kafka.publish_unfollow_event(follower_id, following_id)

        return FollowResponse(
            success=True,
            status=FollowStatus.ACCEPTED,
            message="Successfully unfollowed user",
        )

    async def get_followers(
        self, user_id: int, page: int = 1, page_size: int = 20
    ) -> Tuple[List[UserFollowInfo], int, bool]:
        """
        Get user's followers

        Args:
            user_id: User ID
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            Tuple of (followers list, total count, has_more)
        """
        # Validate pagination
        page = max(1, page)
        page_size = min(page_size, settings.MAX_PAGE_SIZE)
        offset = (page - 1) * page_size

        # Get from database
        followers_data = await self.db.get_followers(
            user_id, limit=page_size + 1, offset=offset
        )

        # Check if there are more results
        has_more = len(followers_data) > page_size
        if has_more:
            followers_data = followers_data[:page_size]

        # Convert to response model
        followers = [
            UserFollowInfo(user_id=row["follower_id"], created_at=row["created_at"])
            for row in followers_data
        ]

        # Get total count
        total = await self.db.get_follower_count(user_id)

        return followers, total, has_more

    async def get_following(
        self, user_id: int, page: int = 1, page_size: int = 20
    ) -> Tuple[List[UserFollowInfo], int, bool]:
        """
        Get users that user is following

        Args:
            user_id: User ID
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            Tuple of (following list, total count, has_more)
        """
        # Validate pagination
        page = max(1, page)
        page_size = min(page_size, settings.MAX_PAGE_SIZE)
        offset = (page - 1) * page_size

        # Get from database
        following_data = await self.db.get_following(
            user_id, limit=page_size + 1, offset=offset
        )

        # Check if there are more results
        has_more = len(following_data) > page_size
        if has_more:
            following_data = following_data[:page_size]

        # Convert to response model
        following = [
            UserFollowInfo(user_id=row["following_id"], created_at=row["created_at"])
            for row in following_data
        ]

        # Get total count
        total = await self.db.get_following_count(user_id)

        return following, total, has_more

    async def get_relationship(
        self, current_user_id: int, target_user_id: int
    ) -> RelationshipResponse:
        """
        Get relationship between current user and target user

        Args:
            current_user_id: Current user ID
            target_user_id: Target user ID

        Returns:
            RelationshipResponse with relationship details
        """
        # Check cache first
        cached = await self.cache.get_relationship(current_user_id, target_user_id)
        if cached:
            return RelationshipResponse(**cached)

        # Get relationships from database
        following = await self.db.get_follow_relationship(
            current_user_id, target_user_id
        )
        followed_by = await self.db.get_follow_relationship(
            target_user_id, current_user_id
        )

        # Determine relationship type
        is_following = following is not None and following["status"] == "accepted"
        is_followed_by = followed_by is not None and followed_by["status"] == "accepted"
        is_pending = following is not None and following["status"] == "pending"
        is_requested = followed_by is not None and followed_by["status"] == "pending"
        is_mutual = is_following and is_followed_by

        if is_mutual:
            relationship = RelationshipType.MUTUAL
        elif is_following:
            relationship = RelationshipType.FOLLOWING
        elif is_followed_by:
            relationship = RelationshipType.FOLLOWED_BY
        elif is_pending:
            relationship = RelationshipType.PENDING
        elif is_requested:
            relationship = RelationshipType.REQUESTED
        else:
            relationship = RelationshipType.NONE

        response = RelationshipResponse(
            user_id=current_user_id,
            target_user_id=target_user_id,
            relationship=relationship,
            is_following=is_following,
            is_followed_by=is_followed_by,
            is_mutual=is_mutual,
            is_pending=is_pending,
            is_requested=is_requested,
        )

        # Cache the result
        await self.cache.set_relationship(
            current_user_id, target_user_id, response.dict()
        )

        return response

    async def get_user_stats(self, user_id: int) -> GraphStatsResponse:
        """
        Get user's graph statistics

        Args:
            user_id: User ID

        Returns:
            GraphStatsResponse with statistics
        """
        # Check cache first
        cached = await self.cache.get_stats(user_id)
        if cached:
            return GraphStatsResponse(**cached)

        # Get counts from database
        follower_count = await self.db.get_follower_count(user_id)
        following_count = await self.db.get_following_count(user_id)
        pending_count = await self.db.get_follower_count(user_id, status="pending")

        stats = GraphStatsResponse(
            user_id=user_id,
            follower_count=follower_count,
            following_count=following_count,
            pending_requests_count=pending_count,
        )

        # Cache the result
        await self.cache.set_stats(user_id, stats.dict())

        return stats

    async def get_pending_requests(
        self, user_id: int, page: int = 1, page_size: int = 20
    ) -> Tuple[List[UserFollowInfo], int, bool]:
        """
        Get pending follow requests

        Args:
            user_id: User ID
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            Tuple of (requests list, total count, has_more)
        """
        # Validate pagination
        page = max(1, page)
        page_size = min(page_size, settings.MAX_PAGE_SIZE)
        offset = (page - 1) * page_size

        # Get from database
        requests_data = await self.db.get_pending_requests(
            user_id, limit=page_size + 1, offset=offset
        )

        # Check if there are more results
        has_more = len(requests_data) > page_size
        if has_more:
            requests_data = requests_data[:page_size]

        # Convert to response model
        requests = [
            UserFollowInfo(user_id=row["follower_id"], created_at=row["created_at"])
            for row in requests_data
        ]

        # Get total count
        total = await self.db.get_follower_count(user_id, status="pending")

        return requests, total, has_more

    async def accept_follow_request(
        self, user_id: int, follower_id: int
    ) -> FollowResponse:
        """
        Accept follow request

        Args:
            user_id: User accepting the request
            follower_id: User who sent the request

        Returns:
            FollowResponse with status
        """
        # Check if request exists
        existing = await self.db.get_follow_relationship(follower_id, user_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Follow request not found",
            )

        if existing["status"] != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Follow request is not pending",
            )

        # Update status to accepted
        success = await self.db.update_follow_status(
            follower_id, user_id, FollowStatus.ACCEPTED.value
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to accept follow request",
            )

        # Invalidate cache
        await self.cache.invalidate_user_cache(follower_id)
        await self.cache.invalidate_user_cache(user_id)
        await self.cache.invalidate_relationship_cache(follower_id, user_id)

        # Publish Kafka event
        await self.kafka.publish_follow_request_accepted_event(follower_id, user_id)

        return FollowResponse(
            success=True,
            status=FollowStatus.ACCEPTED,
            message="Follow request accepted",
        )

    async def reject_follow_request(
        self, user_id: int, follower_id: int
    ) -> FollowResponse:
        """
        Reject follow request

        Args:
            user_id: User rejecting the request
            follower_id: User who sent the request

        Returns:
            FollowResponse with status
        """
        # Check if request exists
        existing = await self.db.get_follow_relationship(follower_id, user_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Follow request not found",
            )

        if existing["status"] != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Follow request is not pending",
            )

        # Delete the request
        success = await self.db.delete_follow(follower_id, user_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to reject follow request",
            )

        # Invalidate cache
        await self.cache.invalidate_user_cache(follower_id)
        await self.cache.invalidate_user_cache(user_id)
        await self.cache.invalidate_relationship_cache(follower_id, user_id)

        # Publish Kafka event
        await self.kafka.publish_follow_request_rejected_event(follower_id, user_id)

        return FollowResponse(
            success=True,
            status=FollowStatus.REJECTED,
            message="Follow request rejected",
        )

    async def get_mutual_followers(
        self, user_id: int, other_user_id: int, limit: int = 20
    ) -> List[int]:
        """
        Get mutual followers between two users

        Args:
            user_id: First user ID
            other_user_id: Second user ID
            limit: Maximum number of results

        Returns:
            List of mutual follower user IDs
        """
        return await self.db.get_mutual_followers(user_id, other_user_id, limit)

    async def get_follow_suggestions(
        self, user_id: int, limit: int = 10
    ) -> List[int]:
        """
        Get follow suggestions (friends of friends)

        Args:
            user_id: User ID
            limit: Maximum number of suggestions

        Returns:
            List of suggested user IDs
        """
        return await self.db.get_follow_suggestions(user_id, limit)
