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

# Banned AI Slop Words Map (regex, plain replacement)
# Replaces inflated corporate buzzwords with direct, active vocabulary
BANNED_SLOP_WORDS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bdelv(?:e|ing|es)\s+into\b", re.IGNORECASE), "examine"),
    (re.compile(r"\bdelv(?:e|ing|es)\b", re.IGNORECASE), "examine"),
    (re.compile(r"\bleverag(?:ing|es|ed)\b", re.IGNORECASE), "using"),
    (re.compile(r"\bleverage\b", re.IGNORECASE), "use"),
    (re.compile(r"\butiliz(?:ing|es|ed)\b", re.IGNORECASE), "using"),
    (re.compile(r"\butilize\b", re.IGNORECASE), "use"),
    (re.compile(r"\butilization\b", re.IGNORECASE), "use"),
    (re.compile(r"\bfoster(?:ing|s|ed)?\b", re.IGNORECASE), "support"),
    (re.compile(r"\bempower(?:ing|s|ed)?\b", re.IGNORECASE), "enable"),
    (re.compile(r"\bstreamlin(?:ing|es|ed)\b", re.IGNORECASE), "simplifying"),
    (re.compile(r"\bstreamline\b", re.IGNORECASE), "simplify"),
    (re.compile(r"\brobust\b", re.IGNORECASE), "strong"),
    (re.compile(r"\bcutting-?edge\b", re.IGNORECASE), "modern"),
    (re.compile(r"\bparadigm\s+shift\b", re.IGNORECASE), "fundamental shift"),
    (re.compile(r"\bgame-?changer\b", re.IGNORECASE), "major advantage"),
    (re.compile(r"\bsupercharg(?:ing|es|ed)\b", re.IGNORECASE), "accelerating"),
    (re.compile(r"\bsupercharge\b", re.IGNORECASE), "accelerate"),
    (re.compile(r"\bharness(?:ing|es|ed)?\b", re.IGNORECASE), "apply"),
    (re.compile(r"\belevat(?:ing|es|ed)\b", re.IGNORECASE), "improving"),
    (re.compile(r"\belevate\b", re.IGNORECASE), "improve"),
    (re.compile(r"\bembark(?:ing|s|ed)?\s+on\b", re.IGNORECASE), "begin"),
    (re.compile(r"\bembark(?:ing|s|ed)?\b", re.IGNORECASE), "begin"),
    (re.compile(r"\bparamount\b", re.IGNORECASE), "essential"),
    (re.compile(r"\btransformative\b", re.IGNORECASE), "significant"),
    (re.compile(r"\btapestry\b", re.IGNORECASE), "framework"),
    (re.compile(r"\bbeacon\b", re.IGNORECASE), "guide"),
    (re.compile(r"\bmultifaceted\b", re.IGNORECASE), "comprehensive"),
    (re.compile(r"\bmeticulous(?:ly)?\b", re.IGNORECASE), "thoroughly"),
    (re.compile(r"\bintricate\b", re.IGNORECASE), "detailed"),
    (re.compile(r"\bever-?evolving\b", re.IGNORECASE), "evolving"),
]

# AI Slop Emojis commonly generated by conversational LLMs
AI_SLOP_EMOJI_PATTERN = re.compile(
    r"[\U0001F300-\U0001F64F\U0001F680-\U0001F6FF\U0001F700-\U0001F77F\U0001F900-\U0001F9FF\U00002700-\U000027BF\U0001FA70-\U0001FAFF]"
)

# AI Slop Phrases, throat-clearing, colon reveals, fake insights, and conclusion filler
AI_SLOP_PHRASES = [
    re.compile(r"these\s+verified\s+accounting\s+metrics\s+provide\s+a\s+clear\s+picture[^\n.]*[\n.]*", re.IGNORECASE),
    re.compile(r"with\s+this\s+information,?\s+you\s+can\s+make\s+informed\s+decisions[^\n.]*[\n.]*", re.IGNORECASE),
    re.compile(r"to\s+optimize\s+your\s+cash\s+runway,?\s+manage\s+your\s+working\s+capital[^\n.]*[\n.]*", re.IGNORECASE),
    # Faux-insight & colon reveals
    re.compile(r"\b(?:here'?s\s+the\s+thing|the\s+truth\s+is|let\s+me\s+be\s+clear|i'll\s+be\s+honest)[,:]*\s*", re.IGNORECASE),
    re.compile(r"\b(?:in\s+today's\s+fast-paced\s+world|at\s+its\s+core|look\s+no\s+further)[,:]*\s*", re.IGNORECASE),
    re.compile(r"\b(?:the\s+best\s+part|the\s+kicker|the\s+key\s+takeaway|here'?s\s+the\s+bottom\s+line)[:.]*\s*", re.IGNORECASE),
]

