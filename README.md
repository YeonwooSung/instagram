# Instagram Clone

Full stack Instagram clone, and deploy with Kubernetes.

## Components

### 1. Discovery Service

[Discovery Service](./discovery-service/)

In microservices architecture services need a way to find each other.
You can’t rely on service IP and port, because those are dynamic.
Whenever an IP or a port of a service changes you’ll need to modify the code in all other services.

To avoid this we need a place where services can register itself and assign it a name, this place is “service discovery”.
You can think of service discovery as DNS, it maps service IP and port to a name.

### 2. Auth Service

[Auth Service](./auth-service/)
