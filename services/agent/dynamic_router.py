"""Dynamic Vector Semantic & LLM Intent Router for Autonomous SME Finance Copilot.

Dispatches intents and sub-intents dynamically using on-device FastEmbed vector semantic
embeddings (BAAI/bge-small-en-v1.5) and zero-shot LLM reasoning without hardcoded keyword lists.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from services.agent.schema import LLMConfig

logger = logging.getLogger(__name__)

INTENT_SYSTEM_PROMPT = (
    "You are the intent classification intelligence for an Autonomous SME Finance Copilot.\n"
    "Categorize the user's message into exactly one of these categories:\n\n"
    "- GENERAL_ASSISTANCE: greetings, introductions, capabilities, how to get started, or non-financial/off-topic questions.\n"
    "- CASH_DIAGNOSTIC: inquiries about cash runway, balance, burn rate, overdrafts, cash deficits, or financial health.\n"
    "- CREDIT_UNDERWRITING: inquiries about borrowing money, loan options, pre-qualified credit lines, factoring, or APR rates.\n"
    "- ACTION_STAGING: requests to stage, draw, transfer, pledge, or execute a loan action or financial transfer.\n\n"
    "Respond with ONLY the category name and nothing else."
)


def _parse_intent_label(raw_output: Optional[str]) -> Optional[str]:
    """Extracts valid intent enum name from raw LLM output."""
    if not raw_output:
        return None
    cleaned = raw_output.strip().upper()
    for valid in ("CASH_DIAGNOSTIC", "CREDIT_UNDERWRITING", "ACTION_STAGING", "GENERAL_ASSISTANCE"):
        if valid in cleaned:
            return valid
    return None


from services.decision.policy_loader import load_semantic_prototypes


class FastEmbedSemanticRouter:
    """Zero-keyword vector semantic router using on-device FastEmbed embeddings (ONNX)."""

    _instance: Optional["FastEmbedSemanticRouter"] = None

    _intents, _subs, _disc = load_semantic_prototypes()
    INTENT_PROTOTYPES = _intents
    SUB_INTENT_PROTOTYPES = _subs
    DISCLAIMER_PROTOTYPE = _disc



    def __init__(self) -> None:
        try:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            self._intent_keys = list(self.INTENT_PROTOTYPES.keys())
            embeds = np.array(list(self._model.embed([self.INTENT_PROTOTYPES[k] for k in self._intent_keys])))
            self._intent_norms = embeds / np.linalg.norm(embeds, axis=1, keepdims=True)

            self._sub_keys = list(self.SUB_INTENT_PROTOTYPES.keys())
            sub_embeds = np.array(list(self._model.embed([self.SUB_INTENT_PROTOTYPES[k] for k in self._sub_keys])))
            self._sub_norms = sub_embeds / np.linalg.norm(sub_embeds, axis=1, keepdims=True)

            disc_embed = np.array(list(self._model.embed([self.DISCLAIMER_PROTOTYPE])))[0]
            self._disclaimer_norm = disc_embed / np.linalg.norm(disc_embed)
            self._ready = True
        except Exception as exc:
            logger.warning("FastEmbedSemanticRouter initialization failed: %s", exc)
            self._ready = False

    @classmethod
    def get_instance(cls) -> "FastEmbedSemanticRouter":
        if cls._instance is None:
            cls._instance = FastEmbedSemanticRouter()
        return cls._instance

    def classify(
        self,
        query: str,
        history: Optional[List[Any]] = None,
        has_csv: bool = False,
    ) -> Tuple[str, str, bool]:
        """Classifies intent, sub-intent, and domain alignment using vector embeddings."""
        m = query.strip()
        if not m:
            if has_csv:
                return "CASH_DIAGNOSTIC", "GENERAL", False
            return "GENERAL_ASSISTANCE", "GENERAL", False

        if not self._ready:
            return "GENERAL_ASSISTANCE", "GENERAL", False

        # 1. Standalone semantic embedding evaluation
        q_embed = np.array(list(self._model.embed([m])))[0]
        q_norm = q_embed / np.linalg.norm(q_embed)

        sub_sims = np.dot(self._sub_norms, q_norm)
        sorted_sub_idx = np.argsort(sub_sims)[::-1]
        top_sub_score = float(sub_sims[sorted_sub_idx[0]])
        second_sub_score = float(sub_sims[sorted_sub_idx[1]])
        sub_margin = top_sub_score - second_sub_score

        # 2. Contextual fusion: if query has low sub-intent separation (< 0.03) and history exists,
        # resolve ambiguous conversational follow-ups using semantic antecedent
        if history and sub_margin < 0.03:
            last_user_msg = ""
            for item in reversed(history):
                role = getattr(item, "role", "") if hasattr(item, "role") else (item.get("role", "") if isinstance(item, dict) else "")
                txt = (getattr(item, "text", "") if hasattr(item, "text") else (item.get("text", "") if isinstance(item, dict) else "")).strip()
                if role == "user" and not last_user_msg:
                    last_user_msg = txt
                    break

            if last_user_msg:
                fused = f"{last_user_msg} {m}"
                q_embed = np.array(list(self._model.embed([fused])))[0]
                q_norm = q_embed / np.linalg.norm(q_embed)

        sims = np.dot(self._intent_norms, q_norm)
        scores = {self._intent_keys[i]: float(sims[i]) for i in range(len(self._intent_keys))}

        off_score = scores.get("OFF_TOPIC", 0.0)
        cash_score = scores.get("CASH_DIAGNOSTIC", 0.0)
        credit_score = scores.get("CREDIT_UNDERWRITING", 0.0)
        action_score = scores.get("ACTION_STAGING", 0.0)
        greet_score = scores.get("GENERAL_ASSISTANCE", 0.0)

        financial_score = max(cash_score, credit_score, action_score)

        # Off-topic detection using statistical significance margins (zero keyword lists)
        is_off_topic = False
        if financial_score < 0.44 and greet_score < 0.48:
            is_off_topic = True
        elif off_score > financial_score:
            if (off_score - greet_score) >= 0.005 and off_score > 0.45:
                is_off_topic = True
            elif greet_score < 0.42:
                is_off_topic = True

        if is_off_topic:
            return "GENERAL_ASSISTANCE", "OFF_TOPIC", True

        # Rank financial & conversational intents
        ranked = sorted(
            [
                ("CASH_DIAGNOSTIC", cash_score),
                ("CREDIT_UNDERWRITING", credit_score),
                ("ACTION_STAGING", action_score),
                ("GENERAL_ASSISTANCE", greet_score),
            ],
            key=lambda x: x[1],
            reverse=True,
        )
        best_intent = ranked[0][0]

        # Contextual adjustment: when no CSV is loaded and scores are tied, route to onboarding guidance
        if not has_csv and best_intent in ("CASH_DIAGNOSTIC", "CREDIT_UNDERWRITING") and (financial_score - greet_score) < 0.03:
            best_intent = "GENERAL_ASSISTANCE"

        # Bayesian likelihood prior: an active statement artifact in session adds likelihood to cash evaluation
        if has_csv and best_intent == "GENERAL_ASSISTANCE" and (financial_score + 0.08) >= greet_score:
            best_intent = "CASH_DIAGNOSTIC"

        # Sub-intent classification via vector similarity and statistical confidence margin
        sub_sims = np.dot(self._sub_norms, q_norm)
        sorted_sub_indices = np.argsort(sub_sims)[::-1]
        top_sub_idx = int(sorted_sub_indices[0])
        top_sub = self._sub_keys[top_sub_idx]
        top_sub_score = float(sub_sims[top_sub_idx])
        second_sub_score = float(sub_sims[sorted_sub_indices[1]])
        sub_margin = top_sub_score - second_sub_score

        # If general assistance dominates, only route to a quantitative tool if there is a distinct, high-confidence match
        if best_intent == "GENERAL_ASSISTANCE":
            if top_sub_score >= 0.74 and sub_margin >= 0.05:
                best_sub = top_sub
            else:
                best_sub = "GENERAL"
        else:
            best_sub = top_sub

        return best_intent, best_sub, False

    def is_off_topic(self, message: str, history: Optional[List[Any]] = None) -> bool:
        """Determines if query is out of domain using semantic distance."""
        _, _, off_topic = self.classify(message, history=history)
        return off_topic

    def is_disclaimer(self, text: str) -> bool:
        """Determines if text is an unhelpful AI capability disclaimer or refusal via vector similarity."""
        if not text or not self._ready:
            return False
        q_embed = np.array(list(self._model.embed([text.strip()])))[0]
        q_norm = q_embed / np.linalg.norm(q_embed)
        sim = float(np.dot(self._disclaimer_norm, q_norm))
        return sim >= 0.55

    def classify_sub_intent(self, message: str, history: Optional[List[Any]] = None) -> str:
        """Classifies cash diagnostic sub-intent via semantic prototype matching."""
        _, sub, _ = self.classify(message, history=history)
        return sub


def is_ai_disclaimer(text: str) -> bool:
    """Detects whether generated text is an unhelpful AI disclaimer or refusal using vector similarity."""
    return FastEmbedSemanticRouter.get_instance().is_disclaimer(text)


def is_in_domain_finance_query(message: str, history: Optional[List[Any]] = None) -> bool:
    """Evaluates whether user message is within the SME Finance & Copilot domain."""
    return not FastEmbedSemanticRouter.get_instance().is_off_topic(message, history=history)


def is_off_topic_query(message: str, history: Optional[List[Any]] = None) -> bool:
    """Detects if a user message is non-financial and off-topic using vector semantic distance."""
    return FastEmbedSemanticRouter.get_instance().is_off_topic(message, history=history)


def _query_llm_for_intent(
    message: str,
    history: Optional[List[Any]] = None,
    has_csv: bool = False,
    config: Optional[LLMConfig] = None,
) -> Optional[str]:
    """Queries either local on-device SLM or cloud LLM to classify user intent dynamically."""
    context_hint = ""
    if history:
        last_entry = history[-1]
        last_text = (
            getattr(last_entry, "text", "")
            if hasattr(last_entry, "text")
            else (last_entry.get("text", "") if isinstance(last_entry, dict) else "")
        )
        if last_text:
            context_hint += f"\nPrevious assistant message: {last_text}"
    if has_csv:
        context_hint += "\nNote: A bank statement CSV is already loaded."

    prompt = f"User message: {message}{context_hint}\n\nCategory:"

    try:
        provider = (config.provider if config else "offline").lower()

        # Offline Local Engine (SME Finance LoRA)
        if provider == "offline":
            from services.agent.local_transformers import LocalTransformersEngine
            trans = LocalTransformersEngine.get_instance()
            if trans.is_available():
                raw = trans.generate(
                    prompt=prompt,
                    system_instruction=INTENT_SYSTEM_PROMPT,
                    max_new_tokens=15,
                    temperature=0.0,
                )
                return _parse_intent_label(raw)
            from services.agent.local_slm import LocalSLMEngine
            engine = LocalSLMEngine.get_instance()
            if engine.is_available():
                raw = engine.generate(
                    prompt=prompt,
                    system_instruction=INTENT_SYSTEM_PROMPT,
                    max_new_tokens=15,
                    temperature=0.0,
                )
                return _parse_intent_label(raw)

        # External Cloud Provider (Gemini, Claude, OpenAI, DeepSeek, Groq, Custom)
        elif config:
            from services.agent.llm_bridge import query_external_llm
            raw = query_external_llm(
                prompt=prompt,
                system_instruction=INTENT_SYSTEM_PROMPT,
                config=config,
            )
            return _parse_intent_label(raw)

    except Exception as exc:
        logger.warning("Dynamic LLM intent classification error: %s", exc)

    return None


def classify_intent_dynamic(
    message: str,
    history: Optional[List[Any]] = None,
    has_csv: bool = False,
    config: Optional[LLMConfig] = None,
) -> str:
    """Dynamically classifies user message into a financial intent using vector embeddings or LLM."""
    clean_msg = message.strip()
    if not clean_msg:
        return "CASH_DIAGNOSTIC" if has_csv else "GENERAL_ASSISTANCE"

    # Dynamic LLM Classification (if cloud LLM configured and outside test runner)
    if "PYTEST_CURRENT_TEST" not in os.environ and config and config.provider and config.provider.lower() != "offline":
        llm_result = _query_llm_for_intent(clean_msg, history, has_csv, config)
        if llm_result:
            return llm_result

    # Evaluate intent by reference via DecisionEngineRegistry (zero hardcoded engine logic)
    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.INTENT_ROUTING,
        input_state={
            "query": clean_msg,
            "history": history,
            "has_csv": has_csv,
        },
        execution_mode="AUTO",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    return decision_res.selected_choice


def classify_sub_intent_dynamic(message: str, history: Optional[List[Any]] = None) -> str:
    """Classifies cash diagnostic sub-intent dynamically by reference via DecisionEngineRegistry."""
    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.INTENT_ROUTING,
        input_state={
            "query": message.strip(),
            "history": history,
            "classify_sub_intent_only": True,
        },
        execution_mode="AUTO",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    sub = decision_res.output_payload.get("sub_intent")
    if sub:
        return sub
    return decision_res.selected_choice