CONCLUSION_SLOP_PATTERN = re.compile(
    r"((?:^|(?<=[.!?\n]))\s*)(?:in\s+conclusion|ultimately|all\s+in\s+all|in\s+summary)[,:]*\s*",
    re.IGNORECASE,
)


def _preserve_case_replace(match: re.Match, replacement: str) -> str:
    """Helper to preserve UPPERCASE and TitleCase when substituting slop words."""
    val = match.group(0)
    if val.isupper():
        return replacement.upper()
    if val[0].isupper():
        return replacement.capitalize()
    return replacement


def sanitize_cfo_reply(text: str) -> str:
    """Post-processing sanitizer that removes accidental chatbot throat-clearing, markdown headers, and AI slop."""
    if not text:
        return ""

    # Strip surrounding quotation marks or backticks first
    cleaned = text.strip().strip("'\"“”`").strip()

    # Strip AI slop emojis (rockets, sparkles, robots, fire, lightbulbs) first
    cleaned = AI_SLOP_EMOJI_PATTERN.sub("", cleaned)
    # Clean up excess spaces left by emoji removal
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()

    # Strip leading markdown document headers (e.g. "### Financial Diagnostic Summary\n\n", "### Copilot Overview\n\n")
    # which smaller fine-tuned models output by default on casual replies
    cleaned = re.sub(r"^\s*(?:#{1,6}\s+[^\n]+\n*)+", "", cleaned).strip()

    # Strip standalone markdown headings mid-text that precede conversational advice
    cleaned = re.sub(r"\n+#{1,6}\s+[^\n]+\n+", "\n\n", cleaned).strip()

    # Strip repeating or hallucinated bullet points of metrics that should never be in narrative text
    cleaned = re.sub(
        r"(?im)^[-*•]\s*\*{0,2}(?:Current Balance|Cash Balance|Average Daily Burn|Monthly Burn|Estimated Historical Runway|Runway|Status|Healthiest Liquidity|Projected \d+-day Reserve|Daily Average Balance|DAB|Cash Flow Deficit|Burn Velocity|Net Inflow|Gross Outflow|Working Capital|Debt Service|Revenue Volatility|Inflow Volatility|Cash Conversion Cycle|Total Liquidity|EBITDA|Reserve|Deficit)[^\n]*\n?",
        "",
        cleaned,
    ).strip()

    # Strip any metric-like key-value bullet points with numbers/currency/percentages
    cleaned = re.sub(
        r"(?im)^[-*•]\s*\*{0,2}[A-Za-z\s]{2,30}\*{0,2}:\s*\*{0,2}[-+]?\$?\d+(?:\.\d+)?(?:[x%]|/day|/month| MoM)?(?:\s+in\s+[A-Za-z]+)?[^\n]*\n?",
        "",
        cleaned,
    ).strip()

    # Strip faux-profound conclusions while preserving spacing
    cleaned = CONCLUSION_SLOP_PATTERN.sub(r"\1", cleaned)

    # Strip corporate filler sentences, colon reveals, and faux-profound phrases
    for slop_pat in AI_SLOP_PHRASES:
        cleaned = slop_pat.sub("", cleaned).strip()

    # Replace banned AI slop words with plain direct verbs/words
    for pat, rep in BANNED_SLOP_WORDS:
        cleaned = pat.sub(lambda m, r=rep: _preserve_case_replace(m, r), cleaned)

    # Clean up excess whitespace and ensure sentence capitalization after stripped words
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    cleaned = re.sub(r"([.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), cleaned)

    changed = True
    while changed:
        changed = False
        cleaned = cleaned.strip("'\"“”`").strip()
        # Also re-check leading markdown headers after stripping quotes
        cleaned = re.sub(r"^\s*(?:#{1,6}\s+[^\n]+\n*)+", "", cleaned).strip()
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
        # Strip trailing incomplete lines with unclosed markdown bold tags (**odd count**)
        lines = cleaned.split("\n")
        while lines and lines[-1].count("**") % 2 != 0:
            lines.pop()
        cleaned = "\n".join(lines).strip()
        # If model generation was cut off mid-sentence without terminal punctuation, trim to last complete sentence
        if cleaned and cleaned[-1] not in (".", "!", "?", '"', "'", "`", "*"):
            end_matches = [m.end() for m in re.finditer(r"[.!?](?:\*{1,2}|[\"'\)\]])?(?:\s+|\n+|$)", cleaned)]
            if end_matches and end_matches[-1] > 40:
                cleaned = cleaned[: end_matches[-1]].strip()
        cleaned = re.sub(r"\n+[-*•\d]+[.)]?\s*$", "", cleaned).strip()
        cleaned = cleaned.strip("'\"“”`").strip()

    return cleaned

