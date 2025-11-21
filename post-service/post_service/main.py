"""
Instagram Clone - Post Service
Main FastAPI application with MongoDB and Kafka
"""
from fastapi import FastAPI, HTTPException, status, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection
import re

from config import settings
from database import mongodb, get_posts_collection
from kafka_producer import kafka_producer
from auth import get_current_user, get_current_user_optional
from schemas import (
    PostCreate, PostUpdate, PostResponse, PostDetailResponse, PostListResponse,
    LikeResponse, CommentCreate, CommentResponse, CommentListResponse,
    MessageResponse, StatsResponse
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    print("🚀 Starting Post Service...")
    await mongodb.connect()
    await kafka_producer.start()
    print(f"✓ Post Service started on {settings.APP_NAME} v{settings.APP_VERSION}")

    yield

    # Shutdown
    print("👋 Shutting down Post Service...")
    await kafka_producer.stop()
    await mongodb.disconnect()


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Post service for Instagram clone with MongoDB and Kafka",
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


def extract_hashtags(text: str) -> List[str]:
    """Extract hashtags from text"""
    if not text:
        return []
    return list(set(re.findall(r'#(\w+)', text)))


def extract_mentions(text: str) -> List[str]:
    """Extract mentions from text"""
    if not text:
        return []
    return list(set(re.findall(r'@(\w+)', text)))


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


@app.post("/api/v1/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED, tags=["Posts"])
async def create_post(
    post_data: PostCreate,
    current_user: dict = Depends(get_current_user),
    posts_collection: AsyncIOMotorCollection = Depends(get_posts_collection)
):
    """
    Create a new post

    - **caption**: Post caption (max 2200 characters)
    - **media_ids**: List of media file IDs (1-10 items)
    - **location**: Optional location name
    - **latitude/longitude**: Optional coordinates
    - **hashtags**: Optional list of hashtags
    - **mentions**: Optional list of mentions
    - **is_comments_disabled**: Disable comments
    - **is_hidden**: Hide post
    - Requires authentication
    """
    # Auto-extract hashtags and mentions from caption if not provided
    auto_hashtags = extract_hashtags(post_data.caption or "")
    auto_mentions = extract_mentions(post_data.caption or "")

    # Merge with provided hashtags/mentions
    all_hashtags = list(set((post_data.hashtags or []) + auto_hashtags))
    all_mentions = list(set((post_data.mentions or []) + auto_mentions))

    # Create post document
    now = datetime.utcnow()
    post_doc = {
        "user_id": current_user["id"],
        "caption": post_data.caption,
        "media_ids": post_data.media_ids,
        "location": post_data.location,
        "latitude": post_data.latitude,
        "longitude": post_data.longitude,
        "hashtags": all_hashtags[:30],  # Limit to 30
        "mentions": all_mentions[:20],  # Limit to 20
        "like_count": 0,
        "comment_count": 0,
        "share_count": 0,
        "view_count": 0,
        "is_comments_disabled": post_data.is_comments_disabled,
        "is_hidden": post_data.is_hidden,
        "created_at": now,
        "updated_at": now
    }

    # Insert into MongoDB
    result = await posts_collection.insert_one(post_doc)
    post_doc["_id"] = result.inserted_id

    # Publish event to Kafka
    await kafka_producer.publish_post_created(
        str(result.inserted_id),
        current_user["id"],
        {
            "post_id": str(result.inserted_id),
            "user_id": current_user["id"],
            "caption": post_data.caption,
            "media_ids": post_data.media_ids,
            "hashtags": all_hashtags,
            "location": post_data.location,
            "created_at": now.isoformat()
        }
    )

    return PostResponse(**post_doc)


@app.get("/api/v1/posts/{post_id}", response_model=PostDetailResponse, tags=["Posts"])
async def get_post(
    post_id: str,
    current_user: dict = Depends(get_current_user_optional),
    posts_collection: AsyncIOMotorCollection = Depends(get_posts_collection)
):
    """
    Get post by ID

    - **post_id**: Post MongoDB ObjectId
    - Authentication optional
    """
    # Validate ObjectId
    if not ObjectId.is_valid(post_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid post ID format"
        )

    # Find post
    post = await posts_collection.find_one({"_id": ObjectId(post_id)})

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )

    # Check if hidden and not owner
    if post.get("is_hidden") and (not current_user or current_user["id"] != post["user_id"]):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )

    # Increment view count (async, don't wait)
    await posts_collection.update_one(
        {"_id": ObjectId(post_id)},
        {"$inc": {"view_count": 1}}
    )

    # Convert to response
    response_data = PostResponse(**post).model_dump()

    # TODO: Fetch user info from auth service
    # TODO: Fetch media URLs from media service
    # TODO: Check if liked/saved by current user

    return PostDetailResponse(**response_data)


