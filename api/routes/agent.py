"""FastAPI router for the Autonomous AI Copilot Agent.

Exposes conversational financial participant endpoints with deterministic tool dispatching.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Header, HTTPException, status

from services.agent.schema import AgentChatRequest, CopilotResponse
from services.agent.supervisor import run_copilot_supervisor

router = APIRouter(prefix="/api/v1/agent", tags=["Autonomous Agent"])


@router.post(
    "/chat",
    response_model=CopilotResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with Autonomous SME Finance Copilot",
    description="Conversational agent interface that invokes deterministic tools for cash flow diagnostics, digital underwriting, and Tier 2 action staging.",
)
async def agent_chat(
    request: AgentChatRequest,
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> CopilotResponse:
    """Dispatches user prompt to the Agent Supervisor with authoritative header-based tenant isolation."""
    try:
        effective_tenant = x_tenant_id or request.tenant_id or "SME-DEFAULT"
        response = run_copilot_supervisor(request, tenant_id=effective_tenant)
        return response
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent reasoning error: {str(exc)}",
        )
