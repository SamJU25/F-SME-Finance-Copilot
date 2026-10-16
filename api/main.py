"""
FastAPI Main Application Entrypoint.
Configures CORS, Security Headers, and Router Mounts.
Aligns with docs/system.md Section 4 and docs/security.md Section 4.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes.health import router as health_router
from api.routes.analyze import router as analyze_router
from api.routes.actions import router as actions_router
from api.routes.underwrite import router as underwrite_router
from api.routes.agent import router as agent_router
from api.routes.decision import router as decision_router

app = FastAPI(
    title="SME Finance Copilot API",
    description="Autonomous AI CFO & Financial Participant for Small & Medium Enterprises",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

import os

# CORS configuration configurable via environment variable with local defaults
allowed_origins_env = os.getenv("ALLOWED_ORIGINS")
origins = (
    [origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()]
    if allowed_origins_env
    else ["http://localhost:3000", "http://127.0.0.1:3000"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(health_router)
app.include_router(analyze_router)
app.include_router(actions_router)
app.include_router(underwrite_router)
app.include_router(agent_router)
app.include_router(decision_router)


@app.get("/")
async def root():
    return {
        "project": "SME Finance Copilot",
        "description": "Autonomous AI CFO & Financial Participant for Small & Medium Enterprises",
        "docs": "/docs",
        "health": "/api/v1/health"
    }
