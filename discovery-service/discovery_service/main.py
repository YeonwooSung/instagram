"""
Instagram Clone - Discovery Service
Service for user and content discovery with search capabilities
"""
from typing import Optional
from fastapi import FastAPI, Request, Response, Depends, Query, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from contextlib import asynccontextmanager
import httpx
from bs4 import BeautifulSoup
import urllib.parse

# custom modules
from exceptions import UnicornException
from settings import Settings
from log import init_log
from cors import init_cors
from instrumentator import init_instrumentator
from zoo import init_kazoo
from config import Config
from database import db, get_db, Database
from auth import get_current_user, get_current_user_optional
from schemas import (
    UserSearchResult, UserSearchResponse, HashtagResult, HashtagSearchResponse,
    PostSummary, TrendingPostsResponse, RecommendedUsersResponse,
    LocationPostsResponse, DiscoveryFeedResponse
)


ZK_SCRAP_PATH = "/zk/services/scrap/nodes"

my_settings = Settings()
conf = Config(my_settings.CONFIG_PATH)

client = httpx.AsyncClient()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    print("🚀 Starting Discovery Service...")
    await db.connect()
    register_into_service_discovery(my_settings.APP_ENDPOINT)
    print("✓ Discovery Service started")

    yield

    # Shutdown
    print("👋 Shutting down Discovery Service...")
    await db.disconnect()


app = FastAPI(
    title="Instagram Discovery Service",
    version="1.0.0",
    description="Service for user and content discovery",
    lifespan=lifespan
)


init_log(app, conf.section("log")["path"])
init_cors(app)
init_instrumentator(app)
zk = init_kazoo(conf.section("zookeeper")["hosts"], None, None)


@app.exception_handler(UnicornException)
async def unicorn_exception_handler(request: Request, exc: UnicornException):
    return JSONResponse(
        status_code=exc.status,
        content={"code": exc.code, "message": exc.message},
    )


def register_into_service_discovery(endpoint):
    """Register service in ZooKeeper"""
    node_path = f"{ZK_SCRAP_PATH}/{endpoint}"
    if zk.exists(node_path):
        zk.delete(node_path)
    zk.create(node_path, ephemeral=True, makepath=True)


# =============================================================================
# Web Scraping API (Original functionality)
# =============================================================================

async def call_api(url: str):
    r = await client.get(url)
    return r.text


def parse_opengraph(body: str):
    soup = BeautifulSoup(body, 'html.parser')

    title = soup.find("meta",  {"property":"og:title"})
    url = soup.find("meta",  {"property":"og:url"})
    og_type = soup.find("meta",  {"property":"og:type"})
    image = soup.find("meta",  {"property":"og:image"})
    description = soup.find("meta",  {"property":"og:description"})
    author = soup.find("meta",  {"property":"og:article:author"})

    resp = {}
    scrap = {}
    scrap["title"] = title["content"] if title else None
    scrap["url"] = url["content"] if url else None
    scrap["type"] = og_type["content"] if og_type else None
    scrap["image"] = image["content"] if image else None
    scrap["description"] = description["content"] if description else None
    scrap["author"] = author["content"] if author else None
    resp["scrap"] = scrap

    return resp


@app.get("/api/v1/scrap/", tags=["Web Scraping"])
async def scrap(url: str):
    """
    Scrape OpenGraph metadata from URL

    - **url**: URL to scrape
    """
    try:
        url = urllib.parse.unquote(url)
        body = await call_api(url)
        return parse_opengraph(body)
    except Exception as e:
        raise UnicornException(status=400, code=-20000, message=str(e))


# =============================================================================
# User Discovery APIs
# =============================================================================

