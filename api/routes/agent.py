"""FastAPI router for the Autonomous AI Copilot Agent.

Exposes conversational financial participant endpoints with deterministic tool dispatching
and multi-provider LLM bridge support.
"""

from __future__ import annotations

import json
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, status
from starlette.concurrency import run_in_threadpool

from services.agent.llm_bridge import fetch_remote_models, test_llm_connection
from services.agent.schema import (
    AgentChatRequest,
    CopilotResponse,
    DeleteModelRequest,
    DeleteModelResponse,
    DownloadModelRequest,
    DownloadModelResponse,
    FetchModelsRequest,
    FetchModelsResponse,
    LLMConfig,
    TestConnectionRequest,
    TestConnectionResponse,
)
from services.agent.supervisor import run_copilot_supervisor

from services.agent.session_store import session_store, SessionRecord

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
    return await run_in_threadpool(test_llm_connection, request)


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
    return await run_in_threadpool(fetch_remote_models, request)


@router.post(
    "/download-model",
    response_model=DownloadModelResponse,
    status_code=status.HTTP_200_OK,
    summary="Download Local Model Weights on Demand",
    description="Explicitly downloads weights for supported local models (sme-finance-lora or qwen-0.5b-mobile) with robust exception handling.",
)
async def agent_download_model(
    request: DownloadModelRequest,
) -> DownloadModelResponse:
    """Explicitly downloads target model weights on demand without silent auto-downloads."""
    from services.agent.local_transformers import LocalTransformersEngine
    engine = LocalTransformersEngine.get_instance()
    res = await run_in_threadpool(engine.download_model, request.model_name)
    return DownloadModelResponse(**res)


@router.post(
    "/delete-model",
    response_model=DeleteModelResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete Downloaded AI Model",
    description="Deletes downloaded model files to free up disk space.",
)
async def agent_delete_model(
    request: DeleteModelRequest,
) -> DeleteModelResponse:
    """Removes downloaded model files to free up disk space."""
    from services.agent.local_transformers import LocalTransformersEngine
    engine = LocalTransformersEngine.get_instance()
    res = await run_in_threadpool(engine.delete_model, request.model_name)
    return DeleteModelResponse(**res)


@router.get(
    "/session/{session_id}",
    response_model=Optional[SessionRecord],
    status_code=status.HTTP_200_OK,
    summary="Retrieve Active Agent Session",
    description="Fetches full session history, cached transactional dossier, and episodic memory facts.",
)
async def get_session(session_id: str) -> Optional[SessionRecord]:
    """Retrieves session record from the persistent store."""
    rec = session_store.get(session_id)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    return rec


@router.delete(
    "/session/{session_id}",
    status_code=status.HTTP_200_OK,
    summary="Clear Active Agent Session",
    description="Wipes session conversation history, statement cache, and episodic facts from memory and disk.",
)
async def clear_session(session_id: str) -> dict:
    """Clears session record from memory and removes serialized disk cache."""
    removed = session_store.clear(session_id)
    return {"session_id": session_id, "cleared": removed}


@router.delete(
    "/session/{session_id}/statement",
    status_code=status.HTTP_200_OK,
    summary="Clear Statement from Active Session",
    description="Purges uploaded CSV statement and cached calculations from the session while preserving conversation history.",
)
async def clear_session_statement(session_id: str) -> dict:
    """Clears statement CSV and cached calculation metrics for the session."""
    rec = session_store.clear_statement(session_id)
    return {"session_id": session_id, "statement_cleared": rec is not None}


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
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-ID"),
) -> CopilotResponse:
    """Dispatches user prompt to the Agent Supervisor with authoritative header-based tenant and session isolation."""
    try:
        effective_tenant = x_tenant_id or request.tenant_id or "SME-DEFAULT"
        effective_session_id = x_session_id or request.session_id
        if not effective_session_id:
            import uuid
            effective_session_id = f"sess_{uuid.uuid4().hex[:12]}"
        effective_llm_config = request.llm_config

        if x_llm_config:
            try:
                parsed = json.loads(x_llm_config)
                effective_llm_config = LLMConfig(**parsed)
            except Exception:
                pass

        response = await run_in_threadpool(
            run_copilot_supervisor,
            request,
            tenant_id=effective_tenant,
            llm_config=effective_llm_config,
            session_id=effective_session_id,
        )
        response.session_id = effective_session_id
        return response
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent reasoning error: {str(exc)}",
        )
