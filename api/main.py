"""
FastAPI Main Application Entrypoint.
Configures CORS, Security Headers, and Router Mounts.
Aligns with docs/system.md Section 4 and docs/security.md Section 4.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes.health import router as health_router
from api.routes.analyze import router as analyze_router

app = FastAPI(
    title="SME Finance Copilot API",
    description="Autonomous AI CFO & Financial Participant for Small & Medium Enterprises",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS configuration locked to frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(health_router)
app.include_router(analyze_router)


@app.get("/")
async def root():
    return {
        "project": "SME Finance Copilot",
        "competition": "FinTechathon 2026 Topic E (Tsinghua PBCSF & WeBank)",
        "docs": "/docs",
        "health": "/api/v1/health"
    }
