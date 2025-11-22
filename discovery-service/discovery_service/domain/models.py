"""
Domain models - Core business entities
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List


@dataclass
class SearchResult:
    """Search result domain model"""
    id: int
    type: str  # 'user', 'hashtag', 'post'
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    relevance_score: float = 0.0


@dataclass
class TrendingHashtag:
    """Trending hashtag domain model"""
    hashtag: str
    post_count: int
    growth_rate: float


@dataclass
class TrendingPost:
    """Trending post domain model"""
    post_id: int
    user_id: int
    engagement_score: float
    created_at: datetime


@dataclass
class DiscoveryFeed:
    """Discovery feed domain model"""
    posts: List[dict]
    has_more: bool
    next_offset: int
