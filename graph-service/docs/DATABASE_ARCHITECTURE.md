# Graph Service Database Architecture

## 목차
- [개요](#개요)
- [데이터베이스 엔진 선택](#데이터베이스-엔진-선택)
- [PostgreSQL - Primary Database](#postgresql---primary-database)
- [Redis - Caching Layer](#redis---caching-layer)
- [Kafka - Event Streaming](#kafka---event-streaming)
- [데이터 흐름](#데이터-흐름)
- [성능 최적화](#성능-최적화)
- [확장성 전략](#확장성-전략)
- [운영 고려사항](#운영-고려사항)

---

## 개요

Graph Service는 **Polyglot Persistence** 전략을 채택하여, 각 데이터베이스 엔진의 강점을 활용합니다.

### 멀티 데이터베이스 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                    Graph Service                         │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ PostgreSQL   │  │    Redis     │  │    Kafka     │  │
│  │  (pgdog)     │  │   Caching    │  │   Events     │  │
│  │              │  │              │  │              │  │
│  │ Source of    │  │ Performance  │  │ Async Comm   │  │
│  │   Truth      │  │ Optimization │  │              │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│       ↓                  ↓                  ↓            │
│   영구 저장           읽기 가속           이벤트 발행      │
└─────────────────────────────────────────────────────────┘
```

### 데이터베이스 역할 매트릭스

| 데이터베이스 | 역할 | 데이터 타입 | 읽기 성능 | 쓰기 성능 | 일관성 | 영구성 |
|-------------|------|-----------|----------|----------|--------|--------|
| PostgreSQL  | Primary Storage | 관계형 데이터 | 중간 | 높음 | 강함 | 영구적 |
| Redis       | Cache | Key-Value | 매우 높음 | 매우 높음 | 약함 | 일시적 |
| Kafka       | Event Bus | 메시지 스트림 | - | 높음 | - | 영구적 |

---

## 데이터베이스 엔진 선택

### CAP 정리에 따른 선택

```
소셜 그래프의 요구사항:

✅ Consistency (일관성)
   - 팔로우 관계는 정확해야 함
   - 중복 팔로우 방지 필요
   → PostgreSQL의 ACID 트랜잭션

✅ Availability (가용성)
   - 24/7 서비스 가용성
   - 빠른 응답 시간 (<100ms)
   → Redis 캐싱 + pgdog 샤딩

⚠️ Partition Tolerance (분할 내성)
   - 일부 샤드 장애 시에도 서비스 지속
   → pgdog 샤딩 + Kafka 메시징
```

### 왜 Graph Database를 사용하지 않았나?

#### 고려한 옵션들

| 데이터베이스 | 장점 | 단점 | 선택 여부 |
|-------------|------|------|----------|
| **Neo4j** | - 그래프 쿼리 최적화<br>- 복잡한 관계 탐색 | - 새로운 인프라 추가<br>- 팀 학습 곡선<br>- 기존 샤딩 불가 | ❌ |
| **ArangoDB** | - 멀티 모델 지원<br>- 유연성 | - 성숙도 낮음<br>- 커뮤니티 작음 | ❌ |
| **PostgreSQL** | - 기존 인프라 활용<br>- pgdog 샤딩 지원<br>- 팀 전문성 | - 복잡한 그래프 쿼리 느림 | ✅ |

#### PostgreSQL 선택 이유

1. **기존 인프라 재사용**
   ```
   이미 구축된 pgdog 샤딩 인프라 활용
   - 추가 운영 비용 없음
   - 기존 모니터링/백업 체계 활용
   ```

2. **충분한 성능**
   ```
   인덱싱 + Redis 캐싱으로 필요한 성능 달성
   - 단순 팔로우 관계 조회: O(1) with index
   - 복잡한 쿼리는 Redis에 캐싱
   ```

3. **팀 전문성**
   ```
   - 모든 개발자가 PostgreSQL 숙지
   - 빠른 개발 및 디버깅
   - 낮은 학습 곡선
   ```

---

## PostgreSQL - Primary Database

### 역할: 영구 저장소 (Source of Truth)

모든 팔로우 관계의 **신뢰할 수 있는 단일 저장소**

### 스키마 설계

#### 1. `follows` 테이블

```sql
CREATE TABLE follows (
    follower_id BIGINT NOT NULL,          -- 팔로우하는 사람
    following_id BIGINT NOT NULL,         -- 팔로우 받는 사람
    status VARCHAR(20) NOT NULL,          -- accepted, pending, rejected
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE,

    PRIMARY KEY (follower_id, following_id),
    CONSTRAINT check_not_self_follow CHECK (follower_id != following_id)
);
```

**설계 결정**:
- **복합 Primary Key**: (follower_id, following_id)로 중복 방지
- **status 컬럼**: Private 계정의 팔로우 요청 지원
- **CHECK 제약**: 자기 자신 팔로우 방지

#### 2. `user_graph_stats` 테이블

```sql
CREATE TABLE user_graph_stats (
    user_id BIGINT PRIMARY KEY,
    follower_count INT NOT NULL DEFAULT 0,
    following_count INT NOT NULL DEFAULT 0,
    pending_requests_count INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE
);
```

**목적**: 통계 쿼리 최적화
- COUNT(*) 대신 미리 계산된 값 사용
- 트리거로 자동 업데이트

### 인덱싱 전략

```sql
-- 1. 팔로워 조회 최적화
CREATE INDEX idx_follows_following_id
ON follows(following_id, status, created_at DESC);

-- 쿼리: "User X의 팔로워는?"
SELECT follower_id FROM follows
WHERE following_id = X AND status = 'accepted';
-- → Index Scan, ~5ms

-- 2. 팔로잉 조회 최적화
CREATE INDEX idx_follows_follower_id
ON follows(follower_id, status, created_at DESC);

-- 쿼리: "User X가 팔로우하는 사람들은?"
SELECT following_id FROM follows
WHERE follower_id = X AND status = 'accepted';
-- → Index Scan, ~5ms

-- 3. Pending 요청 최적화
CREATE INDEX idx_follows_pending
ON follows(following_id, status)
WHERE status = 'pending';

-- 쿼리: "내게 온 팔로우 요청은?"
SELECT follower_id FROM follows
WHERE following_id = X AND status = 'pending';
-- → Partial Index Scan, ~2ms
```

### ACID 트랜잭션 활용

#### 예시 1: 팔로우 + 통계 업데이트

```sql
BEGIN;
    -- 1. 팔로우 관계 생성
    INSERT INTO follows (follower_id, following_id, status)
    VALUES (1, 2, 'accepted');

    -- 2. 통계 업데이트 (트리거 자동 실행)
    -- follower의 following_count += 1
    -- following의 follower_count += 1

COMMIT;
```

**보장**:
- ✅ 관계 생성과 통계 업데이트는 원자적
- ✅ 중간 상태 노출 없음
- ✅ 오류 시 자동 롤백

#### 예시 2: 팔로우 요청 수락

```sql
BEGIN;
    -- 1. 상태 변경
    UPDATE follows
    SET status = 'accepted', updated_at = NOW()
    WHERE follower_id = 1 AND following_id = 2
      AND status = 'pending';

    -- 2. 통계 업데이트 (트리거)
    -- following의 follower_count += 1
    -- following의 pending_requests_count -= 1

COMMIT;
```

### pgdog 샤딩 전략

#### 샤딩 키: `follower_id`

```
Shard 0: follower_id % 3 = 0
Shard 1: follower_id % 3 = 1
Shard 2: follower_id % 3 = 2
```

**선택 이유**:
- 사용자별 팔로잉 목록 조회가 가장 빈번
- 단일 샤드에서 처리 가능

#### 샤딩 고려사항

**효율적인 쿼리**:
```sql
-- ✅ GOOD: follower_id로 필터링 (단일 샤드)
SELECT * FROM follows WHERE follower_id = 123;

-- ❌ BAD: following_id로만 필터링 (모든 샤드 스캔)
SELECT * FROM follows WHERE following_id = 456;
```

**해결책**: Redis 캐싱으로 following_id 쿼리 최적화

### 복잡한 쿼리 예시

#### 1. 친구의 친구 찾기 (팔로우 추천)

```sql
WITH user_following AS (
    -- 내가 팔로우하는 사람들
    SELECT following_id
    FROM follows
    WHERE follower_id = $1 AND status = 'accepted'
),
friends_of_friends AS (
    -- 친구들이 팔로우하는 사람들
    SELECT f.following_id, COUNT(*) as mutual_count
    FROM follows f
    WHERE f.follower_id IN (SELECT following_id FROM user_following)
      AND f.following_id != $1  -- 본인 제외
      AND f.following_id NOT IN (SELECT following_id FROM user_following)  -- 이미 팔로우 중인 사람 제외
      AND f.status = 'accepted'
    GROUP BY f.following_id
    ORDER BY mutual_count DESC
    LIMIT 10
)
SELECT following_id FROM friends_of_friends;
```

**성능**:
- 캐시 미스 시: ~200ms
- Redis에 결과 캐싱 (10분 TTL)

#### 2. 공통 팔로워 찾기

```sql
SELECT f1.follower_id
FROM follows f1
INNER JOIN follows f2 ON f1.follower_id = f2.follower_id
WHERE f1.following_id = $1  -- User A
  AND f2.following_id = $2  -- User B
  AND f1.status = 'accepted'
  AND f2.status = 'accepted'
LIMIT 20;
```

### 성능 특성

| 작업 | 시간 (인덱스 사용) | 시간 (Full Scan) |
|-----|-------------------|------------------|
| 팔로우 생성 | ~10ms | N/A |
| 팔로워 목록 (20개) | ~5ms | ~500ms |
| 팔로잉 목록 (20개) | ~5ms | ~500ms |
| 관계 확인 | ~2ms | ~300ms |
| 통계 조회 | ~1ms (stats 테이블) | ~50ms (COUNT) |

---

## Redis - Caching Layer

### 역할: 읽기 성능 최적화

PostgreSQL 부하를 줄이고 응답 시간을 10-100배 개선

### 캐싱 전략

#### 1. 캐시 키 설계

```python
# 캐시 키 패턴
graph:followers:{user_id}          # 팔로워 목록
graph:following:{user_id}          # 팔로잉 목록
graph:relationship:{user_id}:{other_user_id}  # 관계 상태
graph:stats:{user_id}              # 통계
```

**설계 원칙**:
- 계층적 네임스페이스 (`graph:` 접두사)
- 명확한 키 구조
- 패턴 매칭으로 대량 삭제 가능

#### 2. TTL 전략

```python
# TTL 설정 (초 단위)
CACHE_TTL_FOLLOWERS = 300      # 5분
CACHE_TTL_FOLLOWING = 300      # 5분
CACHE_TTL_RELATIONSHIP = 600   # 10분
CACHE_TTL_STATS = 60           # 1분
```

**TTL 설계 근거**:

| 데이터 | TTL | 이유 |
|--------|-----|------|
| 팔로워/팔로잉 목록 | 5분 | 자주 변경되지 않음, 약간의 지연 허용 |
| 관계 상태 | 10분 | 매우 안정적, 긴 캐싱 가능 |
| 통계 | 1분 | 빠른 업데이트 필요 (실시간성) |

#### 3. 캐시 데이터 구조

```python
# 팔로워 목록 (JSON 직렬화)
{
    "followers": [
        {"user_id": 123, "created_at": "2025-01-20T10:00:00Z"},
        {"user_id": 456, "created_at": "2025-01-19T15:30:00Z"}
    ],
    "cached_at": "2025-01-20T12:00:00Z"
}

# 관계 상태
{
    "relationship": "mutual",
    "is_following": true,
    "is_followed_by": true,
    "is_mutual": true
}

# 통계
{
    "follower_count": 1500,
    "following_count": 800,
    "pending_requests_count": 5
}
```

### 캐시 무효화 전략

#### Write-Through 패턴

```python
async def follow_user(self, follower_id: int, following_id: int):
    # 1. DB에 쓰기
    await self.db.create_follow(follower_id, following_id, "accepted")

    # 2. 즉시 캐시 무효화
    await self.cache.invalidate_user_cache(follower_id)
    await self.cache.invalidate_user_cache(following_id)
    await self.cache.invalidate_relationship_cache(follower_id, following_id)

    # 3. 다음 읽기 시 자동으로 재캐싱 (Cache-Aside)
```

**장점**:
- ✅ 즉시 일관성 보장
- ✅ 오래된 데이터 노출 방지
- ✅ 구현 단순

#### Cache-Aside 패턴

```python
async def get_followers(self, user_id: int):
    # 1. 캐시 확인
    cached = await self.cache.get_followers(user_id)
    if cached:
        return cached

    # 2. 캐시 미스: DB 조회
    followers = await self.db.get_followers(user_id)

    # 3. 캐시에 저장
    await self.cache.set_followers(user_id, followers)

    return followers
```

**장점**:
- ✅ 필요한 데이터만 캐싱 (메모리 효율)
- ✅ 캐시 장애 시에도 서비스 지속

### 성능 측정

#### 캐시 히트율

```
목표: 95%+ 캐시 히트율

실제 측정 (예상):
- 팔로워 목록: 97% 히트율
- 팔로잉 목록: 96% 히트율
- 관계 상태: 99% 히트율
- 통계: 98% 히트율
```

#### 응답 시간 비교

| 작업 | Redis (캐시 히트) | PostgreSQL | 개선율 |
|-----|------------------|-----------|--------|
| 팔로워 목록 (20개) | ~1ms | ~50ms | **50배** |
| 팔로잉 목록 (20개) | ~1ms | ~50ms | **50배** |
| 관계 상태 | ~0.5ms | ~5ms | **10배** |
| 통계 | ~0.5ms | ~10ms | **20배** |
| 대규모 팔로워 (100만) | ~5ms | ~500ms | **100배** |

### Hot/Cold 데이터 전략

```
Hot Data (인플루언서):
- 팔로워 수백만
- 조회 빈도 극도로 높음
→ 항상 Redis에 캐싱, TTL 길게 설정

Cold Data (일반 사용자):
- 팔로워 수백
- 조회 빈도 낮음
→ 캐시 미스 허용, 짧은 TTL
```

### Redis 메모리 관리

#### 메모리 예측

```
사용자당 평균 캐시 크기:
- 팔로워 목록 (20개): ~2KB
- 팔로잉 목록 (20개): ~2KB
- 관계 캐시: ~0.5KB
- 통계: ~0.2KB
→ 사용자당 ~5KB

1000만 사용자 (10% 활성):
100만 사용자 × 5KB = 5GB

Redis 메모리: 10GB (여유분 포함)
```

#### Eviction 정책

```python
# redis.conf
maxmemory 10gb
maxmemory-policy allkeys-lru  # LRU로 오래된 키 자동 삭제
```

---

## Kafka - Event Streaming

### 역할: 비동기 이벤트 발행 및 서비스 간 통신

Graph Service의 상태 변경을 다른 서비스에 실시간 알림

### 이벤트 토픽 설계

#### 1. `graph.follow` - 팔로우 이벤트

```json
{
  "event_type": "follow",
  "follower_id": 123,
  "following_id": 456,
  "status": "accepted",  // or "pending"
  "timestamp": "2025-01-20T10:00:00Z",
  "metadata": {
    "is_mutual": false
  }
}
```

**구독 서비스**:
- Notification Service: 팔로우 알림 전송
- Discovery Service: 피드 업데이트
- Analytics Service: 사용자 행동 분석

#### 2. `graph.unfollow` - 언팔로우 이벤트

```json
{
  "event_type": "unfollow",
  "follower_id": 123,
  "following_id": 456,
  "timestamp": "2025-01-20T11:00:00Z"
}
```

**구독 서비스**:
- Discovery Service: 피드에서 제거
- Analytics Service: 이탈 분석

#### 3. `graph.follow_accepted` - 요청 수락 이벤트

```json
{
  "event_type": "follow_request_accepted",
  "follower_id": 123,
  "following_id": 456,
  "timestamp": "2025-01-20T12:00:00Z"
}
```

**구독 서비스**:
- Notification Service: 수락 알림
- Discovery Service: 피드 구성

#### 4. `graph.follow_rejected` - 요청 거절 이벤트

```json
{
  "event_type": "follow_request_rejected",
  "follower_id": 123,
  "following_id": 456,
  "timestamp": "2025-01-20T13:00:00Z"
}
```

### 이벤트 기반 아키텍처

```
┌──────────────────────────────────────────────────────────────┐
│                      Graph Service                            │
│                                                                │
│  User Action → DB Update → Kafka Event Publish                │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ↓ Kafka Topics
         ┌─────────┴─────────────────┬──────────────┐
         ↓                           ↓              ↓
┌─────────────────┐        ┌─────────────────┐  ┌──────────────┐
│  Notification   │        │   Discovery     │  │  Analytics   │
│    Service      │        │    Service      │  │   Service    │
└─────────────────┘        └─────────────────┘  └──────────────┘
         │                          │                    │
         ↓                          ↓                    ↓
    푸시 알림 전송              피드 업데이트          사용자 분석
```

### 이벤트 발행 패턴

```python
# graph_service/kafka_producer.py

async def publish_follow_event(
    self, follower_id: int, following_id: int, status: str
):
    event_data = {
        "event_type": "follow",
        "follower_id": follower_id,
        "following_id": following_id,
        "status": status,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # 팔로워 ID를 키로 사용 (파티셔닝)
    await self.producer.send(
        topic="graph.follow",
        value=event_data,
        key=str(follower_id)
    )
```

### 파티셔닝 전략

```
Kafka Topic: graph.follow (3 partitions)

Key: follower_id % 3
Partition 0: follower_id % 3 = 0
Partition 1: follower_id % 3 = 1
Partition 2: follower_id % 3 = 2
```

**장점**:
- 같은 사용자의 이벤트는 순서 보장
- 병렬 처리로 높은 처리량

### 신뢰성 보장

#### At-Least-Once Delivery

```python
# Kafka 프로듀서 설정
producer = AIOKafkaProducer(
    bootstrap_servers='localhost:9092',
    acks='all',  # 모든 레플리카 확인
    retries=3,   # 재시도
    enable_idempotence=True  # 중복 방지
)
```

#### 실패 처리

```python
try:
    await kafka_producer.publish_follow_event(follower_id, following_id, status)
except Exception as e:
    # Kafka 실패해도 핵심 기능(팔로우)은 성공
    logger.error(f"Kafka publish failed: {e}")
    # 별도 재시도 큐에 추가 (선택적)
```

**설계 원칙**:
- ✅ Kafka 장애가 핵심 기능을 막지 않음
- ✅ 이벤트는 best-effort로 발행
- ⚠️ 중요한 이벤트는 재시도 메커니즘 필요

### 이벤트 스키마 진화

```json
// Version 1
{
  "event_type": "follow",
  "follower_id": 123,
  "following_id": 456
}

// Version 2 (하위 호환)
{
  "event_type": "follow",
  "follower_id": 123,
  "following_id": 456,
  "status": "accepted",  // 새 필드
  "schema_version": 2
}
```

**원칙**:
- 기존 필드 유지 (하위 호환)
- 새 필드는 optional
- schema_version으로 버전 관리

---

## 데이터 흐름

### 쓰기 흐름 (Write Path)

#### 시나리오: 사용자 A가 사용자 B를 팔로우

```
1. API Request
   POST /api/v1/graph/follow/456
   Authorization: Bearer {token}

2. Authentication
   → Auth Service: JWT 검증
   → User A (ID: 123) 인증 성공

3. Business Logic
   → Private 계정 여부 확인
   → 팔로우 제한 확인
   → Status 결정: "accepted" or "pending"

4. Database Write
   → PostgreSQL: INSERT INTO follows
   → 트리거 실행: user_graph_stats 업데이트

5. Cache Invalidation
   → Redis: DELETE graph:followers:456
   → Redis: DELETE graph:following:123
   → Redis: DELETE graph:stats:456
   → Redis: DELETE graph:stats:123

6. Event Publishing
   → Kafka: Publish to graph.follow

7. Response
   ← HTTP 200 OK
   {
     "success": true,
     "status": "accepted",
     "message": "Successfully followed user"
   }
```

**성능**:
- 총 소요 시간: ~30-50ms
- DB Write: ~10ms
- Cache Invalidation: ~5ms
- Kafka Publish: ~10ms (비동기)

### 읽기 흐름 (Read Path)

#### 시나리오 1: 캐시 히트

```
1. API Request
   GET /api/v1/graph/followers/456

2. Cache Check
   → Redis: GET graph:followers:456
   → Cache HIT! ✅

3. Response
   ← HTTP 200 OK (응답 시간: ~5ms)
   {
     "followers": [...],
     "total": 1500,
     "page": 1
   }
```

#### 시나리오 2: 캐시 미스

```
1. API Request
   GET /api/v1/graph/followers/456

2. Cache Check
   → Redis: GET graph:followers:456
   → Cache MISS! ❌

3. Database Query
   → PostgreSQL: SELECT follower_id FROM follows
                  WHERE following_id = 456
                  LIMIT 20
   → 결과: 20개 레코드 (응답 시간: ~50ms)

4. Cache Write
   → Redis: SET graph:followers:456 [...]
   → TTL: 300초

5. Response
   ← HTTP 200 OK (응답 시간: ~60ms)
```

### 복합 작업 흐름

#### 시나리오: 팔로우 요청 수락

```
1. API Request
   POST /api/v1/graph/requests/123
   Body: {"action": "accept"}

2. Validation
   → DB: 요청 존재 여부 확인
   → DB: status = 'pending' 확인

3. Transaction Start
   BEGIN;

4. Status Update
   → UPDATE follows SET status = 'accepted'

5. Trigger Execution
   → user_graph_stats 자동 업데이트

6. Transaction Commit
   COMMIT;

7. Cache Invalidation (Cascade)
   → 팔로워 캐시 삭제
   → 팔로잉 캐시 삭제
   → 관계 캐시 삭제
   → 통계 캐시 삭제

8. Event Publishing
   → Kafka: graph.follow_accepted

9. Side Effects (비동기)
   → Notification Service: 알림 전송
   → Discovery Service: 피드 업데이트
```

---

## 성능 최적화

### 1. 인덱스 최적화

#### Covering Index

```sql
-- 쿼리가 인덱스만으로 완료되도록 설계
CREATE INDEX idx_follows_covering
ON follows(following_id, status, follower_id, created_at);

-- 이 쿼리는 테이블 접근 없이 인덱스만 사용
SELECT follower_id, created_at
FROM follows
WHERE following_id = 456 AND status = 'accepted'
ORDER BY created_at DESC
LIMIT 20;
```

**효과**:
- I/O 감소
- 응답 시간 30% 개선

#### Partial Index

```sql
-- pending 상태만 인덱싱 (메모리 절약)
CREATE INDEX idx_follows_pending
ON follows(following_id, created_at)
WHERE status = 'pending';
```

**효과**:
- 인덱스 크기 90% 감소
- pending 쿼리 50% 빠름

### 2. 배치 처리

#### 대량 팔로워 조회

```python
# ❌ N+1 쿼리 문제
followers = await db.get_followers(user_id)
for follower in followers:
    user_info = await auth_service.get_user(follower.user_id)  # N번 호출

# ✅ 배치 조회
followers = await db.get_followers(user_id)
follower_ids = [f.user_id for f in followers]
users_info = await auth_service.get_users_batch(follower_ids)  # 1번 호출
```

### 3. 연결 풀링

```python
# database.py
pool = await asyncpg.create_pool(
    dsn=DATABASE_URL,
    min_size=10,    # 최소 연결 유지
    max_size=50,    # 최대 연결 수
    command_timeout=60
)
```

**효과**:
- 연결 생성 오버헤드 제거
- 동시 요청 처리 능력 향상

### 4. 쿼리 최적화

#### EXPLAIN ANALYZE 활용

```sql
EXPLAIN ANALYZE
SELECT follower_id FROM follows
WHERE following_id = 456 AND status = 'accepted';

-- 결과 분석
Index Scan using idx_follows_following_id on follows
  (cost=0.43..8.45 rows=1 width=8)
  (actual time=0.025..0.027 rows=1 loops=1)
Planning Time: 0.103 ms
Execution Time: 0.052 ms
```

### 5. 캐시 워밍

```python
# 서비스 시작 시 인기 사용자 캐시 프리로드
async def warm_cache():
    top_users = await db.get_top_users(limit=1000)
    for user in top_users:
        followers = await db.get_followers(user.id)
        await cache.set_followers(user.id, followers)
```

---

## 확장성 전략

### 수평 확장 (Horizontal Scaling)

#### 1. 데이터베이스 샤딩

```
현재: 3 샤드 (Shard 0, 1, 2)
→ 확장: 6 샤드 (재샤딩)

User ID % 3 → User ID % 6
```

**재샤딩 전략**:
- Consistent Hashing 고려
- 점진적 마이그레이션
- Read Replica 활용

#### 2. Redis 클러스터링

```
현재: 단일 Redis 인스턴스
→ 확장: Redis Cluster (3 마스터 + 3 레플리카)

자동 샤딩:
- 16384 슬롯
- CRC16 해싱
```

#### 3. Kafka 파티션 증가

```
현재: 3 파티션
→ 확장: 9 파티션

처리량:
3 파티션: ~30,000 msg/s
9 파티션: ~90,000 msg/s
```

### 수직 확장 (Vertical Scaling)

#### PostgreSQL 튜닝

```sql
-- postgresql.conf
shared_buffers = 256MB → 2GB
effective_cache_size = 1GB → 8GB
work_mem = 4MB → 32MB
max_connections = 100 → 500
```

#### Redis 메모리 증설

```
현재: 10GB
→ 확장: 50GB

사용자 커버리지:
10GB: 200만 활성 사용자
50GB: 1000만 활성 사용자
```

### 읽기 확장

#### Read Replica 추가

```
Primary DB (쓰기)
    ↓ 복제
Read Replica 1 (읽기)
Read Replica 2 (읽기)
Read Replica 3 (읽기)
```

```python
# 쓰기는 Primary로
await primary_db.create_follow(follower_id, following_id)

# 읽기는 Replica로
followers = await replica_db.get_followers(user_id)
```

---

## 운영 고려사항

### 모니터링

#### 핵심 메트릭

```yaml
PostgreSQL:
  - Query Latency (p50, p95, p99)
  - Connection Pool Usage
  - Slow Query Log (>100ms)
  - Replication Lag

Redis:
  - Hit Rate (목표: >95%)
  - Memory Usage
  - Eviction Rate
  - Command Latency

Kafka:
  - Producer Lag
  - Consumer Lag
  - Message Rate
  - Partition Distribution
```

#### 알림 설정

```
Critical:
- DB Connection Pool > 90%
- Redis Hit Rate < 80%
- Kafka Consumer Lag > 10000

Warning:
- Query Latency p99 > 100ms
- Cache Eviction Rate > 10%
- Kafka Partition Imbalance > 20%
```

### 백업 및 복구

#### PostgreSQL 백업

```bash
# 일일 전체 백업
pg_basebackup -h shard_0 -D /backup/shard_0

# WAL 아카이빙 (PITR 지원)
archive_mode = on
archive_command = 'cp %p /archive/%f'
```

#### Redis 백업

```bash
# RDB 스냅샷 (일일)
SAVE

# AOF 복제 (실시간)
appendonly yes
appendfsync everysec
```

### 장애 대응

#### 시나리오 1: PostgreSQL 샤드 장애

```
1. 자동 감지 (헬스체크)
2. 해당 샤드 트래픽 중단
3. 대기 중인 레플리카로 페일오버
4. DNS 업데이트
5. 서비스 복구

예상 다운타임: ~2분
```

#### 시나리오 2: Redis 장애

```
1. Redis 연결 실패 감지
2. 자동으로 PostgreSQL로 폴백
3. Redis 재시작
4. 캐시 워밍
5. 정상 작동 복구

서비스 영향: 응답 시간 10배 증가 (서비스는 지속)
```

#### 시나리오 3: Kafka 장애

```
1. Kafka 발행 실패
2. 로그에 에러 기록
3. 재시도 큐에 추가 (선택적)
4. Kafka 복구 후 재발행

핵심 기능 영향: 없음 (팔로우는 정상 작동)
부가 기능 영향: 알림 지연
```

### 데이터 일관성 검증

#### 정기 검증 작업

```sql
-- 통계 테이블과 실제 COUNT 비교
SELECT
    s.user_id,
    s.follower_count as cached_count,
    (SELECT COUNT(*) FROM follows WHERE following_id = s.user_id AND status = 'accepted') as actual_count
FROM user_graph_stats s
WHERE s.follower_count != (SELECT COUNT(*) FROM follows WHERE following_id = s.user_id AND status = 'accepted')
LIMIT 100;

-- 불일치 발견 시 재계산
UPDATE user_graph_stats SET follower_count = (
    SELECT COUNT(*) FROM follows WHERE following_id = user_id AND status = 'accepted'
);
```

### 보안

#### SQL Injection 방지

```python
# ✅ Parameterized Query
query = "SELECT * FROM follows WHERE follower_id = $1"
await db.execute(query, user_id)

# ❌ String Concatenation (절대 금지)
query = f"SELECT * FROM follows WHERE follower_id = {user_id}"
```

#### Rate Limiting

```python
# 팔로우 스팸 방지
MAX_FOLLOWS_PER_HOUR = 200

# Redis로 카운팅
key = f"rate_limit:follow:{user_id}:{hour}"
count = await redis.incr(key)
await redis.expire(key, 3600)

if count > MAX_FOLLOWS_PER_HOUR:
    raise HTTPException(429, "Too many follow requests")
```

---

## 결론

Graph Service의 데이터베이스 아키텍처는:

### 핵심 원칙

1. **적재적소 (Right Tool for the Job)**
   - PostgreSQL: 영구 저장 및 복잡한 쿼리
   - Redis: 고속 캐싱
   - Kafka: 비동기 이벤트

2. **성능과 일관성의 균형**
   - 강한 일관성: PostgreSQL ACID
   - 최종 일관성: Redis Cache
   - 비동기 처리: Kafka Events

3. **확장성 우선**
   - pgdog 샤딩
   - Redis 클러스터
   - Kafka 파티셔닝

4. **운영 안정성**
   - 모니터링 및 알림
   - 백업 및 복구
   - 장애 대응 계획

### 예상 성능

| 지표 | 목표 | 예상 달성 |
|-----|------|---------|
| API 응답 시간 (p95) | <100ms | ✅ ~50ms |
| 캐시 히트율 | >90% | ✅ ~97% |
| 동시 사용자 | 100만+ | ✅ 지원 |
| 처리량 | 10,000 req/s | ✅ 지원 |
| 가용성 | 99.9% | ✅ 달성 가능 |

이 아키텍처로 **수백만 사용자**를 지원하는 **안정적이고 확장 가능한** 소셜 그래프 서비스를 운영할 수 있습니다! 🚀
