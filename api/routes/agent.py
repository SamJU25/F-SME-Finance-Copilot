"""FastAPI router for the Autonomous AI Copilot Agent.

Exposes conversational financial participant endpoints with deterministic tool dispatching
and multi-provider LLM bridge support.
"""

from __future__ import annotations

import json
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, status

from services.agent.llm_bridge import fetch_remote_models, test_llm_connection
from services.agent.schema import (
    AgentChatRequest,
    CopilotResponse,
    FetchModelsRequest,
    FetchModelsResponse,
    LLMConfig,
    TestConnectionRequest,
    TestConnectionResponse,
)
from services.agent.supervisor import run_copilot_supervisor

router = APIRouter(prefix="/api/v1/agent", tags=["Autonomous Agent"])


@router.post(
    "/test-connection",
    response_model=TestConnectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Test LLM Provider Connection",
    description="Validates API key, Base URL, and model responsiveness for configured LLM provider before saving.",
)
async def agent_test_connection(
    request: TestConnectionRequest,
) -> TestConnectionResponse:
    """Sends a lightweight verification probe to the target LLM provider."""
    return test_llm_connection(request)


@router.post(
    "/fetch-models",
    response_model=FetchModelsResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch Available Models from Provider",
    description="Queries the target provider's live endpoint to discover supported models in real time.",
)
async def agent_fetch_models(
    request: FetchModelsRequest,
) -> FetchModelsResponse:
    """Dynamically queries the target provider's models catalog."""
    return fetch_remote_models(request)



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
    x_llm_config: Optional[str] = Header(default=None, alias="X-LLM-Config"),
) -> CopilotResponse:
    """Dispatches user prompt to the Agent Supervisor with authoritative header-based tenant isolation."""
    try:
        effective_tenant = x_tenant_id or request.tenant_id or "SME-DEFAULT"
        effective_llm_config = request.llm_config

        if x_llm_config:
            try:
                parsed = json.loads(x_llm_config)
                effective_llm_config = LLMConfig(**parsed)
            except Exception:
                pass

        response = run_copilot_supervisor(
            request,
            tenant_id=effective_tenant,
            llm_config=effective_llm_config,
        )
        return response
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent reasoning error: {str(exc)}",
        )
