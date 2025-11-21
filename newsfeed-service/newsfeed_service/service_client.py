"""
Service mesh client for inter-service communication
"""
import httpx
from typing import Optional, List, Dict, Any
import logging

from .config import settings

logger = logging.getLogger(__name__)


class ServiceClient:
    """HTTP client for communicating with other microservices"""

    def __init__(self):
        self.timeout = httpx.Timeout(10.0, connect=5.0)
        self.client: Optional[httpx.AsyncClient] = None

    async def start(self):
        """Initialize HTTP client"""
        self.client = httpx.AsyncClient(timeout=self.timeout)
        logger.info("Service client initialized")

    async def stop(self):
        """Close HTTP client"""
        if self.client:
            await self.client.aclose()
            logger.info("Service client closed")

    async def _make_request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Make HTTP request to a service"""
        if not self.client:
            logger.error("Service client not initialized")
            return None

        try:
            response = await self.client.request(
                method,
                url,
                headers=headers,
                **kwargs
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code} for {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Request failed for {url}: {e}")
            return None

    # Graph Service API
    async def get_following_ids(
        self,
        user_id: int,
        token: str
    ) -> List[int]:
        """Get list of user IDs that the user is following"""
        url = f"{settings.GRAPH_SERVICE_URL}/api/v1/graph/following/{user_id}"
        headers = {"Authorization": f"Bearer {token}"}

        all_following_ids = []
        page = 1
        has_more = True

        try:
            while has_more:
                response = await self._make_request(
                    "GET",
                    url,
                    headers=headers,
                    params={"page": page, "page_size": 100}
                )

                if not response:
                    break

                following_list = response.get("following", [])
                all_following_ids.extend([f["user_id"] for f in following_list])

                has_more = response.get("has_more", False)
                page += 1

            logger.info(f"Fetched {len(all_following_ids)} following IDs for user {user_id}")
            return all_following_ids

        except Exception as e:
            logger.error(f"Failed to fetch following list: {e}")
            return []

    async def get_follower_count(
        self,
        user_id: int,
        token: str
    ) -> int:
        """Get follower count for a user"""
        url = f"{settings.GRAPH_SERVICE_URL}/api/v1/graph/stats/{user_id}"
        headers = {"Authorization": f"Bearer {token}"}

        response = await self._make_request("GET", url, headers=headers)
        if response:
            return response.get("follower_count", 0)
        return 0

    async def get_followers_ids(
        self,
        user_id: int,
        token: str,
        limit: Optional[int] = None
    ) -> List[int]:
        """Get list of follower IDs for a user"""
        url = f"{settings.GRAPH_SERVICE_URL}/api/v1/graph/followers/{user_id}"
        headers = {"Authorization": f"Bearer {token}"}

        all_follower_ids = []
        page = 1
        has_more = True

        try:
            while has_more:
                response = await self._make_request(
                    "GET",
                    url,
                    headers=headers,
                    params={"page": page, "page_size": 100}
                )

                if not response:
                    break

                followers_list = response.get("followers", [])
                all_follower_ids.extend([f["user_id"] for f in followers_list])

                # Check if we've reached the limit
                if limit and len(all_follower_ids) >= limit:
                    all_follower_ids = all_follower_ids[:limit]
                    break

                has_more = response.get("has_more", False)
                page += 1

            logger.info(f"Fetched {len(all_follower_ids)} follower IDs for user {user_id}")
            return all_follower_ids

        except Exception as e:
            logger.error(f"Failed to fetch followers list: {e}")
            return []

    # Post Service API
    async def get_post(
        self,
        post_id: str,
        token: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get post details from post service"""
        url = f"{settings.POST_SERVICE_URL}/api/v1/posts/{post_id}"
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        return await self._make_request("GET", url, headers=headers)

    async def get_posts_batch(
        self,
        post_ids: List[str],
        token: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get multiple posts in batch"""
        # Since there's no batch endpoint, fetch individually
        # In production, you'd want to add a batch endpoint to post service
        posts = []
        for post_id in post_ids:
            post = await self.get_post(post_id, token)
            if post:
                posts.append(post)
        return posts

    async def get_user_posts(
        self,
        user_id: int,
        token: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get posts by a specific user"""
        url = f"{settings.POST_SERVICE_URL}/api/v1/posts"
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        response = await self._make_request(
            "GET",
            url,
            headers=headers,
            params={"user_id": user_id, "page_size": limit}
        )

        if response:
            return response.get("posts", [])
        return []

    # Auth Service API
    async def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token with auth service"""
        url = f"{settings.AUTH_SERVICE_URL}/api/v1/auth/verify"
        headers = {"Authorization": f"Bearer {token}"}

        return await self._make_request("GET", url, headers=headers)


# Global service client instance
service_client = ServiceClient()


async def get_service_client() -> ServiceClient:
    """Dependency for getting service client instance"""
    return service_client
