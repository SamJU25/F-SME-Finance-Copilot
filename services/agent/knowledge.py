"""
Concept-card retrieval for model prompts.

Cards in knowledge/cards/*.md (one "## " section per concept) are embedded once with the
FastEmbed model the semantic router already holds, so no second ONNX model is loaded.
Retrieved cards supply definitions and context only; business figures in a reply must
still come from the deterministic engine output (see prompts.numbers_are_grounded).
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

CARDS_DIR = Path(__file__).resolve().parents[2] / "knowledge" / "cards"
TOP_K = 3
# Below this cosine similarity a card is unrelated to the question: with bge-small, off-topic
# questions ("pasta recipe", "hello") top out at 0.43-0.50 while concept questions hit 0.70-0.83.
MIN_SIMILARITY = 0.6
_METADATA_LINE = re.compile(r"^<!--.*?-->\s*", re.DOTALL)
_TOOLS_FIELD = re.compile(r"tools:\s*([\w, ]+?)\s*(?:\||-->)")

# Missing-input calculation key (as passed to get_missing_param_guidance) -> engine tool.
# Cards name tools in their metadata, which is how a question is matched to a calculation.
CALCULATION_TOOLS = {
    "ALTMAN_Z_SCORE": "tool_calculate_altman_z_score",
    "AMORTIZATION": "tool_calculate_loan_amortization",
    "ATTRITION": "tool_calculate_revenue_attrition_impact",
    "BREAK_EVEN": "tool_calculate_break_even",
    "BREAK_EVEN_UNITS": "tool_calculate_break_even_units",
    "CAC_PAYBACK": "tool_calculate_cac_payback",
    "CASH_DRAG": "tool_calculate_cash_drag",
    "CONCENTRATION": "tool_calculate_client_concentration",
    "CURRENCY_CONVERSION": "tool_convert_currency",
    "CURRENT_RATIO": "tool_calculate_current_ratio",
    "DCF_VALUATION": "tool_calculate_dcf_valuation",
    "DEBT_CAPACITY": "tool_calculate_prudent_debt_capacity",
    "DEBT_SERVICE_BURDEN": "tool_calculate_debt_service_burden",
    "DEBT_TO_EQUITY": "tool_calculate_debt_to_equity",
    "DEFENSIVE_INTERVAL": "tool_calculate_defensive_interval",
    "DSCR": "tool_calculate_dscr",
    "DUPONT_ROE": "tool_calculate_dupont_roe",
    "ENTERPRISE_VALUE": "tool_calculate_enterprise_value",
    "EVA": "tool_calculate_eva",
    "FACTORING": "tool_calculate_factoring_proceeds",
    "FCCR": "tool_calculate_fccr",
    "FCFF": "tool_calculate_free_cash_flow",
    "FX_EXPOSURE": "tool_calculate_fx_exposure",
    "INTEREST_COVERAGE": "tool_calculate_interest_coverage",
    "INVOICE_HASH": "tool_verify_invoice_hash",
    "LEASE_VS_BUY": "tool_calculate_lease_vs_buy",
    "LTV_CAC": "tool_calculate_ltv_cac",
    "NET_DEBT_TO_EBITDA": "tool_calculate_net_debt_to_ebitda",
    "NRR": "tool_calculate_nrr",
    "OCF_RATIO": "tool_calculate_operating_cash_flow_ratio",
    "QUICK_RATIO": "tool_calculate_quick_ratio",
    "ROA": "tool_calculate_roa",
    "ROIC": "tool_calculate_roic",
    "TRADE_CREDIT": "tool_calculate_trade_credit_apr",
    "WACC": "tool_calculate_wacc",
    "WCR": "tool_calculate_wcr",
}


@dataclass(frozen=True)
class Card:
    title: str
    area: str
    text: str
    tools: tuple[str, ...] = ()


def load_cards(cards_dir: Path = CARDS_DIR) -> list[Card]:
    cards = []
    for path in sorted(cards_dir.glob("*.md")):
        for block in re.split(r"^## ", path.read_text(encoding="utf-8"), flags=re.MULTILINE)[1:]:
            title, _, body = block.partition("\n")
            body = body.strip()
            tools_match = _TOOLS_FIELD.search(body.split("\n", 1)[0])
            tools = tuple(t.strip() for t in tools_match.group(1).split(",")) if tools_match else ()
            cards.append(Card(title=title.strip(), area=path.stem, text=_METADATA_LINE.sub("", body), tools=tools))
    return cards


class _CardIndex:
    _instance: Optional["_CardIndex"] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        from services.agent.dynamic_router import FastEmbedSemanticRouter

        router = FastEmbedSemanticRouter.get_instance()
        self._model = router._model if router._ready else None
        self.cards = load_cards()
        self._norms = None
        if self._model is not None and self.cards:
            passages = [f"{c.title}. {c.text.replace('**', '')}" for c in self.cards]
            embeds = np.array(list(self._model.passage_embed(passages)))
            self._norms = embeds / np.linalg.norm(embeds, axis=1, keepdims=True)

    @classmethod
    def get(cls) -> "_CardIndex":
        with cls._lock:
            if cls._instance is None:
                cls._instance = _CardIndex()
            return cls._instance

    def search(self, query: str, k: int, min_similarity: float) -> list[Card]:
        if self._norms is None or not query.strip():
            return []
        q = np.array(list(self._model.query_embed([query.strip()])))[0]
        sims = self._norms @ (q / np.linalg.norm(q))
        order = np.argsort(sims)[::-1][:k]
        return [self.cards[i] for i in order if sims[i] >= min_similarity]


def retrieve_cards(query: str, k: int = TOP_K, min_similarity: float = MIN_SIMILARITY) -> list[Card]:
    try:
        return _CardIndex.get().search(query, k, min_similarity)
    except Exception as exc:
        logger.warning("Concept card retrieval unavailable: %s", exc)
        return []


def format_reference_cards(sys_directive: str, cards: list[Card]) -> str:
    if not cards:
        return sys_directive
    notes = "\n\n".join(f"### {c.title}\n{c.text}" for c in cards)
    return (
        f"{sys_directive}\n\n"
        "Reference notes (use for definitions and context; figures about this business must come "
        "only from the verified engine outputs or the owner's message):\n\n"
        f"{notes}"
    )


def append_reference_cards(sys_directive: str, query: str) -> str:
    return format_reference_cards(sys_directive, retrieve_cards(query))


def select_concept_card(cards: list[Card], calculation: Optional[str]) -> tuple[Card, bool]:
    """
    Picks the card to summarise for a missing-input question and whether the calculation's
    "how to calculate" steps belong in the reply.

    The sub-intent router can pick the wrong calculation ("Explain the cash conversion cycle"
    lands on cash drag), so steps are kept only when a retrieved card names that calculation's
    tool. Calculations no card covers keep their steps, since relevance cannot be judged.
    """
    tool = CALCULATION_TOOLS.get(calculation or "")
    if tool is None:
        return cards[0], True
    matching = next((c for c in cards if tool in c.tools), None)
    if matching is not None:
        return matching, True
    covered = any(tool in c.tools for c in _CardIndex.get().cards)
    return cards[0], not covered


def card_summary(card: Card) -> str:
    """The card's definition and importance as plain prose, used when no model is available."""
    parts = []
    for label in ("What it is:", "Why it matters:"):
        match = re.search(rf"\*\*{re.escape(label)}\*\*\s*(.+)", card.text)
        if match:
            parts.append(match.group(1).strip())
    return " ".join(parts)
