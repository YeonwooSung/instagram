-- =============================================================================
-- Graph Service Schema
-- =============================================================================
-- This schema is for the Graph Service which handles follow/unfollow relationships
-- with support for private accounts and follow requests
--
-- Note: This is separate from the user_follows table used by Discovery Service
-- for backward compatibility and to support additional features like pending requests

-- Migration: Create follows table for social graph
-- Description: Stores follow relationships between users with status support
-- Version: 001
-- Date: 2025-01-20

-- Create follows table
CREATE TABLE IF NOT EXISTS follows (
    follower_id BIGINT NOT NULL,          -- User who is following (references users.id)
    following_id BIGINT NOT NULL,         -- User being followed (references users.id)
    status VARCHAR(20) NOT NULL DEFAULT 'accepted',  -- Status: accepted, pending, rejected
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),     -- When follow relationship was created
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),     -- When status was last updated

    -- Primary key: unique combination of follower and following
    PRIMARY KEY (follower_id, following_id),

    -- Constraints
    CONSTRAINT check_not_self_follow CHECK (follower_id != following_id),
    CONSTRAINT check_status CHECK (status IN ('accepted', 'pending', 'rejected'))
);

-- Create indexes for efficient queries

-- Index for getting followers of a user (who follows user X?)
CREATE INDEX IF NOT EXISTS idx_follows_following_id
ON follows(following_id, status, created_at DESC);

-- Index for getting following list (who does user X follow?)
CREATE INDEX IF NOT EXISTS idx_follows_follower_id
ON follows(follower_id, status, created_at DESC);

-- Index for pending requests
CREATE INDEX IF NOT EXISTS idx_follows_pending
ON follows(following_id, status)
WHERE status = 'pending';

-- Index for checking mutual follows
CREATE INDEX IF NOT EXISTS idx_follows_mutual
ON follows(follower_id, following_id, status)
WHERE status = 'accepted';

-- Comments
COMMENT ON TABLE follows IS 'Stores follow relationships between users with support for private accounts';
COMMENT ON COLUMN follows.follower_id IS 'ID of user who is following';
COMMENT ON COLUMN follows.following_id IS 'ID of user being followed';
COMMENT ON COLUMN follows.status IS 'Status of follow relationship: accepted (public account or approved), pending (private account awaiting approval), rejected';
COMMENT ON COLUMN follows.created_at IS 'Timestamp when follow relationship was created';
COMMENT ON COLUMN follows.updated_at IS 'Timestamp when status was last updated';

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_follows_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_follows_updated_at
    BEFORE UPDATE ON follows
    FOR EACH ROW
    EXECUTE FUNCTION update_follows_updated_at();

-- Create statistics table (optional - for caching aggregates)
CREATE TABLE IF NOT EXISTS user_graph_stats (
    user_id BIGINT PRIMARY KEY,           -- User ID (references users.id)
    follower_count INT NOT NULL DEFAULT 0,      -- Number of followers
    following_count INT NOT NULL DEFAULT 0,     -- Number of users being followed
    pending_requests_count INT NOT NULL DEFAULT 0,  -- Number of pending follow requests
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),    -- Last update timestamp

    -- Constraints
    CONSTRAINT check_non_negative_counts CHECK (
        follower_count >= 0 AND
        following_count >= 0 AND
        pending_requests_count >= 0
    )
);

-- Index for stats table
CREATE INDEX IF NOT EXISTS idx_user_graph_stats_user_id ON user_graph_stats(user_id);

-- Comments for stats table
COMMENT ON TABLE user_graph_stats IS 'Cached aggregate statistics for user graph relationships';
COMMENT ON COLUMN user_graph_stats.user_id IS 'User ID';
COMMENT ON COLUMN user_graph_stats.follower_count IS 'Cached count of followers';
COMMENT ON COLUMN user_graph_stats.following_count IS 'Cached count of users being followed';
COMMENT ON COLUMN user_graph_stats.pending_requests_count IS 'Cached count of pending follow requests';

-- Function to update user graph stats
CREATE OR REPLACE FUNCTION update_user_graph_stats(p_user_id BIGINT)
RETURNS VOID AS $$
BEGIN
    INSERT INTO user_graph_stats (user_id, follower_count, following_count, pending_requests_count, updated_at)
    SELECT
        p_user_id,
        COALESCE((SELECT COUNT(*) FROM follows WHERE following_id = p_user_id AND status = 'accepted'), 0) as follower_count,
        COALESCE((SELECT COUNT(*) FROM follows WHERE follower_id = p_user_id AND status = 'accepted'), 0) as following_count,
        COALESCE((SELECT COUNT(*) FROM follows WHERE following_id = p_user_id AND status = 'pending'), 0) as pending_requests_count,
        NOW()
    ON CONFLICT (user_id)
    DO UPDATE SET
        follower_count = EXCLUDED.follower_count,
        following_count = EXCLUDED.following_count,
        pending_requests_count = EXCLUDED.pending_requests_count,
        updated_at = NOW();
END;
$$ LANGUAGE plpgsql;

-- Trigger to update stats when follows change
CREATE OR REPLACE FUNCTION trigger_update_graph_stats()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' OR TG_OP = 'UPDATE' THEN
        PERFORM update_user_graph_stats(NEW.follower_id);
        PERFORM update_user_graph_stats(NEW.following_id);
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM update_user_graph_stats(OLD.follower_id);
        PERFORM update_user_graph_stats(OLD.following_id);
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_follows_stats_update
    AFTER INSERT OR UPDATE OR DELETE ON follows
    FOR EACH ROW
    EXECUTE FUNCTION trigger_update_graph_stats();