@app.get("/api/v1/posts", response_model=PostListResponse, tags=["Posts"])
async def get_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[int] = None,
    hashtag: Optional[str] = None,
    location: Optional[str] = None,
    current_user: dict = Depends(get_current_user_optional),
    posts_collection: AsyncIOMotorCollection = Depends(get_posts_collection)
):
    """
    Get posts with filtering and pagination

    - **page**: Page number (default: 1)
    - **page_size**: Items per page (default: 20, max: 100)
    - **user_id**: Filter by user ID
    - **hashtag**: Filter by hashtag
    - **location**: Filter by location
    - Authentication optional
    """
    # Build query
    query = {}

    if user_id:
        query["user_id"] = user_id

    if hashtag:
        query["hashtags"] = hashtag

    if location:
        query["location"] = {"$regex": location, "$options": "i"}

    # Exclude hidden posts unless viewing own posts
    if not current_user or (user_id and user_id != current_user["id"]):
        query["is_hidden"] = False

    # Calculate skip
    skip = (page - 1) * page_size

    # Get total count
    total = await posts_collection.count_documents(query)

    # Get posts
    cursor = posts_collection.find(query).sort("created_at", -1).skip(skip).limit(page_size)
    posts = await cursor.to_list(length=page_size)

    post_responses = [PostResponse(**post) for post in posts]

    has_more = (skip + len(posts)) < total

    return PostListResponse(
        posts=post_responses,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more
    )


@app.put("/api/v1/posts/{post_id}", response_model=PostResponse, tags=["Posts"])
async def update_post(
    post_id: str,
    post_data: PostUpdate,
    current_user: dict = Depends(get_current_user),
    posts_collection: AsyncIOMotorCollection = Depends(get_posts_collection)
):
    """
    Update post

    - **post_id**: Post MongoDB ObjectId
    - **caption**: Update caption
    - **location**: Update location
    - **hashtags**: Update hashtags
    - **is_comments_disabled**: Update comment settings
    - **is_hidden**: Update visibility
    - Requires authentication
    - Only post owner can update
    """
    # Validate ObjectId
    if not ObjectId.is_valid(post_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid post ID format"
        )

    # Find post
    post = await posts_collection.find_one({"_id": ObjectId(post_id)})

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )

    # Check ownership
    if post["user_id"] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to update this post"
        )

    # Build update document
    update_doc = {"updated_at": datetime.utcnow()}

    if post_data.caption is not None:
        update_doc["caption"] = post_data.caption
        # Re-extract hashtags and mentions
        auto_hashtags = extract_hashtags(post_data.caption)
        auto_mentions = extract_mentions(post_data.caption)
        update_doc["hashtags"] = list(set((post_data.hashtags or []) + auto_hashtags))[:30]
        update_doc["mentions"] = auto_mentions[:20]

    if post_data.location is not None:
        update_doc["location"] = post_data.location

    if post_data.latitude is not None:
        update_doc["latitude"] = post_data.latitude

    if post_data.longitude is not None:
        update_doc["longitude"] = post_data.longitude

    if post_data.hashtags is not None and post_data.caption is None:
        update_doc["hashtags"] = post_data.hashtags[:30]

    if post_data.is_comments_disabled is not None:
        update_doc["is_comments_disabled"] = post_data.is_comments_disabled

    if post_data.is_hidden is not None:
        update_doc["is_hidden"] = post_data.is_hidden

    # Update post
    result = await posts_collection.update_one(
        {"_id": ObjectId(post_id)},
        {"$set": update_doc}
    )

    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No changes made to post"
        )

    # Get updated post
    updated_post = await posts_collection.find_one({"_id": ObjectId(post_id)})

    # Publish event to Kafka
    await kafka_producer.publish_post_updated(
        post_id,
        current_user["id"],
        {
            "post_id": post_id,
            "user_id": current_user["id"],
            "updated_fields": list(update_doc.keys()),
            "updated_at": update_doc["updated_at"].isoformat()
        }
    )

    return PostResponse(**updated_post)


@app.delete("/api/v1/posts/{post_id}", response_model=MessageResponse, tags=["Posts"])
async def delete_post(
    post_id: str,
    current_user: dict = Depends(get_current_user),
    posts_collection: AsyncIOMotorCollection = Depends(get_posts_collection)
):
    """
    Delete post

    - **post_id**: Post MongoDB ObjectId
    - Requires authentication
    - Only post owner can delete
    """
    # Validate ObjectId
    if not ObjectId.is_valid(post_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid post ID format"
        )

    # Find post
    post = await posts_collection.find_one({"_id": ObjectId(post_id)})

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )

    # Check ownership
    if post["user_id"] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to delete this post"
        )

    # Delete post
    await posts_collection.delete_one({"_id": ObjectId(post_id)})

    # Publish event to Kafka
    await kafka_producer.publish_post_deleted(
        post_id,
        current_user["id"]
    )

    return MessageResponse(message="Post deleted successfully")


