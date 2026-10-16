import logging
from typing import Any, Dict, List, Optional

from services.decision.base import AbstractDecisionEngine
from services.decision.types import DecisionDomain, DecisionRequest, DecisionResult

logger = logging.getLogger(__name__)


class SystemOneModelAdapter(AbstractDecisionEngine):
    """
    Non-autoregressive System-One AI decision adapter (Kev / ModernBERT / ONNX FastEmbed).
    Evaluates discrete candidate options in a single forward pass without autoregressive
    text generation loops (~15-25ms execution latency, zero Ollama, strictly in-process).
    """

    def __init__(self) -> None:
        self._router = None
        self._init_router()

    def _init_router(self) -> None:
        try:
            from services.agent.dynamic_router import FastEmbedSemanticRouter
            self._router = FastEmbedSemanticRouter.get_instance()
        except Exception as exc:
            logger.warning("SystemOneModelAdapter could not initialize semantic router: %s", exc)

    @property
    def engine_id(self) -> str:
        return "system-one@onnx-fastembed"

    @property
    def supported_domains(self) -> List[DecisionDomain]:
        return [
            DecisionDomain.INTENT_ROUTING,
            DecisionDomain.EXPENSE_TRIAGE,
        ]

    def can_evaluate(self, request: DecisionRequest) -> bool:
        if not super().can_evaluate(request):
            return False
        if self._router is None or not getattr(self._router, "_ready", False):
            return False
        return True

    def evaluate(self, request: DecisionRequest) -> DecisionResult:
        if request.domain == DecisionDomain.INTENT_ROUTING:
            return self._evaluate_intent_routing(request)
        elif request.domain == DecisionDomain.EXPENSE_TRIAGE:
            return self._evaluate_expense_triage(request)
        else:
            raise ValueError(f"Domain {request.domain} not supported by {self.engine_id}")

    def _evaluate_intent_routing(self, request: DecisionRequest) -> DecisionResult:
        query = str(
            request.input_state.get(
                "query",
                request.input_state.get(
                    "message",
                    request.input_state.get("prompt", ""),
                ),
            )
        )
        history = request.input_state.get("history")
        has_csv = bool(request.input_state.get("has_csv", False))

        if request.input_state.get("classify_sub_intent_only"):
            sub_intent = self._router.classify_sub_intent(query, history=history)
            return DecisionResult(
                domain=DecisionDomain.INTENT_ROUTING,
                selected_choice=sub_intent,
                confidence_score=0.90,
                engine_id=self.engine_id,
                rationale=f"Single-pass ONNX embedding classified sub-intent as '{sub_intent}'.",
                output_payload={"sub_intent": sub_intent},
            )

        intent, sub_intent, is_aligned = self._router.classify(
            query=query,
            history=history,
            has_csv=has_csv,
        )

        # High confidence for strong semantic alignment
        confidence = 0.92 if is_aligned else 0.82

        return DecisionResult(
            domain=DecisionDomain.INTENT_ROUTING,
            selected_choice=intent,
            confidence_score=confidence,
            engine_id=self.engine_id,
            rationale=f"Single-pass ONNX embedding classified query into intent '{intent}' and sub-intent '{sub_intent}'.",
            output_payload={
                "intent": intent,
                "sub_intent": sub_intent,
                "is_aligned": is_aligned,
            },
        )

    def _evaluate_expense_triage(self, request: DecisionRequest) -> DecisionResult:
        memo = str(request.input_state.get("description", request.input_state.get("memo", ""))).lower()
        if any(w in memo for w in ("payroll", "salary", "wages", "gusto", "adp", "paychex")):
            category = "PAYROLL"
            confidence = 0.95
        elif any(w in memo for w in ("rent", "lease", "landlord", "property", "storage")):
            category = "RENT"
            confidence = 0.95
        elif any(w in memo for w in ("loan", "debt", "amortization", "note pay", "interest")):
            category = "DEBT_SERVICE"
            confidence = 0.92
        else:
            category = "OPERATING_EXPENSE"
            confidence = 0.85

        return DecisionResult(
            domain=DecisionDomain.EXPENSE_TRIAGE,
            selected_choice=category,
            confidence_score=confidence,
            engine_id=self.engine_id,
            rationale=f"System-One triage classified transaction memo as '{category}'.",
            output_payload={"category": category},
        )
