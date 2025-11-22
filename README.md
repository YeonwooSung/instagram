# Instagram Clone

Full stack Instagram clone with microservices architecture.

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose
- Make (optional, for convenience commands)

### Setup

1. **Clone the repository**
```bash
git clone <repository-url>
cd instagram
```

2. **Initialize environment**
```bash
make init
# or manually:
cp .env.example .env
cp api-gateway/.env.example api-gateway/.env
```

3. **Update environment variables**
Edit `.env` file with your configuration:
```bash
JWT_SECRET=your-secret-key-change-this
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
```

4. **Build and start services**
```bash
make build
make up
```

5. **Access the services**
- **API Gateway**: http://localhost:8080
- **MinIO Console**: http://localhost:9001

### Usage Commands

```bash
# Start all services
make up

# Stop all services
make down

# View logs
make logs

# View API Gateway logs only
make gateway

# Show running containers
make ps

# Clean everything (containers, volumes, images)
make clean

# Health check
make health
```

## 🏗️ Architecture

### System Overview

```
Client → API Gateway (8080)
            ↓
   ┌────────┼────────┐
   ▼        ▼        ▼
  Auth    Media    Post
 (8001)  (8000)  (8002)
   ↓        ▼        ↓
  Graph  Newsfeed
 (8003)   (8004)
```

### Infrastructure

- **Main DB**: PostgreSQL (with pg_dog for sharding)
- **Object Storage**: MinIO (S3-compatible)
- **Cache**: Redis
- **Message Queue**: Kafka
- **Service Discovery**: Zookeeper
- **API Gateway**: Go + Gin

## 📦 Components

### 0. API Gateway (Port: 8080)

[API Gateway](./api-gateway/)

Single entry point for all client requests. Built with Go and Gin framework.

**Features**:
- Reverse proxy to microservices
- JWT authentication
- Rate limiting (100 RPS, 200 burst)
- CORS support
- Structured logging
- Health checks

### 1. Discovery Service

[Discovery Service](./discovery-service/)

In microservices architecture services need a way to find each other.
You can't rely on service IP and port, because those are dynamic.
Whenever an IP or a port of a service changes you'll need to modify the code in all other services.

To avoid this we need a place where services can register itself and assign it a name, this place is "service discovery".
You can think of service discovery as DNS, it maps service IP and port to a name.

### 2. Auth Service (Port: 8001)

[Auth Service](./auth-service/)