@app.post("/api/v1/posts/{post_id}/like", response_model=LikeResponse, tags=["Interactions"])
async def like_post(
    post_id: str,
    current_user: dict = Depends(get_current_user),
    posts_collection: AsyncIOMotorCollection = Depends(get_posts_collection)
):
    """
    Like a post

    - **post_id**: Post MongoDB ObjectId
    - Requires authentication
    """
    # Validate ObjectId
    if not ObjectId.is_valid(post_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid post ID format"
        )

    # Find post
    post = await posts_collection.find_one({"_id": ObjectId(post_id)})

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )

    # TODO: Check if already liked in a separate likes collection
    # For now, just increment the count

    # Increment like count
    result = await posts_collection.update_one(
        {"_id": ObjectId(post_id)},
        {"$inc": {"like_count": 1}}
    )

    # Get updated post
    updated_post = await posts_collection.find_one({"_id": ObjectId(post_id)})

    # Publish event to Kafka
    await kafka_producer.publish_post_liked(
        post_id,
        post["user_id"],
        current_user["id"]
    )

    return LikeResponse(
        post_id=post_id,
        is_liked=True,
        like_count=updated_post["like_count"]
    )


@app.delete("/api/v1/posts/{post_id}/like", response_model=LikeResponse, tags=["Interactions"])
async def unlike_post(
    post_id: str,
    current_user: dict = Depends(get_current_user),
    posts_collection: AsyncIOMotorCollection = Depends(get_posts_collection)
):
    """
    Unlike a post

    - **post_id**: Post MongoDB ObjectId
    - Requires authentication
    """
    # Validate ObjectId
    if not ObjectId.is_valid(post_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid post ID format"
        )

    # Find post
    post = await posts_collection.find_one({"_id": ObjectId(post_id)})

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )

    # Decrement like count (ensure it doesn't go below 0)
    result = await posts_collection.update_one(
        {"_id": ObjectId(post_id), "like_count": {"$gt": 0}},
        {"$inc": {"like_count": -1}}
    )

    # Get updated post
    updated_post = await posts_collection.find_one({"_id": ObjectId(post_id)})

    return LikeResponse(
        post_id=post_id,
        is_liked=False,
        like_count=updated_post["like_count"]
    )


@app.get("/api/v1/posts/user/{user_id}/stats", response_model=StatsResponse, tags=["Stats"])
async def get_user_post_stats(
    user_id: int,
    posts_collection: AsyncIOMotorCollection = Depends(get_posts_collection)
):
    """
    Get post statistics for a user

    - **user_id**: User ID
    """
    # Aggregate statistics
    pipeline = [
        {"$match": {"user_id": user_id, "is_hidden": False}},
        {"$group": {
            "_id": None,
            "total_posts": {"$sum": 1},
            "total_likes": {"$sum": "$like_count"},
            "total_comments": {"$sum": "$comment_count"},
            "total_views": {"$sum": "$view_count"}
        }}
    ]

    result = await posts_collection.aggregate(pipeline).to_list(length=1)

    if not result:
        return StatsResponse(
            total_posts=0,
            total_likes=0,
            total_comments=0,
            total_views=0,
            avg_engagement_rate=0.0
        )

    stats = result[0]
    total_posts = stats["total_posts"]
    total_engagement = stats["total_likes"] + stats["total_comments"]

    avg_engagement_rate = (total_engagement / total_posts) if total_posts > 0 else 0.0

    return StatsResponse(
        total_posts=total_posts,
        total_likes=stats["total_likes"],
        total_comments=stats["total_comments"],
        total_views=stats["total_views"],
        avg_engagement_rate=round(avg_engagement_rate, 2)
    )


@app.get("/api/v1/posts/feed", response_model=PostListResponse, tags=["Feed"])
async def get_feed(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    posts_collection: AsyncIOMotorCollection = Depends(get_posts_collection)
):
    """
    Get personalized feed for current user

    - **page**: Page number (default: 1)
    - **page_size**: Items per page (default: 20, max: 100)
    - Requires authentication
    """
    # TODO: Fetch following list from database/cache
    # For now, return all posts sorted by created_at

    skip = (page - 1) * page_size

    # Query for non-hidden posts
    query = {"is_hidden": False}

    # Get total count
    total = await posts_collection.count_documents(query)

    # Get posts
    cursor = posts_collection.find(query).sort("created_at", -1).skip(skip).limit(page_size)
    posts = await cursor.to_list(length=page_size)

    post_responses = [PostResponse(**post) for post in posts]

    has_more = (skip + len(posts)) < total

    return PostListResponse(
        posts=post_responses,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8002,
        reload=True
    )
