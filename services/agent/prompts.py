"""Unified Agent Persona and System Directives for the Autonomous SME Finance Copilot.

Defines the behavioral contract, executive CFO tone, and domain guardrails.
Ensures identical persona whether accessed via Next.js UI or external REST API.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional


def evaluate_persona_policy(prompt_type: str = "BASE", sub_intent: str = "", base_reply: str = "") -> dict[str, Any]:
    """Evaluates agent persona and prompt directives via GoRules ZEN JDM decision engine strictly by reference."""
    try:
        from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest
        req = DecisionRequest(
            domain=DecisionDomain.AGENT_PERSONA,
            input_state={
                "prompt_type": prompt_type,
                "sub_intent": sub_intent,
                "base_reply": base_reply,
            },
            execution_mode="DETERMINISTIC_ONLY",
        )
        res = DecisionEngineRegistry.get_instance().evaluate(req)
        return res.output_payload
    except Exception:
        from services.decision.adapters.fallback_adapter import FallbackRuleAdapter
        adapter = FallbackRuleAdapter()
        res = adapter._evaluate_agent_persona({
            "prompt_type": prompt_type,
            "sub_intent": sub_intent,
            "base_reply": base_reply,
        })
        return res.output_payload


def get_base_persona() -> str:
    """Retrieves base institutional CFO persona contract from decision engine."""
    payload = evaluate_persona_policy(prompt_type="BASE")
    return payload.get("prompt_template") or ""


class _DynamicPersonaBase(str):
    """Dynamic string proxy that evaluates COPILOT_PERSONA_BASE by reference via DecisionDomain.AGENT_PERSONA."""
    _cached: Optional[str] = None

    def __str__(self) -> str:
        res = get_base_persona()
        if res:
            self._cached = res
            return res
        return self._cached or ""

    def __repr__(self) -> str:
        return repr(str(self))

    def __contains__(self, item: object) -> bool:
        return str(item) in str(self)

    def __len__(self) -> int:
        return len(str(self))

    def __eq__(self, other: object) -> bool:
        return str(self) == str(other)

    def __hash__(self) -> int:
        return hash(str(self))

    def startswith(self, prefix: Any, *args: Any) -> bool:
        return str(self).startswith(prefix, *args)

    def endswith(self, suffix: Any, *args: Any) -> bool:
        return str(self).endswith(suffix, *args)

    def __add__(self, other: str) -> str:
        return str(self) + other

    def __radd__(self, other: str) -> str:
        return other + str(self)


COPILOT_PERSONA_BASE = _DynamicPersonaBase()


def get_conversational_system_prompt() -> str:
    """Prompt for general greetings, onboarding, and casual conversational dialogue evaluated by reference."""
    payload = evaluate_persona_policy(prompt_type="CONVERSATIONAL")
    return payload.get("prompt_template") or ""


def get_cash_diagnostic_prompt(base_reply: str) -> str:
    """Prompt for contextualizing cash flow, burn rate, runway, and deficit early-warnings evaluated by reference."""
    payload = evaluate_persona_policy(prompt_type="CASH_DIAGNOSTIC", base_reply=base_reply)
    return payload.get("prompt_template") or ""


def get_credit_underwriting_prompt(base_reply: str) -> str:
    """Prompt for explaining credit underwriting tiers and pre-qualified financing options evaluated by reference."""
    payload = evaluate_persona_policy(prompt_type="CREDIT_UNDERWRITING", base_reply=base_reply)
    return payload.get("prompt_template") or ""


def get_missing_statement_prompt(context: str = "diagnostic") -> str:
    """Prompt directive when no statement is loaded evaluated by reference."""
    pt = "MISSING_STATEMENT_UNDERWRITING" if context == "underwriting" else "MISSING_STATEMENT_DIAGNOSTIC"
    payload = evaluate_persona_policy(prompt_type=pt)
    return payload.get("prompt_template") or payload.get("guidance_text") or ""


def get_missing_statement_guidance(context: str = "diagnostic") -> str:
    """Guidance reply when no statement is loaded evaluated by reference."""
    pt = "MISSING_STATEMENT_UNDERWRITING" if context == "underwriting" else "MISSING_STATEMENT_DIAGNOSTIC"
    payload = evaluate_persona_policy(prompt_type=pt)
    return payload.get("guidance_text") or ""


def get_off_topic_reply() -> str:
    """Guidance reply when user asks off-topic queries evaluated by reference."""
    payload = evaluate_persona_policy(prompt_type="OFF_TOPIC")
    return payload.get("guidance_text") or ""


def get_missing_param_guidance(sub_intent: str) -> str:
    """Guidance reply when user inquires about a quantitative calculation without necessary inputs evaluated by reference."""
    payload = evaluate_persona_policy(prompt_type="MISSING_PARAM", sub_intent=sub_intent)
    return payload.get("guidance_text") or ""


def resolve_subagent_routing(sub_intent: str) -> str:
    """Resolves target specialist subagent for a financial sub-intent by reference via JDM decision table."""
    payload = evaluate_persona_policy(prompt_type="SUBAGENT_ROUTING", sub_intent=sub_intent)
    return payload.get("target_subagent") or "Supervisor"


THROAT_CLEARING_PATTERNS = [
    re.compile(r"^(?:hello|hi|hey)[!,.]?\s*(?:as an?\s+[^,.]+[,.]\s*)?", re.IGNORECASE),
    re.compile(r"^(?:certainly|sure thing|sure|absolutely)[!,.]?\s*(?:here\s+(?:is|are)[^:.]+[:.]\s*)?", re.IGNORECASE),
    re.compile(r"^(?:i'?d(?:\s+be)?|i would(?:\s+be)?|i am|i'm)\s+(?:happy|glad|delighted|pleased|here|excited|love)\s+to\s+[^.!?\n]+[.!?\n]+\s*", re.IGNORECASE),
    re.compile(r"^(?:as an?\s+(?:ai|financial copilot|assistant|language model)[^,.]+[,.]\s*)", re.IGNORECASE),
    re.compile(r"^(?:great|excellent)\s+question[!,.]\s*", re.IGNORECASE),
    re.compile(r"^(?:here\s+(?:are|is)|here'?s)\s+(?:what\s+you\s+need\s+to\s+know|the\s+breakdown|the\s+details|the\s+results|the\s+numbers)[:.]*\s*", re.IGNORECASE),
    re.compile(r"^(?:your\s+)?bank\s+statement\s+(?:csv\s+)?(?:has\s+been\s+)?(?:successfully\s+)?uploaded[.!?:-]*\s*", re.IGNORECASE),
    re.compile(r"^now[!,.]?\s*let'?s\s+(?:dive|look)\s+into\s+the\s+numbers[.!?:-]*\s*", re.IGNORECASE),
    re.compile(r"^based\s+on\s+(?:the|your)\s+(?:bank\s+)?statement(?:s)?(?: provided)?[,!.]*\s*", re.IGNORECASE),
    re.compile(r"^based\s+on\s+these\s+(?:verified\s+)?(?:accounting\s+)?metrics[,.]*\s*", re.IGNORECASE),
]

AI_SLOP_PHRASES = [
    re.compile(r"these\s+verified\s+accounting\s+metrics\s+provide\s+a\s+clear\s+picture[^\n.]*[\n.]*", re.IGNORECASE),
    re.compile(r"with\s+this\s+information,?\s+you\s+can\s+make\s+informed\s+decisions[^\n.]*[\n.]*", re.IGNORECASE),
    re.compile(r"to\s+optimize\s+your\s+cash\s+runway,?\s+manage\s+your\s+working\s+capital[^\n.]*[\n.]*", re.IGNORECASE),
]


def sanitize_cfo_reply(text: str) -> str:
    """Post-processing sanitizer that removes accidental chatbot throat-clearing and slop from smaller SLMs."""
    if not text:
        return ""

    # Strip surrounding quotation marks or backticks first
    cleaned = text.strip().strip("'\"“”`").strip()

    # Strip repeating bullet points of metrics that were already computed
    cleaned = re.sub(
        r"(?im)^[-*•]\s*\*{0,2}(?:Current Balance|Average Daily Burn|Estimated Historical Runway|Status|Healthiest Liquidity|Projected \d+-day Reserve|Daily Average Balance)[^\n]*\n?",
        "",
        cleaned,
    ).strip()

    # Strip corporate filler sentences
    for slop_pat in AI_SLOP_PHRASES:
        cleaned = slop_pat.sub("", cleaned).strip()

    changed = True
    while changed:
        changed = False
        cleaned = cleaned.strip("'\"“”`").strip()
        for pat in THROAT_CLEARING_PATTERNS:
            new_text = pat.sub("", cleaned).strip()
            if new_text != cleaned and new_text:
                cleaned = new_text
                changed = True

    # Strip surrounding quotation marks again in case they enclosed stripped text
    cleaned = cleaned.strip("'\"“”`").strip()

    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
        # Strip trailing dangling list items or bullet heads (e.g. "\n2." or "\n-")
        cleaned = re.sub(r"\n+[-*•\d]+[.)]?\s*$", "", cleaned)
        # If model generation was cut off mid-sentence, trim to last complete sentence
        last_punct = max(cleaned.rfind("."), cleaned.rfind("!"), cleaned.rfind("?"))
        if last_punct > 40:
            cleaned = cleaned[: last_punct + 1]
        cleaned = re.sub(r"\n+[-*•\d]+[.)]?\s*$", "", cleaned).strip()
        cleaned = cleaned.strip("'\"“”`").strip()

    return cleaned if cleaned else text.strip().strip("'\"“”`").strip()

