-- Instagram 서비스 확장 스키마
-- 기존 setup.sql에 추가로 실행되어야 하는 스키마

-- =============================================================================
-- Auth Service를 위한 테이블 확장
-- =============================================================================

-- users 테이블 확장 (password 및 프로필 정보 추가)
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS website VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number VARCHAR(20);
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_private BOOLEAN DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS follower_count INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS following_count INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS post_count INTEGER DEFAULT 0;

-- Refresh Token 관리 테이블 (샤딩 키: user_id)
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL, -- 샤딩 키
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    is_revoked BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_hash ON refresh_tokens(token_hash) WHERE is_revoked = false;

-- 사용자 세션 테이블 (샤딩 키: user_id)
CREATE TABLE IF NOT EXISTS user_sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL, -- 샤딩 키
    session_token VARCHAR(255) NOT NULL,
    device_info TEXT,
    ip_address INET,
    user_agent TEXT,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_activity_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_user_sessions_user ON user_sessions(user_id);
CREATE INDEX idx_user_sessions_token ON user_sessions(session_token);

-- =============================================================================
-- Media Service를 위한 테이블
-- =============================================================================

-- 미디어 파일 타입
CREATE TABLE IF NOT EXISTS media_types (
    id SMALLINT PRIMARY KEY,
    name VARCHAR(20) UNIQUE NOT NULL
);

INSERT INTO media_types VALUES
(1, 'image'),
(2, 'video'),
(3, 'carousel')
ON CONFLICT (id) DO NOTHING;

