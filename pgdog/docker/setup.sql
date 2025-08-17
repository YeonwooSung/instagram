-- 인스타그램 DM 시스템 데이터베이스 스키마 (pg_dog 샤딩 최적화)

-- =============================================================================
-- ENUM 테이블들 (모든 샤드에 동일하게 복제되어야 함)
-- =============================================================================

-- 대화방 타입 (pg_dog의 cross-shard 쿼리로 관리)
CREATE TABLE conversation_types (
    id SMALLINT PRIMARY KEY,
    name VARCHAR(20) UNIQUE NOT NULL
);
INSERT INTO conversation_types VALUES (1, 'direct'), (2, 'group');

-- 메시지 타입
CREATE TABLE message_types (
    id SMALLINT PRIMARY KEY,
    name VARCHAR(20) UNIQUE NOT NULL
);
INSERT INTO message_types VALUES 
(1, 'text'), (2, 'image'), (3, 'video'), 
(4, 'audio'), (5, 'file'), (6, 'system');

-- 첨부파일 타입
CREATE TABLE attachment_types (
    id SMALLINT PRIMARY KEY,
    name VARCHAR(20) UNIQUE NOT NULL,
    max_size_mb INTEGER NOT NULL,
    allowed_extensions TEXT[] NOT NULL
);
INSERT INTO attachment_types VALUES 
(1, 'image', 10, ARRAY['jpg','jpeg','png','gif','webp']),
(2, 'video', 100, ARRAY['mp4','mov','avi','mkv']),
(3, 'audio', 50, ARRAY['mp3','wav','m4a','ogg']),
(4, 'document', 50, ARRAY['pdf','doc','docx','txt','rtf']),
(5, 'archive', 200, ARRAY['zip','rar','7z','tar']);

-- 참가자 역할
CREATE TABLE participant_roles (
    id SMALLINT PRIMARY KEY,
    name VARCHAR(20) UNIQUE NOT NULL
);
INSERT INTO participant_roles VALUES (1, 'admin'), (2, 'member');

-- 메시지 상태
CREATE TABLE message_statuses (
    id SMALLINT PRIMARY KEY,
    name VARCHAR(20) UNIQUE NOT NULL
);
INSERT INTO message_statuses VALUES (1, 'sent'), (2, 'delivered'), (3, 'read');

-- =============================================================================
-- 메인 테이블들 (user_id 기반 샤딩 - pg_dog 자동 라우팅)
-- =============================================================================

-- 사용자 테이블 (샤딩 키: id)
-- pg_dog: WHERE users.id = $1 형태로 자동 라우팅
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY, -- 샤딩 키 (pg_dog가 자동 인식)
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    profile_image_url TEXT,
    is_active BOOLEAN DEFAULT true,
    last_seen_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);


