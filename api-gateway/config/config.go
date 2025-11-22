package config

import (
	"fmt"
	"os"
	"strconv"
	"time"

	"github.com/joho/godotenv"
)

type Config struct {
	Environment string
	Port        int

	// Service URLs
	AuthServiceURL     string
	MediaServiceURL    string
	PostServiceURL     string
	GraphServiceURL    string
	NewsfeedServiceURL string

	// JWT Configuration
	JWTSecret string

	// Rate Limiting
	RateLimitRPS   int
	RateLimitBurst int

	// Redis Configuration
	RedisAddr     string
	RedisPassword string
	RedisDB       int

	// Timeouts
	ReadTimeout  time.Duration
	WriteTimeout time.Duration
	IdleTimeout  time.Duration

	// Proxy Timeout
	ProxyTimeout time.Duration
}

func Load() (*Config, error) {
	// Load .env file if exists (optional in production)
	_ = godotenv.Load()

	cfg := &Config{
		Environment: getEnv("ENVIRONMENT", "development"),
		Port:        getEnvAsInt("PORT", 8080),

		// Service URLs
		AuthServiceURL:     getEnv("AUTH_SERVICE_URL", "http://auth-service:8001"),
		MediaServiceURL:    getEnv("MEDIA_SERVICE_URL", "http://media-service:8000"),
		PostServiceURL:     getEnv("POST_SERVICE_URL", "http://post-service:8002"),
		GraphServiceURL:    getEnv("GRAPH_SERVICE_URL", "http://graph-service:8003"),
		NewsfeedServiceURL: getEnv("NEWSFEED_SERVICE_URL", "http://newsfeed-service:8004"),

		// JWT Configuration
		JWTSecret: getEnv("JWT_SECRET", "your-secret-key"),

		// Rate Limiting
		RateLimitRPS:   getEnvAsInt("RATE_LIMIT_RPS", 100),
		RateLimitBurst: getEnvAsInt("RATE_LIMIT_BURST", 200),

		// Redis Configuration
		RedisAddr:     getEnv("REDIS_ADDR", "redis:6379"),
		RedisPassword: getEnv("REDIS_PASSWORD", ""),
		RedisDB:       getEnvAsInt("REDIS_DB", 0),

		// Timeouts
		ReadTimeout:  time.Duration(getEnvAsInt("READ_TIMEOUT_SEC", 30)) * time.Second,
		WriteTimeout: time.Duration(getEnvAsInt("WRITE_TIMEOUT_SEC", 30)) * time.Second,
		IdleTimeout:  time.Duration(getEnvAsInt("IDLE_TIMEOUT_SEC", 120)) * time.Second,
		ProxyTimeout: time.Duration(getEnvAsInt("PROXY_TIMEOUT_SEC", 30)) * time.Second,
	}

	if err := cfg.Validate(); err != nil {
		return nil, err
	}

	return cfg, nil
}

func (c *Config) Validate() error {
	if c.JWTSecret == "your-secret-key" && c.Environment == "production" {
		return fmt.Errorf("JWT_SECRET must be set in production")
	}

	if c.Port <= 0 || c.Port > 65535 {
		return fmt.Errorf("invalid port number: %d", c.Port)
	}

	return nil
}

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func getEnvAsInt(key string, defaultValue int) int {
	valueStr := os.Getenv(key)
	if valueStr == "" {
		return defaultValue
	}

	value, err := strconv.Atoi(valueStr)
	if err != nil {
		return defaultValue
	}

	return value
}
