# Instagram Clone - Microservices Architecture

## Overview

Instagram 클론 프로젝트는 마이크로서비스 아키텍처로 구성되어 있으며, 각 서비스는 독립적으로 확장 가능하고 유지보수가 용이합니다.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         API Gateway                              │
└─────────────────────────────────────────────────────────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
        ▼                        ▼                        ▼
┌──────────────┐        ┌──────────────┐        ┌──────────────┐
│ Auth Service │        │ Media Service│        │ Post Service │
│   (8001)     │        │   (8000)     │        │   (8002)     │
└──────────────┘        └──────────────┘        └──────────────┘
        │                        │                        │
        │                        │                        │
        ▼                        ▼                        ▼
┌──────────────┐        ┌──────────────┐        ┌──────────────┐
│ Graph Service│        │   Newsfeed   │        │  Discovery   │
│   (8003)     │◄──────►│   Service    │        │   Service    │
└──────────────┘        │   (8004)     │        └──────────────┘
        │               └──────────────┘                │
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                │
                                ▼
                        ┌──────────────┐
                        │    Kafka     │
                        │  (Message    │
                        │    Queue)    │
                        └──────────────┘
```

## Microservices

### 1. Discovery Service (Port: varies)

**목적**: 서비스 디스커버리 및 등록

**기술 스택**:
- FastAPI
- Zookeeper

**기능**:
- 서비스 등록 및 해제
- 서비스 헬스 체크
- 동적 서비스 발견

**저장소**: Zookeeper

---

### 2. Auth Service (Port: 8001)

**목적**: 사용자 인증 및 권한 관리

**기술 스택**:
- FastAPI
- PostgreSQL (pgdog 샤딩)
- JWT

**기능**:
- 회원가입/로그인
- JWT 토큰 발급 및 검증
- 사용자 프로필 관리
- 비밀번호 암호화 (bcrypt)

**저장소**: PostgreSQL (users 테이블)

---

### 3. Media Service (Port: 8000)

**목적**: 미디어 파일 업로드 및 관리

**기술 스택**:
- FastAPI
- PostgreSQL
- MinIO/S3
- Redis (캐싱)

**기능**:
- 이미지/비디오 업로드
- 이미지 리사이징 및 최적화
- CDN 통합
- 메타데이터 관리

**저장소**:
- PostgreSQL (메타데이터)
- MinIO/S3 (실제 파일)
- Redis (URL 캐싱)

---

### 4. Post Service (Port: 8002)

**목적**: 게시물 생성 및 관리

**기술 스택**:
- FastAPI
- MongoDB
- Kafka

**기능**:
- 포스트 생성/수정/삭제
- 좋아요/댓글 관리
- 해시태그 및 멘션 추출
- 포스트 조회 (사용자별, 해시태그별)
- 통계 (좋아요, 댓글, 조회수)

**저장소**: MongoDB (posts 컬렉션)

**Kafka 이벤트**:
- **발행**: `post.created`, `post.updated`, `post.deleted`, `post.liked`, `post.commented`

---

### 5. Graph Service (Port: 8003)

**목적**: 소셜 그래프 관리 (팔로우/팔로워)

**기술 스택**:
- FastAPI
- PostgreSQL (pgdog 샤딩)
- Redis (캐싱)
- Kafka

**기능**:
- 팔로우/언팔로우
- 팔로우 요청 (비공개 계정)
- 팔로워/팔로잉 목록 조회
- 상호 팔로우 확인
- 팔로우 추천 (친구의 친구)

**저장소**:
- PostgreSQL (follows 테이블)
- Redis (관계 캐싱)

**Kafka 이벤트**:
- **발행**: `follow.accepted`, `follow.removed`

---

### 6. Newsfeed Service (Port: 8004) ⭐ NEW

**목적**: 개인화된 뉴스피드 제공

**기술 스택**:
- FastAPI
- PostgreSQL (영구 저장)
- Redis (타임라인 캐싱)
- Kafka (이벤트 소비)
- HTTP Client (서비스 메시)

**기능**:
- 개인화된 피드 생성
- Hybrid Fan-out 전략
  - 일반 유저: Fan-out on Write
  - 인플루언서: Fan-out on Read
- 피드 캐싱 및 최적화
- 실시간 피드 업데이트

**저장소**:
- PostgreSQL (feed_items, feed_metadata 테이블)
- Redis (타임라인 Sorted Sets)

**Kafka 이벤트**:
- **구독**: `post.created`, `post.deleted`, `follow.accepted`, `follow.removed`
- **발행**: `feed.updated`

**서비스 메시 통신**:
- **Graph Service**: 팔로잉/팔로워 목록 조회
- **Post Service**: 포스트 상세 정보 조회
- **Auth Service**: JWT 토큰 검증

**피드 알고리즘**:
1. **캐시 우선**: Redis에서 타임라인 조회 (5분 TTL)
2. **DB 백업**: PostgreSQL에서 피드 아이템 조회
3. **재구성**: Stale 상태인 경우 피드 재구성
   - 팔로잉 유저 목록 조회 (Graph Service)
   - 각 유저의 최근 포스트 조회 (Post Service)
   - 시간순 정렬 및 저장
4. **하이브리드 전략**:
   - 팔로워 < 100K: 포스트 생성 시 팔로워 피드에 추가
   - 팔로워 ≥ 100K: 피드 조회 시 실시간으로 가져옴

---

## Data Flow

### 1. 포스트 생성 플로우

```
User → Post Service → MongoDB
                    ↓
                  Kafka (post.created)
                    ↓
              Newsfeed Service
                    ↓
        ┌───────────┴───────────┐
        ▼                       ▼
  Graph Service          Followers' Feeds
  (Get Followers)        (Fan-out if < 100K followers)
        ↓                       ↓
  Follower IDs           PostgreSQL + Redis
