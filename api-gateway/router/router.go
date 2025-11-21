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
	// Public routes (no authentication required)
	authPublic := api.Group("/auth")
	{
		authPublic.POST("/register", proxyHandler.ProxyRequest(cfg.AuthServiceURL))
		authPublic.POST("/login", proxyHandler.ProxyRequest(cfg.AuthServiceURL))
		authPublic.POST("/refresh", proxyHandler.ProxyRequest(cfg.AuthServiceURL))
	}

	// Protected auth routes (requires authentication)
	authProtected := api.Group("/auth")
	authProtected.Use(middleware.JWTAuth(cfg.JWTSecret))
	{
		authProtected.GET("/profile", proxyHandler.ProxyRequest(cfg.AuthServiceURL))
		authProtected.PUT("/profile", proxyHandler.ProxyRequest(cfg.AuthServiceURL))
		authProtected.POST("/logout", proxyHandler.ProxyRequest(cfg.AuthServiceURL))
		authProtected.PUT("/password", proxyHandler.ProxyRequest(cfg.AuthServiceURL))
	}

	// ==================== Media Service Routes ====================
	media := api.Group("/media")
	media.Use(middleware.JWTAuth(cfg.JWTSecret))
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
	posts := api.Group("/posts")
	{
		// Public routes (read-only, optional auth for personalization)
		posts.GET("/:id", middleware.OptionalJWTAuth(cfg.JWTSecret), proxyHandler.ProxyRequest(cfg.PostServiceURL))
		posts.GET("", middleware.OptionalJWTAuth(cfg.JWTSecret), proxyHandler.ProxyRequest(cfg.PostServiceURL))
		posts.GET("/user/:user_id", middleware.OptionalJWTAuth(cfg.JWTSecret), proxyHandler.ProxyRequest(cfg.PostServiceURL))
		posts.GET("/hashtag/:hashtag", middleware.OptionalJWTAuth(cfg.JWTSecret), proxyHandler.ProxyRequest(cfg.PostServiceURL))

		// Protected routes (requires authentication)
		postsProtected := posts.Group("")
		postsProtected.Use(middleware.JWTAuth(cfg.JWTSecret))
		{
			// Create, update, delete posts
			postsProtected.POST("", proxyHandler.ProxyRequest(cfg.PostServiceURL))
			postsProtected.PUT("/:id", proxyHandler.ProxyRequest(cfg.PostServiceURL))
			postsProtected.DELETE("/:id", proxyHandler.ProxyRequest(cfg.PostServiceURL))

			// Like/unlike
			postsProtected.POST("/:id/like", proxyHandler.ProxyRequest(cfg.PostServiceURL))
			postsProtected.DELETE("/:id/like", proxyHandler.ProxyRequest(cfg.PostServiceURL))

			// Comments
			postsProtected.POST("/:id/comments", proxyHandler.ProxyRequest(cfg.PostServiceURL))
			postsProtected.GET("/:id/comments", proxyHandler.ProxyRequest(cfg.PostServiceURL))
			postsProtected.DELETE("/:id/comments/:comment_id", proxyHandler.ProxyRequest(cfg.PostServiceURL))
		}
	}

	// ==================== Graph Service Routes ====================
	graph := api.Group("/graph")
	graph.Use(middleware.JWTAuth(cfg.JWTSecret))
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
	feed := api.Group("/feed")
	feed.Use(middleware.JWTAuth(cfg.JWTSecret))
	{
		// Get personalized feed
		feed.GET("", proxyHandler.ProxyRequest(cfg.NewsfeedServiceURL))

		// Refresh feed
		feed.POST("/refresh", proxyHandler.ProxyRequest(cfg.NewsfeedServiceURL))

		// Get feed stats
		feed.GET("/stats", proxyHandler.ProxyRequest(cfg.NewsfeedServiceURL))
	}

	// ==================== Admin Routes ====================
	admin := api.Group("/admin")
	admin.Use(middleware.JWTAuth(cfg.JWTSecret))
	// TODO: Add admin role check middleware
	{
		// Gateway stats
		admin.GET("/stats", func(c *gin.Context) {
			c.JSON(http.StatusOK, gin.H{
				"message": "Gateway statistics endpoint",
				"status":  "healthy",
			})
		})

		// Service health checks
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