@app.get("/api/v1/discovery/users/search", response_model=UserSearchResponse, tags=["Discovery"])
async def search_users(
    q: str = Query(..., min_length=1, description="Search query"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    database: Database = Depends(get_db)
):
    """
    Search users by username or name

    - **q**: Search query (username or full name)
    - **page**: Page number (default: 1)
    - **page_size**: Items per page (default: 20, max: 100)
    """
    offset = (page - 1) * page_size
    search_pattern = f"%{q.lower()}%"

    # Count total results
    total_result = await database.fetch_one(
        """
        SELECT COUNT(*) as count FROM users
        WHERE (LOWER(username) LIKE $1 OR LOWER(full_name) LIKE $1)
        AND is_active = true
        """,
        search_pattern
    )

    # Get users
    users = await database.fetch_all(
        """
        SELECT id, username, full_name, bio, profile_image_url,
               is_verified, is_private, follower_count, following_count, post_count
        FROM users
        WHERE (LOWER(username) LIKE $1 OR LOWER(full_name) LIKE $1)
        AND is_active = true
        ORDER BY follower_count DESC, username ASC
        LIMIT $2 OFFSET $3
        """,
        search_pattern,
        page_size,
        offset
    )

    user_results = [UserSearchResult(**dict(user)) for user in users]

    return UserSearchResponse(
        users=user_results,
        total=total_result["count"],
        page=page,
        page_size=page_size
    )


@app.get("/api/v1/discovery/users/recommended", response_model=RecommendedUsersResponse, tags=["Discovery"])
async def get_recommended_users(
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user_optional),
    database: Database = Depends(get_db)
):
    """
    Get recommended users to follow

    - **limit**: Number of users to return (default: 10, max: 50)
    - Authentication optional (results personalized if authenticated)
    """
    if current_user:
        # Exclude users already followed by current user
        users = await database.fetch_all(
            """
            SELECT u.id, u.username, u.full_name, u.bio, u.profile_image_url,
                   u.is_verified, u.is_private, u.follower_count, u.following_count, u.post_count
            FROM users u
            WHERE u.is_active = true
            AND u.id != $1
            AND u.id NOT IN (
                SELECT following_id FROM user_follows WHERE follower_id = $1
            )
            ORDER BY u.follower_count DESC, u.post_count DESC
            LIMIT $2
            """,
            current_user["id"],
            limit
        )
        reason = "Based on popular accounts"
    else:
        # Return popular users
        users = await database.fetch_all(
            """
            SELECT id, username, full_name, bio, profile_image_url,
                   is_verified, is_private, follower_count, following_count, post_count
            FROM users
            WHERE is_active = true
            ORDER BY follower_count DESC, post_count DESC
            LIMIT $1
            """,
            limit
        )
        reason = "Popular accounts on Instagram"

    user_results = [UserSearchResult(**dict(user)) for user in users]

    return RecommendedUsersResponse(
        users=user_results,
        reason=reason
    )


# =============================================================================
# Hashtag Discovery APIs
# =============================================================================

@app.get("/api/v1/discovery/hashtags/search", response_model=HashtagSearchResponse, tags=["Discovery"])
async def search_hashtags(
    q: str = Query(..., min_length=1, description="Hashtag search query"),
    limit: int = Query(20, ge=1, le=100),
    database: Database = Depends(get_db)
):
    """
    Search hashtags

    - **q**: Hashtag search query (without #)
    - **limit**: Number of results (default: 20, max: 100)
    """
    search_pattern = f"%{q.lower()}%"

    # Search hashtags
    hashtags = await database.fetch_all(
        """
        SELECT id, name, post_count, created_at
        FROM hashtags
        WHERE LOWER(name) LIKE $1
        ORDER BY post_count DESC
        LIMIT $2
        """,
        search_pattern,
        limit
    )

    hashtag_results = [HashtagResult(**dict(tag)) for tag in hashtags]

    # Get preview posts for top hashtag
    posts_preview = []
    if hashtags:
        top_hashtag_id = hashtags[0]["id"]
        posts = await database.fetch_all(
            """
            SELECT p.id, p.user_id, u.username, u.profile_image_url,
                   p.caption, p.image_url, p.video_url,
                   p.like_count, p.comment_count, p.created_at
            FROM posts p
            JOIN post_hashtags ph ON p.id = ph.post_id
            JOIN users u ON p.user_id = u.id
            WHERE ph.hashtag_id = $1 AND p.is_hidden = false
            ORDER BY p.created_at DESC
            LIMIT 9
            """,
            top_hashtag_id
        )

        posts_preview = [
            PostSummary(
                **dict(post),
                user_profile_image=post["profile_image_url"]
            )
            for post in posts
        ]

    return HashtagSearchResponse(
        hashtags=hashtag_results,
        posts_preview=posts_preview,
        total=len(hashtag_results)
    )


@app.get("/api/v1/discovery/hashtags/{hashtag_name}/posts", response_model=TrendingPostsResponse, tags=["Discovery"])
async def get_hashtag_posts(
    hashtag_name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    database: Database = Depends(get_db)
):
    """
    Get posts for a specific hashtag

    - **hashtag_name**: Hashtag name (without #)
    - **page**: Page number (default: 1)
    - **page_size**: Items per page (default: 20, max: 100)
    """
    # Find hashtag
    hashtag = await database.fetch_one(
        "SELECT id FROM hashtags WHERE LOWER(name) = LOWER($1)",
        hashtag_name
    )

    if not hashtag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hashtag not found"
        )

    offset = (page - 1) * page_size

    # Count total posts
    total = await database.fetch_one(
        "SELECT COUNT(*) as count FROM post_hashtags WHERE hashtag_id = $1",
        hashtag["id"]
    )

    # Get posts
    posts = await database.fetch_all(
        """
        SELECT p.id, p.user_id, u.username, u.profile_image_url,
               p.caption, p.image_url, p.video_url,
               p.like_count, p.comment_count, p.created_at
        FROM posts p
        JOIN post_hashtags ph ON p.id = ph.post_id
        JOIN users u ON p.user_id = u.id
        WHERE ph.hashtag_id = $1 AND p.is_hidden = false
        ORDER BY p.created_at DESC
        LIMIT $2 OFFSET $3
        """,
        hashtag["id"],
        page_size,
        offset
    )

    post_results = [
        PostSummary(
            **dict(post),
            user_profile_image=post["profile_image_url"]
        )
        for post in posts
    ]

    return TrendingPostsResponse(
        posts=post_results,
        total=total["count"],
        page=page,
        page_size=page_size
    )