```

### 2. 피드 조회 플로우

```
User → Newsfeed Service
           ↓
    Try Redis Cache
           │
     ┌─────┴─────┐
     ▼           ▼
  Cache Hit   Cache Miss
     │           │
     │      Try PostgreSQL
     │           │
     │      ┌────┴────┐
     │      ▼         ▼
     │   Found    Not Found/Stale
     │      │         │
     │      │    Rebuild Feed
     │      │         ↓
     │      │   Graph Service
     │      │   (Get Following)
     │      │         ↓
     │      │   Post Service
     │      │   (Get Posts)
     │      │         ↓
     │      │   Save to DB + Cache
     │      │         │
     └──────┴─────────┘
           ↓
    Return Feed Items
```

### 3. 팔로우 플로우

```
User → Graph Service
           ↓
    Create Follow Relation
           ↓
      PostgreSQL
           ↓
    Kafka (follow.accepted)
           ↓
    Newsfeed Service
           ↓
   Mark Feed as Stale
   (Rebuild on next request)
```

## Database Schema

### PostgreSQL Tables

#### Auth Service
```sql
-- users 테이블 (샤딩됨)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### Graph Service
```sql
-- follows 테이블 (샤딩됨)
CREATE TABLE follows (
    id BIGSERIAL PRIMARY KEY,
    follower_id INTEGER NOT NULL,
    following_id INTEGER NOT NULL,
    status VARCHAR(20) DEFAULT 'accepted',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(follower_id, following_id)
);

CREATE INDEX idx_follows_follower ON follows(follower_id);
CREATE INDEX idx_follows_following ON follows(following_id);
```

#### Newsfeed Service
```sql
-- feed_items 테이블
CREATE TABLE feed_items (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    post_id VARCHAR(24) NOT NULL,
    post_user_id INTEGER NOT NULL,
    post_created_at TIMESTAMP NOT NULL,
    feed_score DOUBLE PRECISION DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_feed_items_user_created ON feed_items(user_id, post_created_at DESC);
CREATE INDEX idx_feed_items_post ON feed_items(post_id);

-- feed_metadata 테이블
CREATE TABLE feed_metadata (
    user_id INTEGER PRIMARY KEY,
    last_updated TIMESTAMP,
    total_items INTEGER DEFAULT 0,
    is_stale BOOLEAN DEFAULT FALSE
);
```

### MongoDB Collections

#### Post Service
```javascript
// posts 컬렉션
{
    _id: ObjectId,
    user_id: Number,
    caption: String,
    media_ids: [String],
    location: String,
    hashtags: [String],
    mentions: [String],
    like_count: Number,
    comment_count: Number,
    view_count: Number,
    is_comments_disabled: Boolean,
    is_hidden: Boolean,
    created_at: Date,
    updated_at: Date
}
```

### Redis Data Structures

#### Newsfeed Service
```
# Timeline cache (Sorted Set)
Key: feed:{user_id}
Type: ZSET
Score: timestamp
Value: post_id
TTL: 300 seconds

# Feed metadata cache
Key: feed:meta:{user_id}
Type: String (JSON)
Value: {"total_items": 150, "last_updated": "..."}
TTL: 300 seconds
```

## Kafka Topics

| Topic | Producer | Consumer | Purpose |
|-------|----------|----------|---------|
| `post.created` | Post Service | Newsfeed Service | 새 포스트 알림 |
| `post.deleted` | Post Service | Newsfeed Service | 포스트 삭제 알림 |
| `post.liked` | Post Service | - | 좋아요 이벤트 |
| `follow.accepted` | Graph Service | Newsfeed Service | 팔로우 수락 알림 |
| `follow.removed` | Graph Service | Newsfeed Service | 언팔로우 알림 |
| `feed.updated` | Newsfeed Service | - | 피드 업데이트 알림 |

## Service Mesh Communication

### REST API Calls

```
Newsfeed Service → Graph Service
  GET /api/v1/graph/following/{user_id}
  GET /api/v1/graph/followers/{user_id}
  GET /api/v1/graph/stats/{user_id}

Newsfeed Service → Post Service
  GET /api/v1/posts/{post_id}
  GET /api/v1/posts?user_id={user_id}

All Services → Auth Service
  Validate JWT tokens in requests
```

## Scaling Strategy

### Horizontal Scaling
- 각 서비스는 독립적으로 스케일 가능
- Load Balancer를 통한 트래픽 분산
- Stateless 설계

### Database Scaling
- PostgreSQL: pgdog를 통한 샤딩
- MongoDB: Replica Set 및 샤딩
- Redis: Redis Cluster

### Caching Strategy
- **L1 Cache**: Redis (타임라인, 관계)
- **L2 Cache**: PostgreSQL (영구 저장)
- **L3 Cache**: On-demand rebuild

## Monitoring & Observability

### Metrics to Monitor
1. **Newsfeed Service**:
   - Feed request latency
   - Cache hit ratio
   - Feed rebuild frequency
   - Kafka consumer lag

2. **Graph Service**:
   - Follow/unfollow rate
   - Follower count distribution
   - Cache hit ratio

3. **Post Service**:
   - Post creation rate
   - Like/comment rate
   - Media upload size

### Logging
- Centralized logging with ELK stack
- Structured logging (JSON format)
- Correlation IDs for request tracing

## Security

1. **Authentication**: JWT tokens
2. **Authorization**: Role-based access control
3. **Rate Limiting**: Per-user request limits
4. **Input Validation**: Pydantic schemas
5. **SQL Injection**: Parameterized queries
6. **CORS**: Configured per service

## Deployment

### Docker Compose
```bash
docker-compose up -d
```

### Kubernetes
```bash
kubectl apply -f k8s/
```

## Future Enhancements

1. **Newsfeed ML Ranking**: 머신러닝 기반 개인화 알고리즘
2. **Real-time Updates**: WebSocket을 통한 실시간 피드 푸시
3. **Stories Feature**: 24시간 자동 삭제되는 스토리
4. **Direct Messaging**: 1:1 및 그룹 채팅
5. **Notifications Service**: 푸시 알림 및 인앱 알림
6. **Search Service**: Elasticsearch 기반 검색
7. **Analytics Service**: 사용자 행동 분석 및 인사이트
