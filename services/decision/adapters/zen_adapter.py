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
        self._table_mtimes: Dict[DecisionDomain, float] = {}
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
            DecisionDomain.WORKING_CAPITAL_RISK,
        ]

    def _get_domain_file_map(self) -> Dict[DecisionDomain, str]:
        return {
            DecisionDomain.UNDERWRITING: "underwriting_policy.json",
            DecisionDomain.SECURITY_GATE: "security_gate_policy.json",
            DecisionDomain.DEFICIT_SEVERITY: "deficit_severity_policy.json",
            DecisionDomain.WORKING_CAPITAL_RISK: "working_capital_policy.json",
        }

    def _load_decision_tables(self, force: bool = False) -> Dict[str, str]:
        """Pre-compile JDM policy tables into in-memory ZenDecision graphs with mtime cache."""
        domain_to_file = self._get_domain_file_map()
        status: Dict[str, str] = {}

        for domain, filename in domain_to_file.items():
            filepath = self._tables_dir / filename
            if not filepath.exists():
                logger.warning("Decision table not found at %s. Skipping %s.", filepath, domain.value)
                status[domain.value] = "FILE_NOT_FOUND"
                continue

            try:
                current_mtime = filepath.stat().st_mtime
                if not force and domain in self._table_mtimes and self._table_mtimes[domain] == current_mtime:
                    status[domain.value] = "UNCHANGED"
                    continue

                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                decision = self._engine.create_decision(content)
                self._decisions[domain] = decision
                self._table_mtimes[domain] = current_mtime
                status[domain.value] = "COMPILED"
                logger.info("Compiled ZEN decision table: %s -> %s (mtime=%.1f)", domain.value, filename, current_mtime)
            except Exception as e:
                logger.error("Failed to compile ZEN decision table %s: %s", filename, str(e))
                status[domain.value] = f"ERROR: {str(e)}"

        return status

    def reload_tables(self, force: bool = True) -> Dict[str, str]:
        """Explicitly reloads and recompiles all policy tables without server restart."""
        return self._load_decision_tables(force=force)

    def _check_auto_reload(self, domain: DecisionDomain) -> None:
        """Lightweight check to hot-reload if file modified on disk."""
        filename = self._get_domain_file_map().get(domain)
        if not filename:
            return
        filepath = self._tables_dir / filename
        if filepath.exists():
            try:
                current_mtime = filepath.stat().st_mtime
                if self._table_mtimes.get(domain) != current_mtime:
                    self._load_decision_tables(force=True)
            except Exception:
                pass

    def evaluate(self, request: DecisionRequest) -> DecisionResult:
        self._check_auto_reload(request.domain)
        decision = self._decisions.get(request.domain)
        if decision is None:
            raise RuntimeError(f"ZEN decision table for domain {request.domain.value} is not loaded.")

        ctx = self._prepare_context(request)
        eval_output = decision.evaluate(ctx, {"trace": True})

        result_dict = eval_output.get("result", {})
        perf = eval_output.get("performance", "<0.05ms")

        # Parse duration in microseconds
        duration_us: Optional[int] = None
        if perf:
            try:
                clean_perf = perf.replace("µs", "").replace("ms", "").replace("s", "").strip()
                if "ms" in perf:
                    duration_us = int(float(clean_perf) * 1000)
                else:
                    duration_us = int(float(clean_perf))
            except Exception:
                pass

        # Extract fired rule ID and description from ZEN trace
        matched_rule_id: Optional[str] = None
        matched_rule_desc: Optional[str] = None
        trace = eval_output.get("trace", {})
        for _, node_data in trace.items():
            if isinstance(node_data, dict) and "traceData" in node_data:
                trace_data = node_data.get("traceData")
                if isinstance(trace_data, dict) and "rule" in trace_data:
                    rule = trace_data.get("rule", {})
                    matched_rule_id = rule.get("_id")
                    matched_rule_desc = rule.get("_description")
                    break

        adverse_factors: List[str] = []

        if request.domain == DecisionDomain.UNDERWRITING:
            selected_choice = result_dict.get("risk_tier", "HIGH_RISK")
            dab_val = float(ctx.get("dab", 0.0))
            nsf_val = int(ctx.get("nsf_count", 0))
            if selected_choice == "HIGH_RISK":
                if dab_val < 3000.0:
                    adverse_factors.append("DAB_BELOW_MINIMUM_THRESHOLD")
                if nsf_val > 1:
                    adverse_factors.append("EXCESSIVE_NSF_COUNT")
            elif selected_choice == "NEAR_PRIME":
                if dab_val < 10000.0:
                    adverse_factors.append("DAB_BELOW_PRIME_THRESHOLD")
                if nsf_val > 0:
                    adverse_factors.append("NSF_INCIDENTS_RECORDED")
            rationale = f"Evaluated in {perf} via JDM underwriting_policy.json (Rule={matched_rule_id}, DAB={dab_val}, NSF={nsf_val})."
        elif request.domain == DecisionDomain.SECURITY_GATE:
            selected_choice = result_dict.get("security_tier", "TIER_1_OBSERVATION")
            rationale = f"Evaluated in {perf} via JDM security_gate_policy.json (Rule={matched_rule_id}, Action={ctx.get('action_type')})."
        elif request.domain == DecisionDomain.DEFICIT_SEVERITY:
            selected_choice = result_dict.get("severity", "SAFE")
            rationale = f"Evaluated in {perf} via JDM deficit_severity_policy.json (Rule={matched_rule_id}, Days={ctx.get('days_until_deficit')})."
        elif request.domain == DecisionDomain.WORKING_CAPITAL_RISK:
            selected_choice = result_dict.get("status", "BALANCED")
            rationale = f"Evaluated in {perf} via JDM working_capital_policy.json (Rule={matched_rule_id}, Metric={ctx.get('metric')}, Value={ctx.get('value')})."
        else:
            selected_choice = str(result_dict)
            rationale = f"Evaluated in {perf} via GoRules ZEN Engine."

        return DecisionResult(
            domain=request.domain,
            selected_choice=selected_choice,
            confidence_score=1.0,  # Deterministic rule table
            engine_id=self.engine_id,
            matched_rule_id=matched_rule_id,
            matched_rule_description=matched_rule_desc,
            adverse_factors=adverse_factors,
            evaluation_duration_us=duration_us,
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

        elif request.domain == DecisionDomain.WORKING_CAPITAL_RISK:
            metric = str(state.get("metric", "")).upper()
            val = float(Decimal(str(state.get("value", 0))))
            return {"metric": metric, "value": val}

        return state
