import logging
from typing import Dict, List, Optional, Tuple

from services.decision.base import AbstractDecisionEngine
from services.decision.adapters.fallback_adapter import FallbackRuleAdapter
from services.decision.types import DecisionDomain, DecisionRequest, DecisionResult

logger = logging.getLogger(__name__)


class DecisionEngineRegistry:
    """
    Central Ports & Adapters registry for pluggable decision engines.
    Provides reference-based domain routing, confidence gating, and zero-drift fallback.
    """

    _instance: Optional["DecisionEngineRegistry"] = None

    def __init__(self) -> None:
        # List of (priority, engine_adapter) pairs sorted descending by priority
        self._adapters: List[Tuple[int, AbstractDecisionEngine]] = []
        self._domain_overrides: Dict[DecisionDomain, str] = {}
        self._fallback_adapter = FallbackRuleAdapter()

        # Always register fallback adapter as default (lowest priority)
        self.register_adapter(self._fallback_adapter, priority=0)

        # Register GoRules ZEN Engine adapter for deterministic compliance if available
        try:
            from services.decision.adapters.zen_adapter import ZenRulesAdapter
            zen_adapter = ZenRulesAdapter()
            self.register_adapter(zen_adapter, priority=200)
        except Exception as e:
            logger.warning("ZenRulesAdapter could not be initialized: %s", str(e))

        # Register System-One AI model adapter for discrete intent & triage if available
        try:
            from services.decision.adapters.system_one_adapter import SystemOneModelAdapter
            sys1_adapter = SystemOneModelAdapter()
            self.register_adapter(sys1_adapter, priority=150)
        except Exception as e:
            logger.warning("SystemOneModelAdapter could not be initialized: %s", str(e))

    @classmethod
    def get_instance(cls) -> "DecisionEngineRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton for testing isolation."""
        cls._instance = None

    def register_adapter(self, adapter: AbstractDecisionEngine, priority: int = 100) -> None:
        """Register a decision engine adapter with a given evaluation priority."""
        # Remove existing adapter with same engine_id if present
        self._adapters = [pair for pair in self._adapters if pair[1].engine_id != adapter.engine_id]
        self._adapters.append((priority, adapter))
        # Keep sorted by priority descending
        self._adapters.sort(key=lambda pair: pair[0], reverse=True)
        logger.info("Registered decision adapter: %s (priority=%d)", adapter.engine_id, priority)

    def set_domain_override(self, domain: DecisionDomain, engine_id: str) -> None:
        """Explicitly route a domain to a specific engine_id."""
        self._domain_overrides[domain] = engine_id

    def clear_domain_override(self, domain: DecisionDomain) -> None:
        """Clear an explicit domain routing override."""
        self._domain_overrides.pop(domain, None)

    def reload_all(self) -> Dict[str, Any]:
        """Triggers hot-reloading across all registered adapters that support dynamic policies."""
        reload_summary: Dict[str, Any] = {}
        for _, adapter in self._adapters:
            if hasattr(adapter, "reload_tables") and callable(getattr(adapter, "reload_tables")):
                res = getattr(adapter, "reload_tables")(force=True)
                reload_summary[adapter.engine_id] = res
        return reload_summary

    def resolve_adapter(self, request: DecisionRequest) -> AbstractDecisionEngine:
        """Resolve the most qualified adapter for the request."""
        # 1. Check explicit domain override
        if request.domain in self._domain_overrides:
            target_id = self._domain_overrides[request.domain]
            for _, adapter in self._adapters:
                if adapter.engine_id == target_id and adapter.can_evaluate(request):
                    return adapter

        # 2. Match based on execution mode and priority
        for _, adapter in self._adapters:
            if not adapter.can_evaluate(request):
                continue

            # Check execution mode constraints
            is_zen_or_fallback = "zen" in adapter.engine_id.lower() or "fallback" in adapter.engine_id.lower()
            if request.execution_mode == "DETERMINISTIC_ONLY" and not is_zen_or_fallback:
                continue
            if request.execution_mode == "PROBABILISTIC_ONLY" and is_zen_or_fallback:
                continue

            return adapter

        # Default fallback
        return self._fallback_adapter

    def evaluate(self, request: DecisionRequest) -> DecisionResult:
        """
        Main entry point for consumers. Evaluates the request by reference,
        applying confidence thresholds and safe fallback chains.
        """
        adapter = self.resolve_adapter(request)

        try:
            result = adapter.evaluate(request)

            # Check if result meets confidence threshold
            if (
                result.confidence_score < request.confidence_threshold
                and request.fallback_on_low_confidence
                and adapter.engine_id != self._fallback_adapter.engine_id
            ):
                logger.warning(
                    "Decision engine %s returned low confidence (%.2f < %.2f) for %s. Invoking fallback.",
                    adapter.engine_id,
                    result.confidence_score,
                    request.confidence_threshold,
                    request.domain.value,
                )
                fallback_result = self._fallback_adapter.evaluate(request)
                fallback_result.rationale = (
                    f"Fallback engaged: {adapter.engine_id} confidence ({result.confidence_score:.2f}) "
                    f"below threshold ({request.confidence_threshold:.2f}). {fallback_result.rationale or ''}"
                )
                return fallback_result

            return result

        except Exception as e:
            logger.error("Decision engine %s failed during evaluation: %s", adapter.engine_id, str(e))
            if request.fallback_on_low_confidence and adapter.engine_id != self._fallback_adapter.engine_id:
                fallback_result = self._fallback_adapter.evaluate(request)
                fallback_result.rationale = f"Fallback engaged due to error in {adapter.engine_id}: {str(e)}"
                return fallback_result
            raise