-- 대화방 테이블 (모든 참가자가 복제본을 가짐 - 비정규화)
-- pg_dog: WHERE conversations.creator_user_id = $1 또는 참가자 정보로 라우팅
CREATE TABLE conversations (
    id BIGSERIAL PRIMARY KEY,
    creator_user_id BIGINT NOT NULL, -- 샤딩 키 (대화방 생성자)
    type_id SMALLINT NOT NULL REFERENCES conversation_types(id),
    name VARCHAR(100), -- 그룹 대화방 이름
    description TEXT,
    image_url TEXT,
    participant_count SMALLINT DEFAULT 0, -- 캐시된 참가자 수
    last_message_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 대화방 참가자 테이블 (각 사용자 샤드에 저장)
-- pg_dog: WHERE user_id = $1 형태로 완벽한 단일 샤드 라우팅
CREATE TABLE conversation_participants (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL, -- 샤딩 키 (pg_dog 자동 라우팅)
    role_id SMALLINT NOT NULL REFERENCES participant_roles(id) DEFAULT 2,
    display_name VARCHAR(100), -- 대화방에서의 표시명
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    left_at TIMESTAMP WITH TIME ZONE,
    is_muted BOOLEAN DEFAULT false,
    last_read_message_id BIGINT,
    unread_count INTEGER DEFAULT 0,
    
    -- pg_dog 최적화: user_id를 포함한 모든 쿼리가 단일 샤드로 라우팅됨
    UNIQUE(user_id, conversation_id)
);

-- 메시지 테이블 (발신자 기준 샤딩)
-- pg_dog: WHERE sender_id = $1 또는 conversation_id + sender_id 조합으로 라우팅
CREATE TABLE messages (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL,
    sender_id BIGINT NOT NULL, -- 샤딩 키 (pg_dog 자동 라우팅)
    reply_to_message_id BIGINT,
    reply_to_sender_id BIGINT, -- 원본 메시지 발신자 (크로스 샤드 참조용)
    type_id SMALLINT NOT NULL REFERENCES message_types(id),
    content TEXT,
    has_attachments BOOLEAN DEFAULT false,
    attachment_count SMALLINT DEFAULT 0 CHECK (attachment_count <= 20),
    is_edited BOOLEAN DEFAULT false,
    is_deleted BOOLEAN DEFAULT false,
    deleted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 메시지 복제 테이블 (대화방 참가자별로 메시지 복사본 저장 - 비정규화 접근)
-- pg_dog: WHERE recipient_user_id = $1로 완벽한 단일 샤드 라우팅
CREATE TABLE user_messages (
    id BIGSERIAL PRIMARY KEY,
    original_message_id BIGINT NOT NULL, -- 원본 메시지 ID
    conversation_id BIGINT NOT NULL,
    sender_id BIGINT NOT NULL,
    recipient_user_id BIGINT NOT NULL, -- 샤딩 키 (메시지를 받는 사용자)
    type_id SMALLINT NOT NULL REFERENCES message_types(id),
    content TEXT,
    has_attachments BOOLEAN DEFAULT false,
    attachment_count SMALLINT DEFAULT 0,
    is_read BOOLEAN DEFAULT false,
    read_at TIMESTAMP WITH TIME ZONE,
    is_deleted_by_recipient BOOLEAN DEFAULT false, -- 수신자가 삭제했는지
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- pg_dog 최적화: recipient_user_id 기반 완벽한 샤딩
    INDEX idx_user_messages_recipient_conv (recipient_user_id, conversation_id, created_at)
);

-- 첨부파일 테이블 (업로더 기준 샤딩)
-- pg_dog: WHERE uploader_user_id = $1로 자동 라우팅
CREATE TABLE chat_attachments (
    id BIGSERIAL PRIMARY KEY,
    message_id BIGINT NOT NULL,
    uploader_user_id BIGINT NOT NULL, -- 샤딩 키 (pg_dog 자동 라우팅)
    type_id SMALLINT NOT NULL REFERENCES attachment_types(id),
    original_filename VARCHAR(255) NOT NULL,
    stored_filename VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL, -- S3 키 또는 저장 경로
    file_size BIGINT NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    
    -- 미디어 메타데이터
    width INTEGER,
    height INTEGER,
    duration INTEGER, -- 초 단위
    
    -- 썸네일 정보
    thumbnail_path TEXT,
    thumbnail_width INTEGER,
    thumbnail_height INTEGER,
    
    -- 업로드 상태 (비트 플래그로 공간 절약)
    status_flags SMALLINT DEFAULT 1, -- 1:uploading, 2:completed, 4:failed, 8:thumbnail_ready
    upload_progress SMALLINT DEFAULT 0 CHECK (upload_progress >= 0 AND upload_progress <= 100),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 사용자별 첨부파일 참조 테이블 (빠른 조회용)
-- pg_dog: WHERE user_id = $1로 완벽한 단일 샤드 라우팅
CREATE TABLE user_attachments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL, -- 샤딩 키 (첨부파일에 접근할 수 있는 사용자)
    attachment_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    conversation_id BIGINT NOT NULL,
    uploader_user_id BIGINT NOT NULL, -- 원본 파일 위치 샤드 정보
    can_download BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(user_id, attachment_id)
);

-- 차단된 사용자 테이블 (차단한 사용자 기준 샤딩)
-- pg_dog: WHERE blocker_id = $1로 자동 라우팅
CREATE TABLE blocked_users (
    id BIGSERIAL PRIMARY KEY,
    blocker_id BIGINT NOT NULL, -- 샤딩 키 (pg_dog 자동 라우팅)
    blocked_id BIGINT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(blocker_id, blocked_id)
);

-- 알림 설정 테이블 (사용자별 샤딩)
-- pg_dog: WHERE user_id = $1로 자동 라우팅
CREATE TABLE notification_settings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL, -- 샤딩 키 (pg_dog 자동 라우팅)
    conversation_id BIGINT,
    
    -- 비트 플래그로 설정 관리 (공간 절약)
    -- 1:enabled, 2:sound, 4:preview, 8:mentions_only, 16:do_not_disturb
    settings_flags INTEGER DEFAULT 7, -- 기본값: enabled + sound + preview
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(user_id, conversation_id)
);

-- 사용자별 대화방 목록 캐시 (빠른 조회용 비정규화)
-- pg_dog: WHERE user_id = $1로 완벽한 단일 샤드 라우팅
CREATE TABLE user_conversation_list (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL, -- 샤딩 키 (pg_dog 자동 라우팅)
    conversation_id BIGINT NOT NULL,
    other_user_id BIGINT, -- direct 대화방의 상대방 (NULL이면 그룹)
    conversation_name VARCHAR(100), -- 캐시된 대화방 이름
    last_message_content TEXT, -- 마지막 메시지 내용 (일부)
    last_message_at TIMESTAMP WITH TIME ZONE,
    unread_count INTEGER DEFAULT 0,
    is_muted BOOLEAN DEFAULT false,
    is_archived BOOLEAN DEFAULT false,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(user_id, conversation_id)
);

-- =============================================================================
-- pg_dog 최적화 인덱스 (샤딩 키 우선)
-- =============================================================================

-- users 테이블 - 샤딩 키가 이미 PRIMARY KEY이므로 추가 인덱스만
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_last_seen ON users(last_seen_at);

-- conversations 테이블
CREATE INDEX idx_conversations_creator ON conversations(creator_user_id);
CREATE INDEX idx_conversations_last_message ON conversations(last_message_at DESC);

-- conversation_participants 테이블 - user_id 우선 인덱스
CREATE INDEX idx_conv_participants_user ON conversation_participants(user_id);
CREATE INDEX idx_conv_participants_active ON conversation_participants(user_id, left_at) WHERE left_at IS NULL;
CREATE INDEX idx_conv_participants_unread ON conversation_participants(user_id, unread_count) WHERE unread_count > 0;

-- messages 테이블 - sender_id 우선 인덱스
CREATE INDEX idx_messages_sender ON messages(sender_id);
CREATE INDEX idx_messages_sender_conv ON messages(sender_id, conversation_id, created_at);
CREATE INDEX idx_messages_conv_time ON messages(conversation_id, created_at);
CREATE INDEX idx_messages_reply_to ON messages(reply_to_message_id, reply_to_sender_id) WHERE reply_to_message_id IS NOT NULL;

-- user_messages 테이블 - recipient_user_id 최적화
CREATE INDEX idx_user_messages_recipient ON user_messages(recipient_user_id);
CREATE INDEX idx_user_messages_conv ON user_messages(recipient_user_id, conversation_id, created_at DESC);
CREATE INDEX idx_user_messages_unread ON user_messages(recipient_user_id, is_read) WHERE is_read = false;

-- chat_attachments 테이블 - uploader_user_id 우선
CREATE INDEX idx_attachments_uploader ON chat_attachments(uploader_user_id);
CREATE INDEX idx_attachments_message ON chat_attachments(message_id);
CREATE INDEX idx_attachments_type ON chat_attachments(type_id);

-- user_attachments 테이블 - user_id 우선
CREATE INDEX idx_user_attachments_user ON user_attachments(user_id);
CREATE INDEX idx_user_attachments_conv ON user_attachments(user_id, conversation_id, created_at);

-- user_conversation_list 테이블 - user_id 우선
CREATE INDEX idx_user_conv_list_user ON user_conversation_list(user_id);
CREATE INDEX idx_user_conv_list_updated ON user_conversation_list(user_id, updated_at DESC);
CREATE INDEX idx_user_conv_list_unread ON user_conversation_list(user_id, unread_count) WHERE unread_count > 0;

-- 샤딩 키를 첫 번째 컬럼으로 배치
CREATE INDEX idx_user_messages_optimal ON user_messages(recipient_user_id, conversation_id, created_at);
-- pg_dog가 recipient_user_id로 샤드를 찾은 후, 나머지 조건으로 빠른 필터링

-- =============================================================================
-- pg_dog 샤딩 설정을 위한 함수들
-- =============================================================================

-- 샤딩 키 검증 함수 (개발/디버깅용)
CREATE OR REPLACE FUNCTION validate_sharding_key(table_name TEXT, user_id BIGINT)
RETURNS BOOLEAN AS $$
BEGIN
    -- pg_dog가 user_id를 올바르게 인식할 수 있는지 확인
    CASE table_name
        WHEN 'users' THEN
            RETURN user_id IS NOT NULL;
        WHEN 'conversation_participants', 'user_messages', 'user_attachments', 
             'blocked_users', 'notification_settings', 'user_conversation_list' THEN
            RETURN user_id IS NOT NULL;
        WHEN 'messages', 'chat_attachments' THEN
            -- 이 테이블들은 sender_id/uploader_user_id로 샤딩됨
            RETURN user_id IS NOT NULL;
        ELSE
            RETURN false;
    END CASE;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- 대화방 참가자 추가 시 메시지 복제 함수
CREATE OR REPLACE FUNCTION replicate_messages_for_new_participant()
RETURNS TRIGGER AS $$
BEGIN
    -- 새 참가자에게 기존 메시지들을 복제 (최근 100개만)
    INSERT INTO user_messages (
        original_message_id, conversation_id, sender_id, recipient_user_id,
        type_id, content, has_attachments, attachment_count, created_at
    )
    SELECT 
        m.id, m.conversation_id, m.sender_id, NEW.user_id,
        m.type_id, m.content, m.has_attachments, m.attachment_count, m.created_at
    FROM messages m
    WHERE m.conversation_id = NEW.conversation_id
      AND m.is_deleted = false
    ORDER BY m.created_at DESC
    LIMIT 100;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 메시지 발송 시 모든 참가자에게 복제하는 함수
CREATE OR REPLACE FUNCTION distribute_message_to_participants()
RETURNS TRIGGER AS $$
BEGIN
    -- 모든 참가자에게 메시지 복제 (발신자 제외)
    INSERT INTO user_messages (
        original_message_id, conversation_id, sender_id, recipient_user_id,
        type_id, content, has_attachments, attachment_count, created_at
    )
    SELECT 
        NEW.id, NEW.conversation_id, NEW.sender_id, cp.user_id,
        NEW.type_id, NEW.content, NEW.has_attachments, NEW.attachment_count, NEW.created_at
    FROM conversation_participants cp
    WHERE cp.conversation_id = NEW.conversation_id
      AND cp.user_id != NEW.sender_id  -- 발신자는 제외
      AND cp.left_at IS NULL;
      
    -- 발신자 샤드에도 본인 메시지 복사본 저장 (읽음 처리용)
    INSERT INTO user_messages (
        original_message_id, conversation_id, sender_id, recipient_user_id,
        type_id, content, has_attachments, attachment_count, is_read, read_at, created_at
    ) VALUES (
        NEW.id, NEW.conversation_id, NEW.sender_id, NEW.sender_id,
        NEW.type_id, NEW.content, NEW.has_attachments, NEW.attachment_count, true, CURRENT_TIMESTAMP, NEW.created_at
    );
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 첨부파일 업로드 완료 시 참가자별 참조 생성
CREATE OR REPLACE FUNCTION create_attachment_references()
RETURNS TRIGGER AS $$
BEGIN
    -- 업로드 완료된 첨부파일에 대해 모든 대화방 참가자가 접근 가능하도록 참조 생성
    IF (NEW.status_flags & 2) > 0 AND (OLD.status_flags & 2) = 0 THEN -- 완료 상태로 변경됨
        INSERT INTO user_attachments (
            user_id, attachment_id, message_id, conversation_id, uploader_user_id
        )
        SELECT 
            cp.user_id, NEW.id, NEW.message_id, m.conversation_id, NEW.uploader_user_id
        FROM messages m
        JOIN conversation_participants cp ON cp.conversation_id = m.conversation_id
        WHERE m.id = NEW.message_id AND cp.left_at IS NULL;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- 트리거 설정
-- =============================================================================

-- 업데이트 시간 자동 갱신
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_conversations_updated_at BEFORE UPDATE ON conversations 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_notification_settings_updated_at BEFORE UPDATE ON notification_settings 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_conversation_list_updated_at BEFORE UPDATE ON user_conversation_list 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 대화방 참가자 추가 시 메시지 복제
CREATE TRIGGER replicate_messages_after_join AFTER INSERT ON conversation_participants
    FOR EACH ROW EXECUTE FUNCTION replicate_messages_for_new_participant();

-- 메시지 생성 시 참가자별 복제
CREATE TRIGGER distribute_message AFTER INSERT ON messages
    FOR EACH ROW EXECUTE FUNCTION distribute_message_to_participants();

-- 첨부파일 완료 시 참조 생성
CREATE TRIGGER create_attachment_refs AFTER UPDATE ON chat_attachments
    FOR EACH ROW EXECUTE FUNCTION create_attachment_references();

-- =============================================================================
-- pg_dog 샤딩을 위한 샘플 설정 (pgdog.toml 참조용)
-- =============================================================================

/*
# pgdog.toml 샘플 설정

[sharding]
# 샤딩 키 설정 - user_id 컬럼을 기본 샤딩 키로 사용
# pg_dog가 자동으로 user_id = $1 형태의 쿼리를 해당 샤드로 라우팅
sharding_key = "user_id"

# 샤드 설정 (4개 샤드로 시작)
[[shard]]
database = "instagram_dm_shard_0"
host = "localhost"
port = 5432
user = "pgdog"
password = "password"

[[shard]]
database = "instagram_dm_shard_1"
host = "localhost"
port = 5432
user = "pgdog"
password = "password"

[[shard]]
database = "instagram_dm_shard_2"
host = "localhost"
port = 5432
user = "pgdog"
password = "password"

[[shard]]
database = "instagram_dm_shard_3"
host = "localhost"
port = 5432
user = "pgdog"
password = "password"
*/

-- =============================================================================
-- 주요 쿼리 패턴 (pg_dog 최적화)
-- =============================================================================

-- 1. 사용자의 대화방 목록 조회 (단일 샤드 - 최적화됨)
/*
SELECT conversation_id, conversation_name, last_message_content, 
       last_message_at, unread_count, is_muted
FROM user_conversation_list 
WHERE user_id = $1 AND is_archived = false
ORDER BY last_message_at DESC
LIMIT 50;
-- pg_dog: user_id = $1로 자동으로 올바른 샤드에 라우팅됨
*/

-- 2. 대화방의 메시지 조회 (단일 샤드 - 최적화됨)
/*
SELECT original_message_id, sender_id, content, has_attachments, 
       attachment_count, is_read, created_at
FROM user_messages 
WHERE recipient_user_id = $1 AND conversation_id = $2
ORDER BY created_at DESC
LIMIT 50;
-- pg_dog: recipient_user_id = $1로 자동 라우팅
*/

-- 3. 읽지 않은 메시지 수 조회 (단일 샤드)
/*
SELECT COUNT(*) as unread_count
FROM user_messages 
WHERE recipient_user_id = $1 AND is_read = false;
-- pg_dog: recipient_user_id = $1로 자동 라우팅
*/

-- 4. 첨부파일 조회 (단일 샤드)
/*
SELECT ua.attachment_id, ca.original_filename, ca.file_path, ca.file_size
FROM user_attachments ua
JOIN chat_attachments ca ON ua.attachment_id = ca.id
WHERE ua.user_id = $1 AND ua.conversation_id = $2;
-- pg_dog: user_id = $1로 ua는 자동 라우팅, ca는 크로스 샤드 JOIN
*/
