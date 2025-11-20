# Instagram Graph Service

A microservice for managing social graph relationships (follow/unfollow) in an Instagram-like application.

## Features

- **Follow/Unfollow**: Follow and unfollow users with support for private accounts
- **Follow Requests**: Handle pending follow requests for private accounts
- **Followers/Following Lists**: Get paginated lists of followers and following
- **Relationship Status**: Check relationship status between users
- **Mutual Followers**: Find mutual followers between users
- **Follow Suggestions**: Get follow suggestions based on friends-of-friends
- **Statistics**: Get follower/following counts and statistics
- **Redis Caching**: High-performance caching layer for frequently accessed data
- **Kafka Events**: Publish events for follow/unfollow actions
- **Auth Integration**: Seamless integration with Auth Service for authentication

## Architecture

### Technology Stack

- **Framework**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL with pgdog sharding
- **Cache**: Redis
- **Message Queue**: Apache Kafka
- **Authentication**: JWT tokens via Auth Service

### Database Schema

#### `follows` Table
```sql
CREATE TABLE follows (
    follower_id BIGINT NOT NULL,      -- User who is following
    following_id BIGINT NOT NULL,     -- User being followed
    status VARCHAR(20) NOT NULL,      -- accepted, pending, rejected
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (follower_id, following_id)
);
```

#### `user_graph_stats` Table (Cache)
```sql
CREATE TABLE user_graph_stats (
    user_id BIGINT PRIMARY KEY,
    follower_count INT NOT NULL DEFAULT 0,
    following_count INT NOT NULL DEFAULT 0,
    pending_requests_count INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL
);
```

### Key Design Decisions

1. **PostgreSQL for Graph Data**
   - Leverages existing pgdog sharding infrastructure
   - Provides ACID guarantees for follow relationships
   - Efficient indexing for common queries

2. **Redis Caching Layer**
   - Caches followers/following lists
   - Caches relationship status
   - Automatic cache invalidation on updates

3. **Kafka Event Publishing**
   - Publishes follow/unfollow events
   - Enables other services to react to graph changes
   - Supports event-driven architecture

4. **Auth Service Integration**
   - Verifies JWT tokens via HTTP calls
   - Checks user privacy settings
   - Validates user existence

## API Endpoints

### Follow/Unfollow

#### Follow a User
```http
POST /api/v1/graph/follow/{user_id}
Authorization: Bearer {token}
```

Response:
```json
{
  "success": true,
  "status": "accepted",  // or "pending" for private accounts
  "message": "Successfully followed user"
}
```

#### Unfollow a User
```http
DELETE /api/v1/graph/unfollow/{user_id}
Authorization: Bearer {token}
```

### Followers/Following

#### Get Followers
```http
GET /api/v1/graph/followers/{user_id}?page=1&page_size=20
Authorization: Bearer {token}
```

Response:
```json
{
  "followers": [
    {
      "user_id": 123,
      "created_at": "2025-01-20T10:00:00Z"
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "has_more": true
}
```

#### Get Following
```http
GET /api/v1/graph/following/{user_id}?page=1&page_size=20
Authorization: Bearer {token}
```

### Relationship

#### Get Relationship Status
```http
GET /api/v1/graph/relationship/{user_id}
Authorization: Bearer {token}
```

Response:
```json
{
  "user_id": 1,
  "target_user_id": 2,
  "relationship": "mutual",  // following, followed_by, mutual, pending, requested, none
  "is_following": true,
  "is_followed_by": true,
  "is_mutual": true,
  "is_pending": false,
  "is_requested": false
}
```

### Statistics

#### Get User Stats
```http
GET /api/v1/graph/stats/{user_id}
Authorization: Bearer {token}
```

Response:
```json
{
  "user_id": 1,
  "follower_count": 150,
  "following_count": 200,
  "pending_requests_count": 5
}
```

### Follow Requests

