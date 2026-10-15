"""In-process Semantic Vector Router for Autonomous SME Finance Copilot.

Uses FastEmbed with BAAI/bge-small-en-v1.5 running on ONNX Runtime to classify
user messages into financial intents using vector cosine similarity.
Eliminates brittle keyword guessing and runs entirely in-process on CPU without Ollama.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

# Standard financial intent anchors representing semantic centroids
INTENT_ANCHORS: Dict[str, List[str]] = {
    "CASH_DIAGNOSTIC": [
        "how many days left",
        "what is my cash runway and daily burn rate",
        "when will our money run out",
        "how much cash balance do we have left",
        "how long can my business survive",
        "what are my daily expenses and burn",
        "am I bleeding cash or having an overdraft deficit",
        "how much money do I have",
        "how much am I spending every day",
        "when does my balance hit zero",
        "predict our cash position and runway",
        "what is our cash conversion cycle and working capital",
        "will I run out of cash next month",
    ],
    "CREDIT_UNDERWRITING": [
        "what loans or credit lines can I qualify for",
        "can I get a working capital loan or financing",
        "how much money can my business borrow",
        "what are the APR rates and financing facilities available",
        "evaluate our WeBank digital underwriting dossier",
        "can I borrow money",
        "find financing options for our business",
        "what credit facilities can we apply for",
        "show me pre-qualified lenders and true APR",
    ],
    "ACTION_STAGING": [
        "stage an application to draw line of credit",
        "apply for the working capital loan",
        "commit a fund transfer or draw funds",
        "pledge customer invoice for liquidity",
        "execute the credit agreement",
        "stage a draw of $25,000",
        "stage a transfer of funds",
        "draw down on our approved line of credit",
    ],
    "GENERAL_ASSISTANCE": [
        "hello what can you do for my business",
        "explain your features and capabilities",
        "who are you and how do you work",
        "help me get started",
        "hi there",
        "what is the purpose of this copilot",
        "what is my financial status",
        "what is our overall financial status",
        "general financial status",
        "hello copilot how can you assist our business with cash management",
        "how can you help our business or company",
        "what can you do to help my business",
    ],
}


class SemanticRouter:
    """Singleton Vector Router backed by FastEmbed ONNX embeddings."""

    _instance: Optional[SemanticRouter] = None

    def __init__(self) -> None:
        self._model = None
        self._centroids: Dict[str, np.ndarray] = {}
        self._initialized = False

    @classmethod
    def get_instance(cls) -> SemanticRouter:
        if cls._instance is None:
            cls._instance = SemanticRouter()
        return cls._instance

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        try:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

            # Pre-compute normalized centroid vectors for each intent
            for intent, utterances in INTENT_ANCHORS.items():
                embs = list(self._model.embed(utterances))
                norm_embs = [e / np.linalg.norm(e) for e in embs if np.linalg.norm(e) > 0]
                if norm_embs:
                    centroid = np.mean(norm_embs, axis=0)
                    self._centroids[intent] = centroid / np.linalg.norm(centroid)

            self._initialized = True
            logger.info("SemanticRouter initialized with %d intent centroids", len(self._centroids))
        except Exception as exc:
            logger.warning("FastEmbed initialization failed: %s. Fallback mode enabled.", exc)
            self._initialized = False

    def classify(self, text: str, threshold: float = 0.55) -> Tuple[str, float]:
        """Classify a user query into an intent using cosine similarity against centroids.

        Args:
            text: Raw user message.
            threshold: Minimum cosine similarity required to match a specific intent.

        Returns:
            Tuple of (intent_name, confidence_score).
        """
        if not text or not text.strip():
            return "GENERAL_ASSISTANCE", 1.0

        clean_text = text.strip()
        self._ensure_initialized()

        if not self._initialized or not self._model or not self._centroids:
            return "GENERAL_ASSISTANCE", 0.0

        try:
            q_emb = list(self._model.embed([clean_text]))[0]
            norm = np.linalg.norm(q_emb)
            if norm == 0:
                return "GENERAL_ASSISTANCE", 0.0
            q_norm = q_emb / norm

            best_intent = "GENERAL_ASSISTANCE"
            best_score = -1.0

            for intent, centroid in self._centroids.items():
                score = float(np.dot(q_norm, centroid))
                if score > best_score:
                    best_score = score
                    best_intent = intent

            if best_score < threshold:
                return "GENERAL_ASSISTANCE", best_score

            return best_intent, best_score
        except Exception as exc:
            logger.warning("Semantic classification error: %s", exc)
            return "GENERAL_ASSISTANCE", 0.0


def semantic_classify(text: str, threshold: float = 0.55) -> Tuple[str, float]:
    """Convenience helper to classify intent via singleton SemanticRouter."""
    return SemanticRouter.get_instance().classify(text, threshold=threshold)
