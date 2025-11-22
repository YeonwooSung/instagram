package middleware

import (
	"net/http"
	"sync"

	"github.com/gin-gonic/gin"
	"golang.org/x/time/rate"
)

// RateLimiter implements per-IP rate limiting using token bucket algorithm
type RateLimiter struct {
	limiters map[string]*rate.Limiter
	mu       sync.RWMutex
	rps      int
	burst    int
}

// NewRateLimiter creates a new rate limiter
func NewRateLimiter(rps, burst int) *RateLimiter {
	return &RateLimiter{
		limiters: make(map[string]*rate.Limiter),
		rps:      rps,
		burst:    burst,
	}
}

// getLimiter returns a limiter for the given key (IP address)
func (rl *RateLimiter) getLimiter(key string) *rate.Limiter {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	limiter, exists := rl.limiters[key]
	if !exists {
		limiter = rate.NewLimiter(rate.Limit(rl.rps), rl.burst)
		rl.limiters[key] = limiter
	}

	return limiter
}

// RateLimit middleware enforces rate limiting per IP address
func (rl *RateLimiter) RateLimit() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Get client IP as the rate limit key
		key := c.ClientIP()

		// Get limiter for this client
		limiter := rl.getLimiter(key)

		// Check if request is allowed
		if !limiter.Allow() {
			c.JSON(http.StatusTooManyRequests, gin.H{
				"error": "Rate limit exceeded",
			})
			c.Abort()
			return
		}

		c.Next()
	}
}

// UserRateLimit middleware enforces rate limiting per authenticated user
func (rl *RateLimiter) UserRateLimit() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Try to get user ID from context (set by JWT middleware)
		userID, exists := c.Get("user_id")
		var key string

		if exists {
			// Use user ID if authenticated
			key = userID.(string)
		} else {
			// Fall back to IP address
			key = c.ClientIP()
		}

		limiter := rl.getLimiter(key)

		if !limiter.Allow() {
			c.JSON(http.StatusTooManyRequests, gin.H{
				"error": "Rate limit exceeded",
			})
			c.Abort()
			return
		}

		c.Next()
	}
}
