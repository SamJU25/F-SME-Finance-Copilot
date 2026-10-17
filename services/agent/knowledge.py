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


@dataclass(frozen=True)
class Card:
    title: str
    area: str
    text: str


def load_cards(cards_dir: Path = CARDS_DIR) -> list[Card]:
    cards = []
    for path in sorted(cards_dir.glob("*.md")):
        for block in re.split(r"^## ", path.read_text(encoding="utf-8"), flags=re.MULTILINE)[1:]:
            title, _, body = block.partition("\n")
            cards.append(Card(title=title.strip(), area=path.stem, text=_METADATA_LINE.sub("", body.strip())))
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


def card_summary(card: Card) -> str:
    """The card's definition and importance as plain prose, used when no model is available."""
    parts = []
    for label in ("What it is:", "Why it matters:"):
        match = re.search(rf"\*\*{re.escape(label)}\*\*\s*(.+)", card.text)
        if match:
            parts.append(match.group(1).strip())
    return " ".join(parts)