# =============================================================================
# Content Discovery APIs
# =============================================================================

@app.get("/api/v1/discovery/posts/trending", response_model=TrendingPostsResponse, tags=["Discovery"])
async def get_trending_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    database: Database = Depends(get_db)
):
    """
    Get trending/popular posts

    - **page**: Page number (default: 1)
    - **page_size**: Items per page (default: 20, max: 100)
    """
    offset = (page - 1) * page_size

    # Get trending posts (sorted by engagement)
    posts = await database.fetch_all(
        """
        SELECT p.id, p.user_id, u.username, u.profile_image_url,
               p.caption, p.image_url, p.video_url,
               p.like_count, p.comment_count, p.created_at,
               (p.like_count * 2 + p.comment_count * 3 + p.share_count * 5) as engagement_score
        FROM posts p
        JOIN users u ON p.user_id = u.id
        WHERE p.is_hidden = false
        AND p.created_at > NOW() - INTERVAL '7 days'
        ORDER BY engagement_score DESC, p.created_at DESC
        LIMIT $1 OFFSET $2
        """,
        page_size,
        offset
    )

    # Count total
    total = await database.fetch_one(
        """
        SELECT COUNT(*) as count FROM posts
        WHERE is_hidden = false
        AND created_at > NOW() - INTERVAL '7 days'
        """
    )

    post_results = [
        PostSummary(
            **{k: v for k, v in dict(post).items() if k != "engagement_score"},
            user_profile_image=post["profile_image_url"]
        )
        for post in posts
    ]

    return TrendingPostsResponse(
        posts=post_results,
        total=total["count"],
        page=page,
        page_size=page_size
    )


@app.get("/api/v1/discovery/posts/location", response_model=LocationPostsResponse, tags=["Discovery"])
async def get_posts_by_location(
    location: str = Query(..., min_length=1, description="Location name"),
    limit: int = Query(20, ge=1, le=100),
    database: Database = Depends(get_db)
):
    """
    Get posts by location

    - **location**: Location name
    - **limit**: Number of posts (default: 20, max: 100)
    """
    search_pattern = f"%{location}%"

    posts = await database.fetch_all(
        """
        SELECT p.id, p.user_id, u.username, u.profile_image_url,
               p.caption, p.image_url, p.video_url, p.location,
               p.like_count, p.comment_count, p.created_at
        FROM posts p
        JOIN users u ON p.user_id = u.id
        WHERE p.location ILIKE $1 AND p.is_hidden = false
        ORDER BY p.created_at DESC
        LIMIT $2
        """,
        search_pattern,
        limit
    )

    post_results = [
        PostSummary(
            **dict(post),
            user_profile_image=post["profile_image_url"]
        )
        for post in posts
    ]

    return LocationPostsResponse(
        location=location,
        posts=post_results,
        total=len(post_results)
    )


@app.get("/api/v1/discovery/feed", response_model=DiscoveryFeedResponse, tags=["Discovery"])
async def get_discovery_feed(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user_optional),
    database: Database = Depends(get_db)
):
    """
    Get personalized discovery feed

    - **page**: Page number (default: 1)
    - **page_size**: Items per page (default: 20, max: 100)
    - Authentication optional (results personalized if authenticated)
    """
    offset = (page - 1) * page_size

    if current_user:
        # Personalized feed - exclude posts from users already followed
        posts = await database.fetch_all(
            """
            SELECT p.id, p.user_id, u.username, u.profile_image_url,
                   p.caption, p.image_url, p.video_url,
                   p.like_count, p.comment_count, p.created_at
            FROM posts p
            JOIN users u ON p.user_id = u.id
            WHERE p.is_hidden = false
            AND p.user_id != $1
            AND p.user_id NOT IN (
                SELECT following_id FROM user_follows WHERE follower_id = $1
            )
            ORDER BY (p.like_count + p.comment_count * 2) DESC, p.created_at DESC
            LIMIT $2 OFFSET $3
            """,
            current_user["id"],
            page_size,
            offset
        )
    else:
        # General discovery feed
        posts = await database.fetch_all(
            """
            SELECT p.id, p.user_id, u.username, u.profile_image_url,
                   p.caption, p.image_url, p.video_url,
                   p.like_count, p.comment_count, p.created_at
            FROM posts p
            JOIN users u ON p.user_id = u.id
            WHERE p.is_hidden = false
            ORDER BY (p.like_count + p.comment_count * 2) DESC, p.created_at DESC
            LIMIT $1 OFFSET $2
            """,
            page_size,
            offset
        )

    post_results = [
        PostSummary(
            **dict(post),
            user_profile_image=post["profile_image_url"]
        )
        for post in posts
    ]

    has_more = len(post_results) == page_size

    return DiscoveryFeedResponse(
        posts=post_results,
        page=page,
        page_size=page_size,
        has_more=has_more
    )


@app.get("/", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {
        "service": "Instagram Discovery Service",
        "version": "1.0.0",
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }
