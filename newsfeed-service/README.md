# Newsfeed Service

Instagram Clone의 뉴스피드 서비스입니다. 사용자에게 개인화된 포스트 피드를 제공합니다.

## 아키텍처

### 데이터베이스 설계

#### PostgreSQL 테이블

**feed_items**
```sql
CREATE TABLE feed_items (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,           -- 피드를 볼 유저
    post_id VARCHAR(24) NOT NULL,       -- MongoDB ObjectId
    post_user_id INTEGER NOT NULL,      -- 포스트 작성자
    post_created_at TIMESTAMP NOT NULL, -- 포스트 생성 시간
    feed_score DOUBLE PRECISION,        -- 랭킹 점수
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_feed_items_user_created ON feed_items (user_id, post_created_at DESC);
CREATE INDEX idx_feed_items_post ON feed_items (post_id);
```

**feed_metadata**
```sql
CREATE TABLE feed_metadata (
    user_id INTEGER PRIMARY KEY,
    last_updated TIMESTAMP,
    total_items INTEGER DEFAULT 0,
    is_stale BOOLEAN DEFAULT FALSE
);
```

#### Redis 캐싱

- **Key**: `feed:{user_id}`
- **Type**: Sorted Set (ZSET)
- **Score**: 포스트 생성 시간의 타임스탬프
- **Value**: post_id
- **TTL**: 5분 (300초)

### 피드 전략: Hybrid Fan-out

#### 1. Fan-out on Write (일반 유저)
- 팔로워 수 < 100,000
- 포스트 생성 시 모든 팔로워의 피드에 추가
- **장점**: 읽기가 빠름
- **단점**: 쓰기 비용이 높음

#### 2. Fan-out on Read (인플루언서)
- 팔로워 수 ≥ 100,000
- 피드 조회 시 실시간으로 포스트 가져옴
- **장점**: 쓰기 비용이 낮음
- **단점**: 읽기가 느림 (캐싱으로 완화)

### 서비스 메시 (Inter-service Communication)

다음 서비스들과 HTTP를 통해 통신:

1. **Graph Service** (`/api/v1/graph/*`)
   - 팔로잉/팔로워 목록 가져오기
   - 팔로워 수 확인 (celebrity 여부 판단)

2. **Post Service** (`/api/v1/posts/*`)
   - 포스트 상세 정보 가져오기
   - 배치로 여러 포스트 조회

3. **Auth Service** (`/api/v1/auth/*`)
   - JWT 토큰 검증
   - 사용자 인증

### Kafka 이벤트 처리

#### 구독하는 토픽 (Consumer)

1. **post.created**
   - 새 포스트 생성 시
   - Fan-out 전략에 따라 피드에 추가

2. **post.deleted**
   - 포스트 삭제 시
   - 모든 피드에서 제거

3. **follow.accepted**
   - 팔로우 수락 시
   - 팔로워의 피드를 stale로 마킹 (다음 조회 시 재구성)

4. **follow.removed**
   - 언팔로우 시
   - 언팔로우한 유저의 포스트를 피드에서 제거

#### 발행하는 토픽 (Producer)

1. **feed.updated**
   - 피드 업데이트 시
   - 알림 서비스 등에서 활용 가능

## API 엔드포인트

### 피드 조회

```http
GET /api/v1/feed?page=1&page_size=20
Authorization: Bearer <token>
```

**응답**:
```json
{
  "items": [
    {
      "id": 1,
      "post_id": "507f1f77bcf86cd799439011",
      "post_user_id": 123,
      "post_created_at": "2024-01-01T12:00:00Z",
      "feed_score": 0.0,
      "created_at": "2024-01-01T12:00:05Z",
      "post_data": {
        "id": "507f1f77bcf86cd799439011",
        "user_id": 123,
        "caption": "Beautiful sunset!",
        "media_ids": ["media1", "media2"],
        "like_count": 42,
        "comment_count": 5
      }
    }
  ],
  "total": 150,
  "page": 1,
  "page_size": 20,
  "has_more": true
}
```

### 피드 새로고침

```http
POST /api/v1/feed/refresh
Authorization: Bearer <token>
```

**응답**:
```json
{
  "message": "Feed refreshed successfully"
}
```

### 피드 통계

```http
GET /api/v1/feed/stats
Authorization: Bearer <token>
```

**응답**:
```json
{
  "user_id": 123,
  "total_items": 150,
  "last_updated": "2024-01-01T12:00:00Z",
  "cache_status": "hit"
}
```

## 환경 변수

```bash
# Application
APP_NAME="Instagram Newsfeed Service"
APP_VERSION="1.0.0"
DEBUG=false
HOST="0.0.0.0"
PORT=8004

# Database
DATABASE_URL="postgresql://user:pass@localhost:6432/instagram"
DB_POOL_SIZE=20

# Redis
REDIS_HOST="localhost"
REDIS_PORT=6379
REDIS_DB=1
REDIS_ENABLED=true

# Auth
JWT_SECRET_KEY="your-secret-key"
JWT_ALGORITHM="HS256"

# Other Services
POST_SERVICE_URL="http://localhost:8002"
GRAPH_SERVICE_URL="http://localhost:8003"
AUTH_SERVICE_URL="http://localhost:8001"

# Kafka
KAFKA_BOOTSTRAP_SERVERS="localhost:9092"
KAFKA_ENABLED=true
KAFKA_CONSUMER_GROUP="newsfeed-service"

# Feed Settings
CELEBRITY_FOLLOWER_THRESHOLD=100000
MAX_FEED_ITEMS_PER_USER=500
FEED_CACHE_TTL=300
```

## 실행 방법

```bash
# 의존성 설치
uv pip install -e .

# 서비스 실행
python -m newsfeed_service.main

# 또는 uvicorn 직접 실행
uvicorn newsfeed_service.main:app --host 0.0.0.0 --port 8004 --reload
```

## 성능 최적화

1. **3단계 캐싱 전략**
   - Redis (L1): 타임라인 캐싱
   - PostgreSQL (L2): 영구 저장
   - On-demand rebuild: 필요 시 재구성

2. **배치 처리**
   - 여러 포스트를 한 번에 조회
   - 대량 피드 아이템 삽입

3. **비동기 처리**
   - Kafka를 통한 이벤트 기반 업데이트
   - 백그라운드에서 피드 업데이트

4. **데이터베이스 인덱싱**
   - (user_id, post_created_at) 복합 인덱스
   - post_id 인덱스

## 확장성

- **수평 확장**: 여러 인스턴스 실행 가능
- **샤딩**: PostgreSQL pgdog를 통한 데이터 샤딩
- **캐시 분산**: Redis Cluster 사용 가능
- **메시지 큐**: Kafka 파티셔닝

## 모니터링

주요 메트릭:
- 피드 조회 응답 시간
- 캐시 히트율
- 피드 재구성 빈도
- Kafka 이벤트 처리 지연시간

## 향후 개선 사항

1. **ML 기반 랭킹**
   - feed_score를 활용한 개인화 알고리즘
   - 사용자 상호작용 기반 학습

2. **실시간 업데이트**
   - WebSocket을 통한 실시간 피드 푸시

3. **이미지 프리로딩**
   - 미디어 서비스와 연동하여 이미지 미리 로드

4. **A/B 테스팅**
   - 다양한 피드 알고리즘 테스트

5. **광고 통합**
   - 스폰서 포스트 삽입
