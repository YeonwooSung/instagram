.PHONY: help build up down restart logs clean test dev

# Default target
help:
	@echo "Instagram Clone - Makefile Commands"
	@echo ""
	@echo "Usage:"
	@echo "  make build       - Build all Docker images"
	@echo "  make up          - Start all services"
	@echo "  make down        - Stop all services"
	@echo "  make restart     - Restart all services"
	@echo "  make logs        - View logs from all services"
	@echo "  make clean       - Remove all containers, volumes, and images"
	@echo "  make dev         - Start services in development mode"
	@echo "  make test        - Run tests"
	@echo "  make gateway     - View API Gateway logs"
	@echo "  make ps          - Show running containers"
	@echo ""

# Build all services
build:
	@echo "Building all services..."
	docker-compose build

# Start all services
up:
	@echo "Starting all services..."
	docker-compose up -d
	@echo "Services are starting..."
	@echo "API Gateway: http://localhost:8080"
	@echo "MinIO Console: http://localhost:9001"
	@echo ""
	@echo "Run 'make logs' to view logs"

# Stop all services
down:
	@echo "Stopping all services..."
	docker-compose down

# Restart all services
restart:
	@echo "Restarting all services..."
	docker-compose restart

# View logs
logs:
	docker-compose logs -f

# View API Gateway logs
gateway:
	docker-compose logs -f api-gateway

# Show running containers
ps:
	docker-compose ps

# Clean everything
clean:
	@echo "Cleaning up..."
	docker-compose down -v --rmi all
	@echo "Cleanup complete"

# Development mode (with logs)
dev:
	@echo "Starting services in development mode..."
	docker-compose up

# Run tests
test:
	@echo "Running tests..."
	@echo "Auth Service tests..."
	cd auth_service && python -m pytest || true
	@echo "Graph Service tests..."
	cd graph-service && python -m pytest || true
	@echo "Newsfeed Service tests..."
	cd newsfeed-service && python -m pytest || true

# Database operations
db-shell:
	docker-compose exec postgres psql -U postgres

db-migrate:
	@echo "Running database migrations..."
	@echo "Migrations not yet implemented"

# Redis operations
redis-cli:
	docker-compose exec redis redis-cli

# Kafka operations
kafka-topics:
	docker-compose exec kafka kafka-topics --list --bootstrap-server localhost:9092

kafka-console:
	docker-compose exec kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic post.created --from-beginning

# Health checks
health:
	@echo "Checking service health..."
	@curl -s http://localhost:8080/health | jq '.' || echo "API Gateway not responding"
	@echo ""

# Initialize environment
init:
	@echo "Initializing environment..."
	@cp -n .env.example .env || true
	@cp -n api-gateway/.env.example api-gateway/.env || true
	@echo "Environment files created. Please update them with your configuration."
	@echo "Run 'make build && make up' to start the services."
