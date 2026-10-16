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
            DecisionDomain.DEBT_AFFORDABILITY,
            DecisionDomain.USURY_COMPLIANCE,
            DecisionDomain.CONCENTRATION_RISK,
            DecisionDomain.UNIT_ECONOMICS,
            DecisionDomain.REVENUE_VOLATILITY,
        ]

    def _get_domain_file_map(self) -> Dict[DecisionDomain, str]:
        return {
            DecisionDomain.UNDERWRITING: "underwriting_policy.json",
            DecisionDomain.SECURITY_GATE: "security_gate_policy.json",
            DecisionDomain.DEFICIT_SEVERITY: "deficit_severity_policy.json",
            DecisionDomain.WORKING_CAPITAL_RISK: "working_capital_policy.json",
            DecisionDomain.DEBT_AFFORDABILITY: "debt_covenant_policy.json",
            DecisionDomain.USURY_COMPLIANCE: "usury_policy.json",
            DecisionDomain.CONCENTRATION_RISK: "concentration_policy.json",
            DecisionDomain.UNIT_ECONOMICS: "unit_economics_policy.json",
            DecisionDomain.REVENUE_VOLATILITY: "revenue_volatility_policy.json",
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
            if request.input_state.get("eval_horizon_confidence"):
                target_days = int(ctx.get("target_horizon_days", 30))
                if target_days > 365:
                    selected_choice = "INDICATIVE"
                    horizon_capped = True
                    effective_target_days = 365
                    advisory = (
                        f"Requested horizon of {target_days} days was capped at 365 days (1 year). "
                        "Transactional daily burn extrapolation loses statistical validity beyond 12 months; "
                        "multi-year planning requires an indirect 3-statement corporate budget model."
                    )
                elif target_days > 90:
                    selected_choice = "INDICATIVE"
                    horizon_capped = False
                    effective_target_days = target_days
                    advisory = (
                        f"{target_days}-day forecast reflects an indicative linear trend. "
                        "Corporate treasury models recommend 13-week (90-day) reviews to adjust for payable drifts."
                    )
                else:
                    selected_choice = "HIGH"
                    horizon_capped = False
                    effective_target_days = target_days
                    advisory = None
                result_dict = {
                    "confidence_tier": selected_choice,
                    "horizon_capped": horizon_capped,
                    "effective_target_days": effective_target_days,
                    "advisory_note": advisory,
                }
                rationale = advisory or f"Horizon of {target_days} days evaluated as {selected_choice} confidence."
            elif request.input_state.get("eval_cash_status"):
                bal = float(ctx.get("current_balance", 0))
                burn = float(ctx.get("average_daily_burn", 0))
                runway = ctx.get("runway_days")
                thresh = int(ctx.get("alert_threshold_days", 30))
                if bal <= 0:
                    selected_choice = "CASH_NONPOSITIVE"
                elif burn == 0:
                    selected_choice = "NO_BURN"
                elif runway is not None and runway < thresh:
                    selected_choice = "LOW_RUNWAY"
                else:
                    selected_choice = "WATCH"
                rationale = f"Evaluated cash status as {selected_choice} (Balance={bal}, Burn={burn}, Runway={runway}, Threshold={thresh})."
            else:
                selected_choice = result_dict.get("severity", "SAFE")
                rationale = f"Evaluated in {perf} via JDM deficit_severity_policy.json (Rule={matched_rule_id}, Days={ctx.get('days_until_deficit')})."
        elif request.domain == DecisionDomain.WORKING_CAPITAL_RISK:
            selected_choice = result_dict.get("status", "BALANCED")
            rationale = f"Evaluated in {perf} via JDM working_capital_policy.json (Rule={matched_rule_id}, Metric={ctx.get('metric')}, Value={ctx.get('value')})."
        elif request.domain == DecisionDomain.DEBT_AFFORDABILITY:
            selected_choice = result_dict.get("status", "STANDARD")
            raw_rat = result_dict.get("rationale", "")
            if "{ratio}" in raw_rat:
                raw_rat = raw_rat.replace("{ratio}", str(ctx.get("ratio", 0)))
            rationale = raw_rat or f"Evaluated in {perf} via JDM debt_covenant_policy.json (Rule={matched_rule_id}, Metric={ctx.get('metric')}, Ratio={ctx.get('ratio')})."
        elif request.domain == DecisionDomain.USURY_COMPLIANCE:
            is_pred = result_dict.get("is_predatory", False)
            selected_choice = "PREDATORY" if is_pred else "COMPLIANT"
            rationale = result_dict.get("rationale") or f"Evaluated in {perf} via JDM usury_policy.json (Rule={matched_rule_id}, APR={ctx.get('apr')}%)."
        elif request.domain == DecisionDomain.CONCENTRATION_RISK:
            if request.input_state.get("eval_churn"):
                burn_val = float(ctx.get("projected_annual_burn", 0))
                share_val = float(ctx.get("lost_share", 0))
                if burn_val > 0.0 or share_val >= 25.0:
                    selected_choice = "CRITICAL"
                    rec = (
                        f"Loss of client creates an immediate annual operating deficit of ${burn_val:,.2f} "
                        f"({share_val}% revenue loss). Secure bridge working capital or cut overhead immediately."
                    )
                elif share_val >= 15.0:
                    selected_choice = "ELEVATED"
                    rec = (
                        f"Loss represents {share_val}% of annual revenue. Operating cash flow tightens; "
                        f"diversify pipeline to replace customer volume."
                    )
                else:
                    selected_choice = "MODERATE"
                    rec = (
                        f"Loss represents {share_val}% of annual revenue. Operating margin absorbs the variance, "
                        f"maintain active pipeline."
                    )
                result_dict = {"severity": selected_choice, "recommendation": rec}
                rationale = rec
            else:
                selected_choice = result_dict.get("tier", "DIVERSIFIED")
                raw_assess = result_dict.get("assessment", "")
                if "{top_1}" in raw_assess or "{hhi}" in raw_assess or "{top_3}" in raw_assess:
                    top_1_val = request.input_state.get("top_1_pct", ctx.get("top_1_pct", 0))
                    top_3_val = request.input_state.get("top_3_pct", "")
                    hhi_val = request.input_state.get("hhi", ctx.get("hhi", 0))
                    raw_assess = raw_assess.replace("{top_1}", str(top_1_val)).replace("{top_3}", str(top_3_val)).replace("{hhi}", str(hhi_val))
                rationale = raw_assess or f"Evaluated in {perf} via JDM concentration_policy.json (Rule={matched_rule_id}, Top1={ctx.get('top_1_pct')}%, HHI={ctx.get('hhi')})."

        elif request.domain == DecisionDomain.UNIT_ECONOMICS:
            selected_choice = result_dict.get("tier", result_dict.get("status", "MODERATE"))
            result_dict["tier"] = selected_choice
            result_dict["is_safe"] = result_dict.get("is_healthy", True)
            rationale = result_dict.get("rationale") or f"Evaluated in {perf} via JDM unit_economics_policy.json (Rule={matched_rule_id}, Metric={ctx.get('metric')}, Value={ctx.get('value')}%)."
        elif request.domain == DecisionDomain.REVENUE_VOLATILITY:
            selected_choice = result_dict.get("tier", "LOW")
            result_dict["volatility_tier"] = selected_choice
            rationale = result_dict.get("description") or f"Evaluated in {perf} via JDM revenue_volatility_policy.json (Rule={matched_rule_id}, CV={ctx.get('cv')})."

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
            if state.get("eval_horizon_confidence"):
                return {
                    "eval_horizon_confidence": True,
                    "target_horizon_days": int(state.get("target_horizon_days", 30)),
                }
            if state.get("eval_cash_status"):
                return {
                    "eval_cash_status": True,
                    "current_balance": float(Decimal(str(state.get("current_balance", 0)))),
                    "average_daily_burn": float(Decimal(str(state.get("average_daily_burn", 0)))),
                    "runway_days": state.get("runway_days"),
                    "alert_threshold_days": int(state.get("alert_threshold_days", 30)),
                }
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

        elif request.domain == DecisionDomain.DEBT_AFFORDABILITY:
            metric = str(state.get("metric", "DSCR")).upper()
            ratio = float(Decimal(str(state.get("ratio", 0))))
            return {"metric": metric, "ratio": ratio}

        elif request.domain == DecisionDomain.USURY_COMPLIANCE:
            apr = float(Decimal(str(state.get("apr", 0))))
            product = str(state.get("product_type", ""))
            return {"apr": apr, "product_type": product}

        elif request.domain == DecisionDomain.CONCENTRATION_RISK:
            if state.get("eval_churn"):
                return {
                    "eval_churn": True,
                    "lost_share": float(Decimal(str(state.get("lost_share", 0)))),
                    "projected_annual_burn": float(Decimal(str(state.get("projected_annual_burn", 0)))),
                }
            top1 = float(Decimal(str(state.get("top_1_pct", 0))))
            hhi = float(Decimal(str(state.get("hhi", 0))))
            return {"top_1_pct": top1, "hhi": hhi}


        elif request.domain == DecisionDomain.UNIT_ECONOMICS:
            metric = str(state.get("metric", "")).upper()
            if metric in ("MARGIN_OF_SAFETY", "MOS"):
                metric = "MOS_PERCENT"
            elif metric in ("OPERATING_MARGIN", "OP_MARGIN"):
                metric = "OPERATING_MARGIN_PERCENT"
            val = float(Decimal(str(state.get("value", 0))))
            if metric in ("MOS_PERCENT", "OPERATING_MARGIN_PERCENT") and -1.0 <= val <= 1.0 and val != 0.0:
                val = val * 100.0
            return {"metric": metric, "value": val}


        elif request.domain == DecisionDomain.REVENUE_VOLATILITY:
            cv = float(Decimal(str(state.get("cv", 0))))
            return {"cv": cv}

        return state
