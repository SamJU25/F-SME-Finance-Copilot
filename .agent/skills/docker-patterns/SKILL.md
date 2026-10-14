---
name: docker-patterns
description: "Containerization patterns for SME Finance Copilot. Use when authoring multi-stage Dockerfiles, docker-compose setups, container healthchecks, and production runtime environments without hardcoded hostnames or credentials."
---

# Docker Patterns for SME Finance Copilot

Operational guidelines for containerizing the FastAPI backend and Next.js frontend with minimal image footprints, non-root execution, and dynamic environment injection.

## 1. Multi-Stage Architecture

Every service uses multi-stage builds to separate build toolchains from runtime images:

```
[Build Stage: Dev dependencies, compiler tools]
                     │
                     ▼ (Copy only compiled artifacts & production modules)
[Runtime Stage: Minimal distroless/slim base, non-root user, minimal attack surface]
```

## 2. Invariants & Rules

1. **Zero Hardcoded References**:
   - Never hardcode hostnames, IP addresses, credentials, or ports in images or compose files.
   - Bind backend hosts to `0.0.0.0` inside containers and use `${PORT:-8000}`.
   - Frontend consumes `${NEXT_PUBLIC_API_BASE_URL:-http://localhost:8000}` dynamically at build/runtime.
2. **Non-Root Execution**:
   - Always create and switch to a dedicated system user (`appuser` with UID 10001) before launching services.
3. **Container Healthchecks**:
   - Backend must expose an active `/health` probe that returns HTTP 200 without side effects.
   - Docker Compose services must define `healthcheck` and `depends_on: { condition: service_healthy }`.
4. **Context Hygiene (.dockerignore)**:
   - Exclude `.git`, `node_modules`, `.next`, `__pycache__`, `.pytest_cache`, and local `.env` files.
5. **Bridge Networking**:
   - Place services on a private internal bridge network (`copilot-net`) and publish only designated ingress ports to the host.