-- 미디어 파일 메타데이터 (샤딩 키: user_id)
CREATE TABLE IF NOT EXISTS media_files (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL, -- 샤딩 키 (업로더)
    type_id SMALLINT NOT NULL REFERENCES media_types(id),
    post_id BIGINT, -- NULL이면 아직 게시물에 첨부되지 않음

    -- 원본 파일 정보
    original_filename VARCHAR(255) NOT NULL,
    stored_filename VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL, -- S3 경로
    file_size BIGINT NOT NULL,
    mime_type VARCHAR(100) NOT NULL,

    -- 미디어 메타데이터
    width INTEGER,
    height INTEGER,
    duration INTEGER, -- 비디오의 경우 초 단위
    aspect_ratio DECIMAL(10, 4),

    -- 썸네일 정보
    thumbnail_path TEXT,
    thumbnail_width INTEGER,
    thumbnail_height INTEGER,

    -- 처리된 버전들 (다양한 해상도)
    processed_versions JSONB, -- {small: 'path', medium: 'path', large: 'path'}

    -- 상태
    status VARCHAR(20) DEFAULT 'processing', -- processing, completed, failed
    upload_progress SMALLINT DEFAULT 0,

    -- EXIF 데이터
    exif_data JSONB,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_media_files_user ON media_files(user_id);
CREATE INDEX idx_media_files_post ON media_files(post_id);
CREATE INDEX idx_media_files_status ON media_files(status);

-- =============================================================================
-- Discovery Service를 위한 테이블
-- =============================================================================

-- 팔로우 관계 테이블 (샤딩 키: follower_id)
CREATE TABLE IF NOT EXISTS user_follows (
    id BIGSERIAL PRIMARY KEY,
    follower_id BIGINT NOT NULL, -- 샤딩 키 (팔로우하는 사람)
    following_id BIGINT NOT NULL, -- 팔로우되는 사람
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(follower_id, following_id)
);

CREATE INDEX idx_user_follows_follower ON user_follows(follower_id);
CREATE INDEX idx_user_follows_following ON user_follows(following_id);

-- 좋아요 테이블 (샤딩 키: user_id)
CREATE TABLE IF NOT EXISTS post_likes (
    id BIGSERIAL PRIMARY KEY,
    post_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL, -- 샤딩 키
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(post_id, user_id)
);

CREATE INDEX idx_post_likes_user ON post_likes(user_id);
CREATE INDEX idx_post_likes_post ON post_likes(post_id);

-- 댓글 테이블 (샤딩 키: user_id)
CREATE TABLE IF NOT EXISTS comments (
    id BIGSERIAL PRIMARY KEY,
    post_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL, -- 샤딩 키 (댓글 작성자)
    parent_comment_id BIGINT, -- 대댓글인 경우
    content TEXT NOT NULL,
    like_count INTEGER DEFAULT 0,
    is_deleted BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_comments_post ON comments(post_id, created_at);
CREATE INDEX idx_comments_user ON comments(user_id);
CREATE INDEX idx_comments_parent ON comments(parent_comment_id);

-- 댓글 좋아요 테이블 (샤딩 키: user_id)
CREATE TABLE IF NOT EXISTS comment_likes (
    id BIGSERIAL PRIMARY KEY,
    comment_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL, -- 샤딩 키
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(comment_id, user_id)
);

CREATE INDEX idx_comment_likes_user ON comment_likes(user_id);
CREATE INDEX idx_comment_likes_comment ON comment_likes(comment_id);

-- 해시태그 테이블 (글로벌 테이블 - 모든 샤드에 복제)
CREATE TABLE IF NOT EXISTS hashtags (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    post_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_hashtags_name ON hashtags(name);
CREATE INDEX idx_hashtags_post_count ON hashtags(post_count DESC);

-- 게시물-해시태그 연결 테이블 (샤딩 키: post_user_id)
CREATE TABLE IF NOT EXISTS post_hashtags (
    id BIGSERIAL PRIMARY KEY,
    post_id BIGINT NOT NULL,
    post_user_id BIGINT NOT NULL, -- 샤딩 키 (게시물 작성자 ID)
    hashtag_id BIGINT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(post_id, hashtag_id)
);

CREATE INDEX idx_post_hashtags_post ON post_hashtags(post_id);
CREATE INDEX idx_post_hashtags_hashtag ON post_hashtags(hashtag_id);
CREATE INDEX idx_post_hashtags_user ON post_hashtags(post_user_id);

-- 게시물 확장 (위치, 캡션, 좋아요 수 등)
ALTER TABLE posts ADD COLUMN IF NOT EXISTS caption TEXT;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS location VARCHAR(255);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS latitude DECIMAL(10, 8);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS longitude DECIMAL(11, 8);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS like_count INTEGER DEFAULT 0;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS comment_count INTEGER DEFAULT 0;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS share_count INTEGER DEFAULT 0;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS is_comments_disabled BOOLEAN DEFAULT false;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN DEFAULT false;

-- 저장된 게시물 테이블 (샤딩 키: user_id)
CREATE TABLE IF NOT EXISTS saved_posts (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL, -- 샤딩 키
    post_id BIGINT NOT NULL,
    collection_name VARCHAR(100), -- 저장 컬렉션 이름
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(user_id, post_id, collection_name)
);

CREATE INDEX idx_saved_posts_user ON saved_posts(user_id);
CREATE INDEX idx_saved_posts_collection ON saved_posts(user_id, collection_name);

-- 사용자 피드 캐시 (샤딩 키: user_id)
CREATE TABLE IF NOT EXISTS user_feed_cache (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL, -- 샤딩 키
    post_id BIGINT NOT NULL,
    post_user_id BIGINT NOT NULL, -- 게시물 작성자
    score DECIMAL(10, 4), -- 랭킹 점수
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_user_feed_cache_user ON user_feed_cache(user_id, score DESC);
CREATE INDEX idx_user_feed_cache_expires ON user_feed_cache(expires_at);

-- 인기 게시물 캐시 (글로벌 테이블)
CREATE TABLE IF NOT EXISTS trending_posts (
    id BIGSERIAL PRIMARY KEY,
    post_id BIGINT NOT NULL,
    post_user_id BIGINT NOT NULL,
    engagement_score DECIMAL(10, 4),
    time_decay_score DECIMAL(10, 4),
    final_score DECIMAL(10, 4),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_trending_posts_score ON trending_posts(final_score DESC);
CREATE INDEX idx_trending_posts_updated ON trending_posts(updated_at DESC);

-- =============================================================================
-- 트리거 및 함수
-- =============================================================================

-- 좋아요 수 업데이트 함수
CREATE OR REPLACE FUNCTION update_post_like_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE posts SET like_count = like_count + 1 WHERE id = NEW.post_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE posts SET like_count = like_count - 1 WHERE id = OLD.post_id;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_like_count_on_like
AFTER INSERT OR DELETE ON post_likes
FOR EACH ROW EXECUTE FUNCTION update_post_like_count();

-- 댓글 수 업데이트 함수
CREATE OR REPLACE FUNCTION update_post_comment_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE posts SET comment_count = comment_count + 1 WHERE id = NEW.post_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE posts SET comment_count = comment_count - 1 WHERE id = OLD.post_id;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_comment_count_on_comment
AFTER INSERT OR DELETE ON comments
FOR EACH ROW EXECUTE FUNCTION update_post_comment_count();

-- 팔로우 카운트 업데이트 함수
CREATE OR REPLACE FUNCTION update_follow_counts()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE users SET following_count = following_count + 1 WHERE id = NEW.follower_id;
        UPDATE users SET follower_count = follower_count + 1 WHERE id = NEW.following_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE users SET following_count = following_count - 1 WHERE id = OLD.follower_id;
        UPDATE users SET follower_count = follower_count - 1 WHERE id = OLD.following_id;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_follow_counts_trigger
AFTER INSERT OR DELETE ON user_follows
FOR EACH ROW EXECUTE FUNCTION update_follow_counts();

-- 게시물 수 업데이트 함수
CREATE OR REPLACE FUNCTION update_user_post_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE users SET post_count = post_count + 1 WHERE id = NEW.user_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE users SET post_count = post_count - 1 WHERE id = OLD.user_id;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_post_count_trigger
AFTER INSERT OR DELETE ON posts
FOR EACH ROW EXECUTE FUNCTION update_user_post_count();

-- 해시태그 게시물 수 업데이트 함수
CREATE OR REPLACE FUNCTION update_hashtag_post_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE hashtags SET post_count = post_count + 1 WHERE id = NEW.hashtag_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE hashtags SET post_count = post_count - 1 WHERE id = OLD.hashtag_id;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_hashtag_count_trigger
AFTER INSERT OR DELETE ON post_hashtags
FOR EACH ROW EXECUTE FUNCTION update_hashtag_post_count();
