# Instagram Clone - Post Service

Post Service provides CRUD operations for user posts using MongoDB and Apache Kafka.

## Features

- ✅ Create, Read, Update, Delete posts
- ✅ MongoDB for data storage
- ✅ Apache Kafka for event publishing
- ✅ JWT authentication with Auth Service
- ✅ Automatic hashtag and mention extraction
- ✅ Like/unlike posts
- ✅ Post statistics and analytics
- ✅ Personalized feed
- ✅ Location-based posts
- ✅ Hashtag filtering
- ✅ User posts listing

## API Endpoints

### Posts

- `POST /api/v1/posts` - Create a new post
- `GET /api/v1/posts/{post_id}` - Get post by ID
- `GET /api/v1/posts` - List posts with filtering
- `PUT /api/v1/posts/{post_id}` - Update post
- `DELETE /api/v1/posts/{post_id}` - Delete post

### Interactions

- `POST /api/v1/posts/{post_id}/like` - Like a post
- `DELETE /api/v1/posts/{post_id}/like` - Unlike a post

### Feed & Stats

- `GET /api/v1/posts/feed` - Get personalized feed
- `GET /api/v1/posts/user/{user_id}/stats` - Get user post statistics

## Kafka Events

The service publishes the following events:

- `post.created` - When a new post is created
- `post.updated` - When a post is updated
- `post.deleted` - When a post is deleted
- `post.liked` - When a post is liked
- `post.commented` - When a post receives a comment

## Environment Variables

Create a `.env` file with the following variables:

```env
# MongoDB
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=instagram_posts

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Auth Service
AUTH_SERVICE_URL=http://localhost:8001

# Media Service
MEDIA_SERVICE_URL=http://localhost:8000
```

## Running the Service

```bash
# Install dependencies
uv sync

# Run the service
python -m post_service.main
```

The service will be available at `http://localhost:8002`

## MongoDB Collections

### posts

```json
{
  "_id": ObjectId,
  "user_id": int,
  "caption": string,
  "media_ids": [int],
  "location": string,
  "latitude": float,
  "longitude": float,
  "hashtags": [string],
  "mentions": [string],
  "like_count": int,
  "comment_count": int,
  "share_count": int,
  "view_count": int,
  "is_comments_disabled": boolean,
  "is_hidden": boolean,
  "created_at": datetime,
  "updated_at": datetime
}
```

## Dependencies

- FastAPI - Web framework
- Motor - Async MongoDB driver
- aiokafka - Async Kafka client
- Pydantic - Data validation
- httpx - HTTP client for service communication
