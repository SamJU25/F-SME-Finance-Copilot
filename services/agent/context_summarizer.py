"""Rolling conversation summarizer for multi-turn SME Finance Copilot sessions.

Provides:
1. Deterministic conversation condensation when message count exceeds sliding window.
2. Extracts core user intents, topics discussed, and recommendations given.
3. Preserves narrative continuity across 10-50 turn sessions without bloating context.
"""

from __future__ import annotations

import logging
import re
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


def generate_deterministic_summary(
    messages: List[Any],
    existing_summary: Optional[str] = None,
) -> str:
    """Condenses older conversation turns into an objective narrative summary without LLM latency.

    Args:
        messages: List of ChatHistoryItem objects to summarize.
        existing_summary: Previous rolling summary to append/roll into.
    """
    if not messages:
        return existing_summary or ""

    user_topics: List[str] = []
    copilot_actions: List[str] = []

    for item in messages:
        if isinstance(item, dict):
            role = item.get("role", "user")
            text = item.get("text", "")
        else:
            role = getattr(item, "role", "user")
            text = getattr(item, "text", "")

        if not text:
            continue

        clean_text = text.strip()

        if role in ("user", "human"):
            # Extract key user inquiry themes
            lower_text = clean_text.lower()
            if any(k in lower_text for k in ("runway", "burn", "cash flow", "balance")):
                if "cash runway & burn analysis" not in user_topics:
                    user_topics.append("cash runway & burn analysis")
            elif any(k in lower_text for k in ("loan", "credit", "borrow", "financing", "facility")):
                if "financing & credit options" not in user_topics:
                    user_topics.append("financing & credit options")
            elif any(k in lower_text for k in ("invoice", "factoring", "receivable")):
                if "invoice factoring & receivables" not in user_topics:
                    user_topics.append("invoice factoring & receivables")
            elif any(k in lower_text for k in ("dscr", "coverage", "debt service")):
                if "debt service coverage (DSCR)" not in user_topics:
                    user_topics.append("debt service coverage (DSCR)")
            elif any(k in lower_text for k in ("payroll", "deficit", "shortfall", "crunch")):
                if "payroll liquidity & deficit early-warning" not in user_topics:
                    user_topics.append("payroll liquidity & deficit early-warning")
            elif any(k in lower_text for k in ("ccc", "conversion cycle", "dso", "dpo")):
                if "cash conversion cycle (CCC)" not in user_topics:
                    user_topics.append("cash conversion cycle (CCC)")
            else:
                # Truncate clean user snippet
                first_sentence = clean_text.split(".")[0].strip()
                if len(first_sentence) > 60:
                    first_sentence = first_sentence[:57] + "..."
                if first_sentence and first_sentence not in user_topics:
                    user_topics.append(first_sentence)

        elif role in ("agent", "assistant"):
            lower_text = clean_text.lower()
            if "### financial diagnostic summary" in lower_text or "cash runway" in lower_text:
                if "calculated cash health and runway metrics" not in copilot_actions:
                    copilot_actions.append("calculated cash health and runway metrics")
            elif "### credit underwriting assessment" in lower_text or "pre-qualified" in lower_text:
                if "evaluated borrowing capacity and pre-qualified options" not in copilot_actions:
                    copilot_actions.append("evaluated borrowing capacity and pre-qualified options")
            elif "critical" in lower_text or "shortfall" in lower_text:
                if "identified cash crunch risk" not in copilot_actions:
                    copilot_actions.append("identified cash crunch risk")
            elif "action" in lower_text or "staged" in lower_text:
                if "prepared financial action proposal" not in copilot_actions:
                    copilot_actions.append("prepared financial action proposal")

    summary_clauses = []
    if existing_summary:
        summary_clauses.append(existing_summary.rstrip("."))

    if user_topics:
        topics_str = ", ".join(user_topics[:4])
        clause = f"User inquired about {topics_str}"
        if copilot_actions:
            actions_str = ", ".join(copilot_actions[:3])
            clause += f"; Copilot {actions_str}"
        summary_clauses.append(clause)
    elif copilot_actions:
        actions_str = ", ".join(copilot_actions[:3])
        summary_clauses.append(f"Copilot {actions_str}")

    result = ". ".join(summary_clauses).strip()
    if result and not result.endswith("."):
        result += "."

    # Cap maximum summary length to prevent prompt bloat (max ~350 chars)
    if len(result) > 400:
        sentences = [s.strip() for s in result.split(".") if s.strip()]
        result = ". ".join(sentences[-3:]) + "."

    return result
