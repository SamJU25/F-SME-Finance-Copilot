"""Universal LLM Bridge for the Autonomous SME Finance Copilot.

Supports:
1. Native Gemini API (Google AI)
2. Native Anthropic Messages API
3. Native OpenAI Chat Completions API
4. DeepSeek, Groq, and Ollama (OpenAI-compatible)
5. Custom OpenAI-compatible endpoints (Base URL + Key + Model)
6. Offline Local Deterministic fallback (0 external keys)
7. Pre-flight PII redaction and deterministic calculation grounding
"""

from __future__ import annotations

import re
import time
from typing import Optional, Tuple
import httpx

from services.agent.schema import (
    FetchModelsRequest,
    FetchModelsResponse,
    LLMConfig,
    ModelItem,
    TestConnectionRequest,
    TestConnectionResponse,
)

# Pre-compiled PII Sanitization Patterns
RE_ACCOUNT = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{9,18}\b")
RE_TAX_ID = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")


def mask_pii(text: str) -> str:
    """Sanitizes sensitive identifiers before external transmission."""
    if not text:
        return text
    scrubbed = RE_ACCOUNT.sub("[REDACTED_ACCOUNT]", text)
    scrubbed = RE_TAX_ID.sub("[REDACTED_TAX_ID]", scrubbed)
    scrubbed = RE_EMAIL.sub("[REDACTED_EMAIL]", scrubbed)
    return scrubbed


PROVIDER_DEFAULTS = {
    "offline": {
        "model": "deterministic-v1",
        "url": "local",
    },
    "gemini": {
        "model": "gemini-2.0-flash",
        "url": "https://generativelanguage.googleapis.com/v1beta",
    },
    "anthropic": {
        "model": "claude-3-5-sonnet-20241022",
        "url": "https://api.anthropic.com/v1/messages",
    },
    "openai": {
        "model": "gpt-4o-mini",
        "url": "https://api.openai.com/v1/chat/completions",
    },
    "deepseek": {
        "model": "deepseek-chat",
        "url": "https://api.deepseek.com/v1/chat/completions",
    },
    "groq": {
        "model": "llama-3.3-70b-versatile",
        "url": "https://api.groq.com/openai/v1/chat/completions",
    },
    "ollama": {
        "model": "qwen2.5:14b",
        "url": "http://localhost:11434/v1/chat/completions",
    },
}


def _resolve_endpoint(provider: str, base_url: Optional[str], model: Optional[str]) -> Tuple[str, str]:
    """Resolves target endpoint URL and model identifier for a given provider."""
    p_lower = (provider or "offline").lower()
    defaults = PROVIDER_DEFAULTS.get(p_lower, {})
    model_name = model or defaults.get("model", "custom-model")

    if p_lower == "custom":
        raw_url = (base_url or "").rstrip("/")
        if not raw_url.endswith("/chat/completions"):
            raw_url = f"{raw_url}/chat/completions"
        return raw_url, model_name

    if p_lower == "gemini":
        base = (base_url or defaults.get("url", "")).rstrip("/")
        return f"{base}/models/{model_name}:generateContent", model_name

    if p_lower in ["openai", "deepseek", "groq", "ollama"]:
        if base_url:
            raw_url = base_url.rstrip("/")
            if not raw_url.endswith("/chat/completions"):
                raw_url = f"{raw_url}/chat/completions"
            return raw_url, model_name
        return defaults.get("url", ""), model_name

    if p_lower == "anthropic":
        return base_url or defaults.get("url", ""), model_name

    return "local", "deterministic-v1"


