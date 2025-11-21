# API Gateway

API Gateway for Instagram Clone microservices architecture. Built with Go and Gin framework.

## Features

- **Reverse Proxy**: Routes requests to appropriate microservices
- **Passthrough Authentication**: Forwards JWT tokens to services for validation
- **Rate Limiting**: Per-IP request limiting using token bucket algorithm
- **CORS**: Cross-Origin Resource Sharing support
- **Logging**: Structured logging with zap
- **Health Checks**: Service health monitoring
- **Graceful Shutdown**: Handles shutdown signals properly

## Architecture

The gateway operates in **passthrough mode** - it forwards all requests (including Authorization headers) to backend services without validating JWT tokens. Each microservice handles its own authentication, providing better service autonomy and reducing gateway complexity.

```
Client → API Gateway (Rate Limiting + Logging)
            ↓ (Forwards request with headers)
   ┌────────┼────────┐
   ▼        ▼        ▼
  Auth    Media    Post      (Each service validates JWT)
 (8001)  (8000)  (8002)
   ↓        ▼        ↓
  Graph  Newsfeed
 (8003)   (8004)
```

## Routing

### Auth Service (`/api/v1/auth`)
- `POST /register` - User registration (public)
- `POST /login` - User login (public)
- `POST /refresh` - Refresh token (public)
- `GET /profile` - Get user profile (requires auth - service validates)
- `GET /me` - Get current user (requires auth - service validates)
- `PUT /profile` - Update user profile (requires auth - service validates)
- `POST /logout` - Logout (requires auth - service validates)
- `PUT /password` - Change password (requires auth - service validates)

**Note**: Authentication is handled by the Auth Service. Send `Authorization: Bearer <token>` header.

### Media Service (`/api/v1/media`)
- `POST /upload` - Upload media (requires auth - service validates)
- `GET /:id` - Get media by ID (requires auth - service validates)
- `DELETE /:id` - Delete media (requires auth - service validates)
- `GET /user/:user_id` - Get user's media (requires auth - service validates)

**Note**: All media operations require authentication. Service validates JWT tokens.

### Post Service (`/api/v1/posts`)
- `GET /:id` - Get post by ID (optional auth for personalization)
- `GET /` - List posts (optional auth for personalization)
- `GET /user/:user_id` - Get user's posts (optional auth)
- `GET /hashtag/:hashtag` - Get posts by hashtag (optional auth)
- `POST /` - Create post (requires auth - service validates)
- `PUT /:id` - Update post (requires auth - service validates)
- `DELETE /:id` - Delete post (requires auth - service validates)
- `POST /:id/like` - Like post (requires auth - service validates)
- `DELETE /:id/like` - Unlike post (requires auth - service validates)
- `POST /:id/comments` - Add comment (requires auth - service validates)
- `GET /:id/comments` - Get comments (optional auth)
- `DELETE /:id/comments/:comment_id` - Delete comment (requires auth - service validates)

**Note**: Read operations work without auth. Write operations require authentication.

### Graph Service (`/api/v1/graph`)
- `POST /follow/:user_id` - Follow user (protected)
- `DELETE /follow/:user_id` - Unfollow user (protected)
- `GET /follow-requests` - Get follow requests (protected)
- `POST /follow-requests/:request_id/accept` - Accept follow request (protected)
- `POST /follow-requests/:request_id/reject` - Reject follow request (protected)
- `GET /followers/:user_id` - Get followers (protected)
- `GET /following/:user_id` - Get following (protected)
- `GET /relationship/:user_id` - Check relationship (protected)
- `GET /stats/:user_id` - Get user stats (protected)
- `GET /recommendations` - Get follow recommendations (protected)

### Newsfeed Service (`/api/v1/feed`)
- `GET /` - Get personalized feed (protected)
- `POST /refresh` - Refresh feed (protected)
- `GET /stats` - Get feed stats (protected)

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | Environment (development/production) | `development` |
| `PORT` | Gateway port | `8080` |
| `AUTH_SERVICE_URL` | Auth service URL | `http://auth-service:8001` |
| `MEDIA_SERVICE_URL` | Media service URL | `http://media-service:8000` |
| `POST_SERVICE_URL` | Post service URL | `http://post-service:8002` |
| `GRAPH_SERVICE_URL` | Graph service URL | `http://graph-service:8003` |
| `NEWSFEED_SERVICE_URL` | Newsfeed service URL | `http://newsfeed-service:8004` |
| `JWT_SECRET` | JWT signing secret | `your-secret-key` |
| `RATE_LIMIT_RPS` | Rate limit requests per second | `100` |
| `RATE_LIMIT_BURST` | Rate limit burst size | `200` |
| `REDIS_ADDR` | Redis address | `redis:6379` |
| `REDIS_PASSWORD` | Redis password | `` |
| `REDIS_DB` | Redis database | `0` |
| `READ_TIMEOUT_SEC` | HTTP read timeout | `30` |
| `WRITE_TIMEOUT_SEC` | HTTP write timeout | `30` |
| `IDLE_TIMEOUT_SEC` | HTTP idle timeout | `120` |
| `PROXY_TIMEOUT_SEC` | Proxy request timeout | `30` |

## Development

### Prerequisites

- Go 1.21 or higher
- Docker (optional)

### Run Locally

```bash
# Install dependencies
go mod download

# Run the gateway
go run main.go
```

### Build

```bash
go build -o api-gateway .
```

### Run with Docker

```bash
# Build image
docker build -t instagram-api-gateway .

# Run container
docker run -p 8080:8080 --env-file .env instagram-api-gateway
```

## Testing

### Health Check

```bash
curl http://localhost:8080/health
```

### Test Authentication

```bash
# Register
curl -X POST http://localhost:8080/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@example.com","password":"password123"}'

# Login
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"password123"}'

# Access protected endpoint
curl http://localhost:8080/api/v1/auth/profile \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## Middleware

### Authentication Middleware

- `JWTAuth`: Validates JWT tokens, aborts on invalid/missing token
- `OptionalJWTAuth`: Validates JWT tokens but doesn't abort if missing

### Rate Limiting Middleware

- `RateLimit`: Per-IP rate limiting using token bucket algorithm
- `UserRateLimit`: Per-user rate limiting (uses user ID if authenticated, falls back to IP)

### Logger Middleware

Logs all HTTP requests with:
- Method, path, query
- Status code
- Latency
- Client IP
- User agent
- Response size

## Performance

- **Concurrent Requests**: Handles thousands of concurrent requests
- **Rate Limiting**: 100 RPS per client by default
- **Timeouts**: Configurable timeouts to prevent hanging requests
- **Connection Pooling**: Reuses HTTP connections for backend services

## Security

- **JWT Validation**: Validates all tokens before forwarding requests
- **Rate Limiting**: Prevents abuse and DDoS attacks
- **CORS**: Configurable CORS policies
- **Header Sanitization**: Removes hop-by-hop headers
- **Non-root User**: Docker container runs as non-root user

## Monitoring

### Metrics to Monitor

- Request latency
- Error rates
- Rate limit hits
- Backend service availability
- Memory and CPU usage

### Health Check

The gateway exposes a `/health` endpoint for health checks:

```json
{
  "status": "healthy",
  "time": "2025-11-21T10:00:00Z"
}
```

## License

MIT
