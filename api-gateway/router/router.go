package router

import (
	"net/http"

	"github.com/YeonwooSung/instagram/api-gateway/config"
	"github.com/YeonwooSung/instagram/api-gateway/middleware"
	"github.com/YeonwooSung/instagram/api-gateway/proxy"
	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
)

// SetupRoutes configures all routes for the API Gateway
func SetupRoutes(
	r *gin.Engine,
	cfg *config.Config,
	logger *zap.Logger,
	rateLimiter *middleware.RateLimiter,
) {
	// Create proxy handler
	proxyHandler := proxy.NewProxyHandler(cfg.ProxyTimeout, logger)

	// API version group
	api := r.Group("/api/v1")

	// Apply rate limiting to all API routes
	api.Use(rateLimiter.RateLimit())

	// ==================== Auth Service Routes ====================
	// All auth routes - service handles authentication internally
	auth := api.Group("/auth")
	{
		// Public routes
		auth.POST("/register", proxyHandler.ProxyRequest(cfg.AuthServiceURL))
		auth.POST("/login", proxyHandler.ProxyRequest(cfg.AuthServiceURL))
		auth.POST("/refresh", proxyHandler.ProxyRequest(cfg.AuthServiceURL))

		// Protected routes (service validates JWT)
		auth.GET("/profile", proxyHandler.ProxyRequest(cfg.AuthServiceURL))
		auth.GET("/me", proxyHandler.ProxyRequest(cfg.AuthServiceURL))
		auth.PUT("/profile", proxyHandler.ProxyRequest(cfg.AuthServiceURL))
		auth.POST("/logout", proxyHandler.ProxyRequest(cfg.AuthServiceURL))
		auth.PUT("/password", proxyHandler.ProxyRequest(cfg.AuthServiceURL))
	}

	// ==================== Media Service Routes ====================
	// All media routes - service handles authentication internally
	media := api.Group("/media")
	{
		// Upload media
		media.POST("/upload", proxyHandler.ProxyRequest(cfg.MediaServiceURL))

		// Get media
		media.GET("/:id", proxyHandler.ProxyRequest(cfg.MediaServiceURL))

		// Delete media
		media.DELETE("/:id", proxyHandler.ProxyRequest(cfg.MediaServiceURL))

		// Get user's media
		media.GET("/user/:user_id", proxyHandler.ProxyRequest(cfg.MediaServiceURL))
	}

	// ==================== Post Service Routes ====================
	// All post routes - service handles authentication internally
	posts := api.Group("/posts")
	{
		// Read operations
		posts.GET("/:id", proxyHandler.ProxyRequest(cfg.PostServiceURL))
		posts.GET("", proxyHandler.ProxyRequest(cfg.PostServiceURL))
		posts.GET("/user/:user_id", proxyHandler.ProxyRequest(cfg.PostServiceURL))
		posts.GET("/hashtag/:hashtag", proxyHandler.ProxyRequest(cfg.PostServiceURL))

		// Write operations (service validates JWT)
		posts.POST("", proxyHandler.ProxyRequest(cfg.PostServiceURL))
		posts.PUT("/:id", proxyHandler.ProxyRequest(cfg.PostServiceURL))
		posts.DELETE("/:id", proxyHandler.ProxyRequest(cfg.PostServiceURL))

		// Like/unlike
		posts.POST("/:id/like", proxyHandler.ProxyRequest(cfg.PostServiceURL))
		posts.DELETE("/:id/like", proxyHandler.ProxyRequest(cfg.PostServiceURL))

		// Comments
		posts.POST("/:id/comments", proxyHandler.ProxyRequest(cfg.PostServiceURL))
		posts.GET("/:id/comments", proxyHandler.ProxyRequest(cfg.PostServiceURL))
		posts.DELETE("/:id/comments/:comment_id", proxyHandler.ProxyRequest(cfg.PostServiceURL))
	}

	// ==================== Graph Service Routes ====================
	// All graph routes - service handles authentication internally
	graph := api.Group("/graph")
	{
		// Follow/unfollow
		graph.POST("/follow/:user_id", proxyHandler.ProxyRequest(cfg.GraphServiceURL))
		graph.DELETE("/follow/:user_id", proxyHandler.ProxyRequest(cfg.GraphServiceURL))

		// Follow requests (for private accounts)
		graph.GET("/follow-requests", proxyHandler.ProxyRequest(cfg.GraphServiceURL))
		graph.POST("/follow-requests/:request_id/accept", proxyHandler.ProxyRequest(cfg.GraphServiceURL))
		graph.POST("/follow-requests/:request_id/reject", proxyHandler.ProxyRequest(cfg.GraphServiceURL))

		// Get followers/following
		graph.GET("/followers/:user_id", proxyHandler.ProxyRequest(cfg.GraphServiceURL))
		graph.GET("/following/:user_id", proxyHandler.ProxyRequest(cfg.GraphServiceURL))

		// Check relationship
		graph.GET("/relationship/:user_id", proxyHandler.ProxyRequest(cfg.GraphServiceURL))

		// Get stats
		graph.GET("/stats/:user_id", proxyHandler.ProxyRequest(cfg.GraphServiceURL))

		// Recommendations
		graph.GET("/recommendations", proxyHandler.ProxyRequest(cfg.GraphServiceURL))
	}

	// ==================== Newsfeed Service Routes ====================
	// All feed routes - service handles authentication internally
	feed := api.Group("/feed")
	{
		// Get personalized feed
		feed.GET("", proxyHandler.ProxyRequest(cfg.NewsfeedServiceURL))

		// Refresh feed
		feed.POST("/refresh", proxyHandler.ProxyRequest(cfg.NewsfeedServiceURL))

		// Get feed stats
		feed.GET("/stats", proxyHandler.ProxyRequest(cfg.NewsfeedServiceURL))
	}

	// ==================== Admin Routes ====================
	// Admin routes - authentication handled here for gateway management
	admin := api.Group("/admin")
	{
		// Gateway stats (public for monitoring)
		admin.GET("/stats", func(c *gin.Context) {
			c.JSON(http.StatusOK, gin.H{
				"message": "Gateway statistics endpoint",
				"status":  "healthy",
			})
		})

		// Service health checks (public for monitoring)
		admin.GET("/health/services", func(c *gin.Context) {
			c.JSON(http.StatusOK, gin.H{
				"services": gin.H{
					"auth":     cfg.AuthServiceURL,
					"media":    cfg.MediaServiceURL,
					"post":     cfg.PostServiceURL,
					"graph":    cfg.GraphServiceURL,
					"newsfeed": cfg.NewsfeedServiceURL,
				},
			})
		})
	}

	// ==================== Catch-all Routes ====================
	r.NoRoute(func(c *gin.Context) {
		c.JSON(http.StatusNotFound, gin.H{
			"error": "Route not found",
		})
	})
}
