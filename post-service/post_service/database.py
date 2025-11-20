"""
MongoDB database connection and utilities
"""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from typing import Optional
from config import settings


class MongoDB:
    """MongoDB connection manager"""

    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.posts_collection: Optional[AsyncIOMotorCollection] = None

    async def connect(self):
        """Connect to MongoDB"""
        self.client = AsyncIOMotorClient(settings.MONGODB_URL)
        self.db = self.client[settings.MONGODB_DATABASE]
        self.posts_collection = self.db[settings.MONGODB_COLLECTION]

        # Create indexes
        await self.create_indexes()

        print(f"✓ Connected to MongoDB at {settings.MONGODB_URL}")
        print(f"✓ Using database: {settings.MONGODB_DATABASE}")

    async def disconnect(self):
        """Disconnect from MongoDB"""
        if self.client:
            self.client.close()
            print("✓ MongoDB connection closed")

    async def create_indexes(self):
        """Create database indexes for optimization"""
        # Index on user_id for faster user post queries
        await self.posts_collection.create_index("user_id")

        # Index on created_at for sorting
        await self.posts_collection.create_index([("created_at", -1)])

        # Compound index for user posts sorted by date
        await self.posts_collection.create_index([("user_id", 1), ("created_at", -1)])

        # Index on hashtags for hashtag search
        await self.posts_collection.create_index("hashtags")

        # Index on location for location-based queries
        await self.posts_collection.create_index("location")

        # Text index for caption search
        await self.posts_collection.create_index([("caption", "text")])

        print("✓ MongoDB indexes created")


# Global MongoDB instance
mongodb = MongoDB()


async def get_db() -> AsyncIOMotorDatabase:
    """Dependency for getting database instance"""
    return mongodb.db


async def get_posts_collection() -> AsyncIOMotorCollection:
    """Dependency for getting posts collection"""
    return mongodb.posts_collection
