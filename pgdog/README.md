# pg_dog

[PgDog](https://github.com/pgdogdev/pgdog) is a transaction pooler and logical replication manager that can shard PostgreSQL.
Written in Rust, PgDog is fast, secure and can manage hundreds of databases and hundreds of thousands of connections.

## Running pg_dog

### Kubernetes

pg_dog can be deployed on Kuberentes using helm.

```bash
git clone https://github.com/pgdogdev/helm && \
cd helm && \
helm install -f values.yaml pgdog ./
```

### Docker

The provided docker-compose file can be used to run pg_dog locally.
It creates 3 shards of ParadeDB with PostgreSQL 17.

```bash
docker-compose up -d
```

Once started, you can connect to pg_dog using the following command:

```bash
PGPASSWORD=postgres psql -h 127.0.0.1 -p 6432 -U postgres
```

## High-Availability & Disaster Recovery

샤드 추가 시나리오:
```
# 1. 새 샤드 생성
createdb instagram_dm_shard_4

# 2. 스키마 복사
pg_dump --schema-only instagram_dm_shard_0 | psql instagram_dm_shard_4

# 3. pg_dog 설정 업데이트 (다운타임 없음)
# pgdog.toml에 새 샤드 추가

# 4. 논리적 복제를 통한 데이터 재분산 (pg_dog 자동 처리)
# 기존 데이터의 일부가 새 샤드로 자동 이동
```

## Features

```python
# 1. 사용자 대화방 목록 (완벽한 단일 샤드)
async def get_user_conversations(user_id: int):
    return await db.fetch_all("""
        SELECT conversation_id, conversation_name, last_message_content, 
               last_message_at, unread_count
        FROM user_conversation_list 
        WHERE user_id = $1 AND is_archived = false
        ORDER BY last_message_at DESC
        LIMIT 20
    """, user_id)
    # pg_dog: user_id = $1로 자동 라우팅

# 2. 대화방 메시지 조회 (완벽한 단일 샤드)
async def get_conversation_messages(user_id: int, conversation_id: int):
    return await db.fetch_all("""
        SELECT original_message_id, sender_id, content, 
               has_attachments, created_at, is_read
        FROM user_messages 
        WHERE recipient_user_id = $1 AND conversation_id = $2
        ORDER BY created_at DESC
        LIMIT 50
    """, user_id, conversation_id)
    # pg_dog: recipient_user_id = $1로 자동 라우팅

# 3. 메시지 전송 (발신자 샤드에 저장)
async def send_message(sender_id: int, conversation_id: int, content: str):
    message = await db.fetch_one("""
        INSERT INTO messages (conversation_id, sender_id, type_id, content)
        VALUES ($1, $2, 1, $3)
        RETURNING id
    """, conversation_id, sender_id, content)
    # pg_dog: sender_id를 통해 자동 라우팅
    # 트리거가 자동으로 모든 참가자에게 복제
```
