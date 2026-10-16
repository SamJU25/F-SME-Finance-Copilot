from decimal import Decimal
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import zen

from services.decision.base import AbstractDecisionEngine
from services.decision.types import DecisionDomain, DecisionRequest, DecisionResult

logger = logging.getLogger(__name__)

DECISION_TABLES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "contracts" / "decision_tables"


class ZenRulesAdapter(AbstractDecisionEngine):
    """
    Pluggable GoRules ZEN Engine adapter for deterministic financial compliance.
    Compiles and executes external JSON Decision Model (JDM) tables in-process
    via Rust PyO3 bindings (<0.05ms execution latency).
    """

    def __init__(self, tables_dir: Optional[Path] = None) -> None:
        self._tables_dir = tables_dir or DECISION_TABLES_DIR
        self._engine = zen.ZenEngine()
        self._decisions: Dict[DecisionDomain, Any] = {}
        self._load_decision_tables()

    @property
    def engine_id(self) -> str:
        return "zen-engine@2.1.3"

    @property
    def supported_domains(self) -> List[DecisionDomain]:
        return [
            DecisionDomain.UNDERWRITING,
            DecisionDomain.SECURITY_GATE,
            DecisionDomain.DEFICIT_SEVERITY,
        ]

    def _load_decision_tables(self) -> None:
        """Pre-compile JDM policy tables into in-memory ZenDecision graphs."""
        domain_to_file = {
            DecisionDomain.UNDERWRITING: "underwriting_policy.json",
            DecisionDomain.SECURITY_GATE: "security_gate_policy.json",
            DecisionDomain.DEFICIT_SEVERITY: "deficit_severity_policy.json",
        }

        for domain, filename in domain_to_file.items():
            filepath = self._tables_dir / filename
            if not filepath.exists():
                logger.warning("Decision table not found at %s. Skipping %s.", filepath, domain.value)
                continue

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                decision = self._engine.create_decision(content)
                self._decisions[domain] = decision
                logger.info("Compiled ZEN decision table: %s -> %s", domain.value, filename)
            except Exception as e:
                logger.error("Failed to compile ZEN decision table %s: %s", filename, str(e))

    def evaluate(self, request: DecisionRequest) -> DecisionResult:
        decision = self._decisions.get(request.domain)
        if decision is None:
            raise RuntimeError(f"ZEN decision table for domain {request.domain.value} is not loaded.")

        ctx = self._prepare_context(request)
        eval_output = decision.evaluate(ctx)

        result_dict = eval_output.get("result", {})
        perf = eval_output.get("performance", "<0.05ms")

        if request.domain == DecisionDomain.UNDERWRITING:
            selected_choice = result_dict.get("risk_tier", "HIGH_RISK")
            rationale = f"Evaluated in {perf} via JDM underwriting_policy.json (DAB={ctx.get('dab')}, NSF={ctx.get('nsf_count')})."
        elif request.domain == DecisionDomain.SECURITY_GATE:
            selected_choice = result_dict.get("security_tier", "TIER_1_OBSERVATION")
            rationale = f"Evaluated in {perf} via JDM security_gate_policy.json (Action={ctx.get('action_type')})."
        elif request.domain == DecisionDomain.DEFICIT_SEVERITY:
            selected_choice = result_dict.get("severity", "SAFE")
            rationale = f"Evaluated in {perf} via JDM deficit_severity_policy.json (Days={ctx.get('days_until_deficit')})."
        else:
            selected_choice = str(result_dict)
            rationale = f"Evaluated in {perf} via GoRules ZEN Engine."

        return DecisionResult(
            domain=request.domain,
            selected_choice=selected_choice,
            confidence_score=1.0,  # Deterministic rule table
            engine_id=self.engine_id,
            rationale=rationale,
            output_payload=result_dict,
        )

    def _prepare_context(self, request: DecisionRequest) -> Dict[str, Any]:
        """Convert input state into JSON-serializable context for ZEN evaluation."""
        state = request.input_state.copy()

        if request.domain == DecisionDomain.UNDERWRITING:
            raw_dab = state.get("daily_average_balance", state.get("dab", 0))
            dab_float = float(Decimal(str(raw_dab)))
            nsf_count = int(state.get("nsf_count", 0))
            return {
                "dab": dab_float,
                "nsf_count": nsf_count,
            }

        elif request.domain == DecisionDomain.SECURITY_GATE:
            action_type = str(state.get("action_type", "")).upper()
            return {"action_type": action_type}

        elif request.domain == DecisionDomain.DEFICIT_SEVERITY:
            days = state.get("days_until_deficit")
            has_deficit = state.get("has_deficit")
            if has_deficit is None:
                has_deficit = days is not None
            days_val = int(days) if days is not None else 9999
            return {
                "has_deficit": bool(has_deficit),
                "days_until_deficit": days_val,
            }

        return state
