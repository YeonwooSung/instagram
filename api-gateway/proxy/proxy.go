package proxy

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
)

// ProxyHandler handles reverse proxy requests to backend services
type ProxyHandler struct {
	client  *http.Client
	logger  *zap.Logger
	timeout time.Duration
}

// NewProxyHandler creates a new proxy handler
func NewProxyHandler(timeout time.Duration, logger *zap.Logger) *ProxyHandler {
	return &ProxyHandler{
		client: &http.Client{
			Timeout: timeout,
			CheckRedirect: func(req *http.Request, via []*http.Request) error {
				return http.ErrUseLastResponse
			},
		},
		logger:  logger,
		timeout: timeout,
	}
}

// ProxyRequest forwards the request to the target service
func (p *ProxyHandler) ProxyRequest(targetURL string) gin.HandlerFunc {
	return func(c *gin.Context) {
		// Build target URL
		target := targetURL + c.Request.URL.Path
		if c.Request.URL.RawQuery != "" {
			target += "?" + c.Request.URL.RawQuery
		}

		// Read request body
		var bodyBytes []byte
		if c.Request.Body != nil {
			bodyBytes, _ = io.ReadAll(c.Request.Body)
			c.Request.Body.Close()
		}

		// Create new request
		proxyReq, err := http.NewRequestWithContext(
			c.Request.Context(),
			c.Request.Method,
			target,
			bytes.NewReader(bodyBytes),
		)
		if err != nil {
			p.logger.Error("Failed to create proxy request",
				zap.Error(err),
				zap.String("target", target),
			)
			c.JSON(http.StatusInternalServerError, gin.H{
				"error": "Failed to create request",
			})
			return
		}

		// Copy headers
		p.copyHeaders(c.Request.Header, proxyReq.Header)

		// Add/override headers
		proxyReq.Header.Set("X-Forwarded-For", c.ClientIP())
		proxyReq.Header.Set("X-Forwarded-Proto", "http")
		proxyReq.Header.Set("X-Real-IP", c.ClientIP())

		// Add user context if available
		if userID, exists := c.Get("user_id"); exists {
			proxyReq.Header.Set("X-User-ID", fmt.Sprintf("%v", userID))
		}
		if username, exists := c.Get("username"); exists {
			proxyReq.Header.Set("X-Username", fmt.Sprintf("%v", username))
		}

		// Send request
		start := time.Now()
		resp, err := p.client.Do(proxyReq)
		latency := time.Since(start)

		if err != nil {
			p.logger.Error("Proxy request failed",
				zap.Error(err),
				zap.String("target", target),
				zap.Duration("latency", latency),
			)
			c.JSON(http.StatusBadGateway, gin.H{
				"error": "Service unavailable",
			})
			return
		}
		defer resp.Body.Close()

		// Read response body
		respBody, err := io.ReadAll(resp.Body)
		if err != nil {
			p.logger.Error("Failed to read response body",
				zap.Error(err),
				zap.String("target", target),
			)
			c.JSON(http.StatusInternalServerError, gin.H{
				"error": "Failed to read response",
			})
			return
		}

		// Log response
		p.logger.Debug("Proxy response",
			zap.String("target", target),
			zap.Int("status", resp.StatusCode),
			zap.Duration("latency", latency),
			zap.Int("response_size", len(respBody)),
		)

		// Copy response headers
		for key, values := range resp.Header {
			for _, value := range values {
				c.Writer.Header().Add(key, value)
			}
		}

		// Send response
		c.Data(resp.StatusCode, resp.Header.Get("Content-Type"), respBody)
	}
}

// copyHeaders copies HTTP headers from source to destination
func (p *ProxyHandler) copyHeaders(src, dst http.Header) {
	for key, values := range src {
		// Skip hop-by-hop headers
		if p.isHopByHopHeader(key) {
			continue
		}
		for _, value := range values {
			dst.Add(key, value)
		}
	}
}

// isHopByHopHeader checks if a header is hop-by-hop
func (p *ProxyHandler) isHopByHopHeader(header string) bool {
	hopByHopHeaders := []string{
		"Connection",
		"Keep-Alive",
		"Proxy-Authenticate",
		"Proxy-Authorization",
		"Te",
		"Trailers",
		"Transfer-Encoding",
		"Upgrade",
	}

	headerLower := strings.ToLower(header)
	for _, h := range hopByHopHeaders {
		if strings.ToLower(h) == headerLower {
			return true
		}
	}
	return false
}
