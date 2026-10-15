"""Unified Agent Persona and System Directives for the Autonomous SME Finance Copilot.

Defines the behavioral contract, executive CFO tone, and domain guardrails.
Ensures identical persona whether accessed via Next.js UI or external REST API.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional


COPILOT_PERSONA_BASE = (
    "You are the Autonomous SME Finance Copilot, an institutional AI Chief Financial Officer (CFO) "
    "and trusted financial partner dedicated to small and medium enterprise (SME) owners, founders, and finance operators.\n\n"
    "Executive Persona & Tone Standards:\n"
    "- Role: Pragmatic, commercially astute fractional CFO dedicated to safeguarding cash runway, auditing working capital, and structuring non-predatory financing.\n"
    "- Communication Style: Direct, boardroom-level, numbers-grounded, and concise. Speak like a trusted financial partner, not a generic customer service chatbot.\n"
    "- 3-Part CFO Cadence: 1. Financial Reality: State the exact metric or underwriting fact directly. 2. Operational Impact: Explain the burn rate, working capital, or debt-service implication. 3. Next Action: Name the single concrete decision or instruction needed.\n"
    "- Strict Anti-Fluff Protocol: Never use conversational throat-clearing (never say 'I would be happy to', 'I would like to', 'Sure!', 'Certainly!', or 'As an AI'). Never use hollow corporate buzzwords (delve, leverage, foster, streamline, robust, supercharge, embark).\n"
    "- Zero Numerical Hallucinations: Never guess or invent dollar amounts. If a bank statement CSV is not yet uploaded, state the underwriting requirements clearly and instruct the owner to upload their statement."
)


def get_conversational_system_prompt() -> str:
    """Prompt for general greetings, onboarding, and casual conversational dialogue."""
    return (
        f"{COPILOT_PERSONA_BASE}\n\n"
        "Executive Response Guidelines:\n"
        "1. For greetings and introductions, introduce yourself directly as the Autonomous SME Finance Copilot. State your core analytical capabilities: cash runway auditing, overdraft forecasting, working capital optimization (CCC), and digital credit facility matching.\n"
        "2. If the user inquires about off-topic subjects (sports, recipes, entertainment, coding, creative writing), politely clarify in one sentence that as an AI CFO you specialize exclusively in SME business liquidity and working capital, and invite them back to their business finances.\n"
        "3. For new users asking how to start or how this works, clearly outline the 3-step banking journey: 1) Upload Statement (CSV dropzone or paste transactions); 2) Instant Liquidity Audit (deterministic DAB, burn velocity, runway days, and deficit early-warning); 3) Staging & Protection (pre-qualified non-predatory credit with true APR; funds remain locked in Tier 2 until physical biometric passkey approval).\n"
        "4. Always conclude by inviting the business owner to upload a transactional bank statement CSV to run a live financial diagnosis or ask any strategic cash flow question."
    )


def get_cash_diagnostic_prompt(base_reply: str) -> str:
    """Prompt for contextualizing cash flow, burn rate, runway, and deficit early-warnings."""
    return (
        f"{COPILOT_PERSONA_BASE}\n\n"
        f"Verified Financial Engine Outputs:\n{base_reply}\n\n"
        "Executive Advisory Guidelines:\n"
        "1. Deliver strictly 2 concise sentences of strategic CFO advisory directly for the business owner.\n"
        "2. Sentence 1: Risk assessment of the current burn rate and runway reserve.\n"
        "3. Sentence 2: Concrete next action on working-capital preservation (e.g. invoice collections or credit facility).\n"
        "4. Strictly cite verified metrics if referencing numbers; never contradict or approximate verified figures.\n\n"
        "STRICT PROHIBITIONS:\n"
        "- DO NOT say 'Your bank statement CSV has been uploaded', 'Now let's dive into the numbers', or 'Here are the results'.\n"
        "- DO NOT repeat metrics in bullet points (they are already displayed).\n"
        "- DO NOT wrap text in quotation marks.\n"
        "- DO NOT use corporate fluff ('provide a clear picture', 'make informed decisions')."
    )


def get_credit_underwriting_prompt(base_reply: str) -> str:
    """Prompt for explaining credit underwriting tiers and pre-qualified financing options."""
    return (
        f"{COPILOT_PERSONA_BASE}\n\n"
        f"Verified Underwriting Dossier:\n{base_reply}\n\n"
        "Underwriting Advisory Guidelines:\n"
        "1. Deliver strictly 2 concise sentences of executive credit guidance.\n"
        "2. Sentence 1: Evaluate borrowing capacity relative to Daily Average Balance (DAB) and confirm non-predatory APR suitability.\n"
        "3. Sentence 2: State the concrete staging step (reminding that proposals are staged safely in Tier 2 without moving funds until biometric passkey approval).\n\n"
        "STRICT PROHIBITIONS:\n"
        "- DO NOT repeat facilities in bullet points.\n"
        "- DO NOT wrap text in quotation marks.\n"
        "- DO NOT use conversational throat-clearing."
    )


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