#### Get Pending Requests
```http
GET /api/v1/graph/requests/pending?page=1&page_size=20
Authorization: Bearer {token}
```

#### Accept/Reject Request
```http
POST /api/v1/graph/requests/{follower_id}
Authorization: Bearer {token}
Content-Type: application/json

{
  "action": "accept"  // or "reject"
}
```

### Social Features

#### Get Mutual Followers
```http
GET /api/v1/graph/mutual/{user_id}?limit=20
Authorization: Bearer {token}
```

Response:
```json
{
  "user_id": 1,
  "other_user_id": 2,
  "mutual_followers": [3, 4, 5],
  "count": 3
}
```

#### Get Follow Suggestions
```http
GET /api/v1/graph/suggestions?limit=10
Authorization: Bearer {token}
```

Response:
```json
{
  "suggestions": [10, 11, 12],
  "count": 3
}
```

## Installation

### Prerequisites

- Python 3.11+
- PostgreSQL (via pgdog)
- Redis
- Apache Kafka
- Auth Service running

### Setup

1. **Clone the repository**
```bash
cd graph-service
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. **Run database migrations**
```bash
psql -h localhost -p 6432 -U instagram_user -d instagram -f migrations/001_create_follows_table.sql
```

6. **Start the service**
```bash
python -m uvicorn graph_service.main:app --host 0.0.0.0 --port 8003 --reload
```

## Docker Deployment

### Using Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f graph-service

# Stop services
docker-compose down
```

### Environment Variables

See `.env.example` for all available configuration options.

Key variables:
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_HOST`: Redis host
- `KAFKA_BOOTSTRAP_SERVERS`: Kafka brokers
- `AUTH_SERVICE_URL`: Auth service endpoint
- `JWT_SECRET_KEY`: JWT secret for token validation

## Development

### Running Tests

```bash
pytest tests/
```

### Code Style

```bash
# Format code
black graph_service/

# Lint
flake8 graph_service/

# Type checking
mypy graph_service/
```

## Kafka Events

The service publishes the following events:

### `graph.follow`
```json
{
  "event_type": "follow",
  "follower_id": 1,
  "following_id": 2,
  "status": "accepted",
  "timestamp": "2025-01-20T10:00:00Z"
}
```

### `graph.unfollow`
```json
{
  "event_type": "unfollow",
  "follower_id": 1,
  "following_id": 2,
  "timestamp": "2025-01-20T10:00:00Z"
}
```

### `graph.follow_accepted`
```json
{
  "event_type": "follow_request_accepted",
  "follower_id": 1,
  "following_id": 2,
  "timestamp": "2025-01-20T10:00:00Z"
}
```

### `graph.follow_rejected`
```json
{
  "event_type": "follow_request_rejected",
  "follower_id": 1,
  "following_id": 2,
  "timestamp": "2025-01-20T10:00:00Z"
}
```

## Performance Considerations

### Caching Strategy

- **Followers/Following Lists**: 5 minutes TTL
- **Relationship Status**: 10 minutes TTL
- **User Stats**: 1 minute TTL
- Cache invalidation on any follow/unfollow action

### Database Optimization

- Composite primary key on (follower_id, following_id)
- Indexes on follower_id and following_id with status
- Partial index on pending requests
- Database triggers for maintaining stats table

### Scalability

- Horizontal scaling via pgdog sharding
- Stateless service design
- Connection pooling for database and Redis
- Async I/O throughout

## Monitoring

### Health Check

```http
GET /health
```

Response:
```json
{
  "status": "healthy",
  "service": "Instagram Graph Service"
}
```

### Metrics to Monitor

- Follow/unfollow rate
- Cache hit rate
- Database query latency
- Kafka publish rate
- Auth service response time

## API Documentation

Interactive API documentation available at:
- Swagger UI: `http://localhost:8003/docs`
- ReDoc: `http://localhost:8003/redoc`

## License

Copyright (c) 2025 Instagram Engineering

## Support

For issues and questions, please open an issue in the repository.