def test_llm_connection(req: TestConnectionRequest) -> TestConnectionResponse:
    """Sends a lightweight verification probe to the target LLM provider."""
    provider = (req.provider or "offline").lower()

    if provider == "offline":
        return TestConnectionResponse(
            success=True,
            message="Offline deterministic financial engine ready (0 external keys needed).",
            provider="offline",
            model_name="deterministic-v1",
            latency_ms=0,
        )

    # Validate mandatory fields
    if provider in ["gemini", "anthropic", "openai", "deepseek", "groq"] and not req.api_key:
        return TestConnectionResponse(
            success=False,
            message=f"API key is required for provider '{provider}'.",
            provider=provider,
            latency_ms=None,
        )

    if provider == "custom" and not req.base_url:
        return TestConnectionResponse(
            success=False,
            message="Base URL is required for custom OpenAI-compatible endpoint.",
            provider=provider,
            latency_ms=None,
        )

    endpoint, model = _resolve_endpoint(provider, req.base_url, req.model_name)
    probe_prompt = "Hello. Respond with the single word 'READY'."
    start_time = time.perf_counter()

    try:
        with httpx.Client(timeout=6.0) as client:
            if provider == "gemini":
                url = f"{endpoint}?key={req.api_key}"
                payload = {
                    "contents": [{"parts": [{"text": probe_prompt}]}],
                    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 10},
                }
                res = client.post(url, json=payload)

            elif provider == "anthropic":
                headers = {
                    "x-api-key": req.api_key or "",
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }
                payload = {
                    "model": model,
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": probe_prompt}],
                }
                res = client.post(endpoint, headers=headers, json=payload)

            else:  # OpenAI, DeepSeek, Groq, Ollama, Custom
                headers = {"content-type": "application/json"}
                if req.api_key:
                    headers["Authorization"] = f"Bearer {req.api_key}"
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": probe_prompt}],
                    "max_tokens": 10,
                    "temperature": 0.1,
                }
                res = client.post(endpoint, headers=headers, json=payload)

            latency_ms = int((time.perf_counter() - start_time) * 1000)

            if res.status_code == 200:
                return TestConnectionResponse(
                    success=True,
                    message=f"Connection verified successfully with {provider} ({model}).",
                    provider=provider,
                    model_name=model,
                    latency_ms=latency_ms,
                )
            elif res.status_code == 401:
                return TestConnectionResponse(
                    success=False,
                    message=f"Authentication failed (HTTP 401): Check your API key for {provider}.",
                    provider=provider,
                    model_name=model,
                    latency_ms=latency_ms,
                )
            elif res.status_code == 404:
                return TestConnectionResponse(
                    success=False,
                    message=f"Endpoint or model not found (HTTP 404): Check model name '{model}' or Base URL.",
                    provider=provider,
                    model_name=model,
                    latency_ms=latency_ms,
                )
            else:
                return TestConnectionResponse(
                    success=False,
                    message=f"Provider returned error HTTP {res.status_code}: {res.text[:150]}",
                    provider=provider,
                    model_name=model,
                    latency_ms=latency_ms,
                )

    except httpx.ConnectError:
        return TestConnectionResponse(
            success=False,
            message=f"Unable to connect to host at '{endpoint}'. Verify your network or local server status.",
            provider=provider,
            model_name=model,
        )
    except httpx.TimeoutException:
        return TestConnectionResponse(
            success=False,
            message="Connection timed out after 6 seconds.",
            provider=provider,
            model_name=model,
        )
    except Exception as exc:
        return TestConnectionResponse(
            success=False,
            message=f"Connection probe failed: {str(exc)}",
            provider=provider,
            model_name=model,
        )


