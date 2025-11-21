-- Create databases for each service
CREATE DATABASE instagram_auth;
CREATE DATABASE instagram_media;
CREATE DATABASE instagram_graph;
CREATE DATABASE instagram_newsfeed;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE instagram_auth TO postgres;
GRANT ALL PRIVILEGES ON DATABASE instagram_media TO postgres;
GRANT ALL PRIVILEGES ON DATABASE instagram_graph TO postgres;
GRANT ALL PRIVILEGES ON DATABASE instagram_newsfeed TO postgres;
