"""FastAPI router for the Autonomous AI Copilot Agent.

Exposes conversational financial participant endpoints with deterministic tool dispatching.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

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
async def agent_chat(request: AgentChatRequest) -> CopilotResponse:
    """Dispatches user prompt to the Agent Supervisor."""
    try:
        response = run_copilot_supervisor(request)
        return response
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent reasoning error: {str(exc)}",
        )