def query_external_llm(
    prompt: str,
    system_instruction: str,
    config: Optional[LLMConfig],
) -> Optional[str]:
    """Queries configured external LLM with PII redaction and graceful fallback."""
    if not config or (config.provider or "offline").lower() == "offline":
        return None

    provider = config.provider.lower()
    endpoint, model = _resolve_endpoint(provider, config.base_url, config.model_name)
    sanitized_prompt = mask_pii(prompt)

    try:
        with httpx.Client(timeout=10.0) as client:
            if provider == "gemini":
                if not config.api_key:
                    return None
                url = f"{endpoint}?key={config.api_key}"
                payload = {
                    "contents": [{"parts": [{"text": f"System Directive: {system_instruction}\n\nUser Context:\n{sanitized_prompt}"}]}],
                    "generationConfig": {"temperature": 0.2, "maxOutputTokens": 800},
                }
                res = client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip()

            elif provider == "anthropic":
                if not config.api_key:
                    return None
                headers = {
                    "x-api-key": config.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }
                payload = {
                    "model": model,
                    "max_tokens": 800,
                    "system": system_instruction,
                    "messages": [{"role": "user", "content": sanitized_prompt}],
                    "temperature": 0.2,
                }
                res = client.post(endpoint, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    return data["content"][0]["text"].strip()

            else:  # OpenAI, DeepSeek, Groq, Ollama, Custom
                headers = {"content-type": "application/json"}
                if config.api_key:
                    headers["Authorization"] = f"Bearer {config.api_key}"
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": sanitized_prompt},
                    ],
                    "max_tokens": 800,
                    "temperature": 0.2,
                }
                res = client.post(endpoint, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    return data["choices"][0]["message"]["content"].strip()

    except Exception:
        # Fallback cleanly to deterministic template response
        return None

    return None


FALLBACK_CATALOG: dict[str, list[ModelItem]] = {
    "offline": [
        ModelItem(id="deterministic-v1", name="Deterministic Financial Engine (Offline)"),
    ],
    "gemini": [
        ModelItem(id="gemini-2.0-flash", name="Gemini 2.0 Flash (Recommended)"),
        ModelItem(id="gemini-1.5-pro", name="Gemini 1.5 Pro"),
        ModelItem(id="gemini-1.5-flash", name="Gemini 1.5 Flash"),
    ],
    "anthropic": [
        ModelItem(id="claude-3-5-sonnet-20241022", name="Claude 3.5 Sonnet (Recommended)"),
        ModelItem(id="claude-3-5-haiku-20241022", name="Claude 3.5 Haiku"),
        ModelItem(id="claude-3-opus-20240229", name="Claude 3 Opus"),
    ],
    "openai": [
        ModelItem(id="gpt-4o-mini", name="GPT-4o Mini (Recommended)"),
        ModelItem(id="gpt-4o", name="GPT-4o"),
        ModelItem(id="o3-mini", name="o3-mini (Reasoning)"),
    ],
    "deepseek": [
        ModelItem(id="deepseek-chat", name="DeepSeek-V3 (deepseek-chat)"),
        ModelItem(id="deepseek-reasoner", name="DeepSeek-R1 (deepseek-reasoner)"),
    ],
    "groq": [
        ModelItem(id="llama-3.3-70b-versatile", name="Llama 3.3 70B Versatile"),
        ModelItem(id="mixtral-8x7b-32768", name="Mixtral 8x7B"),
        ModelItem(id="llama-3.1-8b-instant", name="Llama 3.1 8B Instant"),
    ],
    "ollama": [
        ModelItem(id="qwen2.5:14b", name="Qwen 2.5 14B"),
        ModelItem(id="llama3.3:latest", name="Llama 3.3"),
        ModelItem(id="mistral:latest", name="Mistral"),
    ],
    "custom": [
        ModelItem(id="custom-model", name="Custom Model"),
    ],
}


def fetch_remote_models(req: FetchModelsRequest) -> FetchModelsResponse:
    """Dynamically queries the target provider's live models endpoint to discover models."""
    provider = (req.provider or "offline").lower()
    fallbacks = FALLBACK_CATALOG.get(provider, [ModelItem(id="custom-model", name="Custom Model")])

    if provider == "offline":
        return FetchModelsResponse(
            success=True,
            provider="offline",
            models=[ModelItem(id="deterministic-v1", name="Deterministic Financial Engine (Offline)")],
            message="Offline deterministic engine requires no remote models.",
        )

    # If missing required credentials, return empty models list (never pretend with hardcoded list)
    if provider in ["gemini", "anthropic", "openai", "deepseek", "groq"] and not req.api_key:
        return FetchModelsResponse(
            success=False,
            provider=provider,
            models=[],
            message=f"API key required. Enter your API key to discover live models from {provider}.",
        )

    if provider == "custom" and not req.base_url:
        return FetchModelsResponse(
            success=False,
            provider=provider,
            models=[],
            message="Base URL required to fetch custom models.",
        )

    try:
        with httpx.Client(timeout=6.0) as client:
            if provider == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models?key={req.api_key}"
                res = client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    models_list = []
                    for m in data.get("models", []):
                        methods = m.get("supportedGenerationMethods", [])
                        if "generateContent" in methods:
                            mid = m.get("name", "").replace("models/", "")
                            disp = m.get("displayName", mid)
                            models_list.append(ModelItem(id=mid, name=f"{disp} ({mid})"))
                    if models_list:
                        return FetchModelsResponse(
                            success=True,
                            provider=provider,
                            models=models_list,
                            message=f"Discovered {len(models_list)} live Gemini models.",
                        )

            elif provider == "anthropic":
                url = "https://api.anthropic.com/v1/models"
                headers = {
                    "x-api-key": req.api_key or "",
                    "anthropic-version": "2023-06-01",
                }
                res = client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    models_list = [
                        ModelItem(id=m["id"], name=m.get("display_name", m["id"]))
                        for m in data.get("data", [])
                        if "id" in m
                    ]
                    if models_list:
                        return FetchModelsResponse(
                            success=True,
                            provider=provider,
                            models=models_list,
                            message=f"Discovered {len(models_list)} live Anthropic models.",
                        )

            else:  # OpenAI, DeepSeek, Groq, Ollama, Custom
                base = req.base_url
                if not base:
                    if provider == "openai":
                        base = "https://api.openai.com/v1"
                    elif provider == "deepseek":
                        base = "https://api.deepseek.com/v1"
                    elif provider == "groq":
                        base = "https://api.groq.com/openai/v1"
                    elif provider == "ollama":
                        base = "http://localhost:11434/v1"
                    else:
                        base = "https://api.openai.com/v1"

                clean_base = base.rstrip("/")
                if clean_base.endswith("/chat/completions"):
                    clean_base = clean_base[:-17]
                url = f"{clean_base}/models"
                headers = {}
                if req.api_key:
                    headers["Authorization"] = f"Bearer {req.api_key}"
                res = client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    raw_items = data.get("data", [])
                    models_list = [
                        ModelItem(id=m["id"], name=m.get("name", m["id"]))
                        for m in raw_items
                        if isinstance(m, dict) and "id" in m
                    ]
                    if models_list:
                        return FetchModelsResponse(
                            success=True,
                            provider=provider,
                            models=models_list[:50],
                            message=f"Discovered {len(models_list)} live models from {provider}.",
                        )

    except Exception as exc:
        return FetchModelsResponse(
            success=False,
            provider=provider,
            models=[],
            message=f"Live model discovery failed ({str(exc)[:80]}). Verify connection and credentials.",
        )

    return FetchModelsResponse(
        success=False,
        provider=provider,
        models=[],
        message=f"Unable to query /models endpoint for {provider}. Verify connection and credentials.",
    )

