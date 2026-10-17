from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DecisionDomain(str, Enum):
    UNDERWRITING = "UNDERWRITING"          # Credit risk tiering, limits, APR suitability
    SECURITY_GATE = "SECURITY_GATE"        # 3-Tier Security Matrix authorization
    INTENT_ROUTING = "INTENT_ROUTING"      # Conversational query classification
    EXPENSE_TRIAGE = "EXPENSE_TRIAGE"      # Bank memo expense categorization (Payroll/Rent/Debt)
    DEFICIT_SEVERITY = "DEFICIT_SEVERITY"  # Runway crunch horizon classification
    WORKING_CAPITAL_RISK = "WORKING_CAPITAL_RISK"  # CCC, WCR, and operational lag benchmarks
    DEBT_AFFORDABILITY = "DEBT_AFFORDABILITY"      # DSCR / FCCR commercial debt covenant tiers
    USURY_COMPLIANCE = "USURY_COMPLIANCE"          # Truth-in-lending APR predatory ceiling
    CONCENTRATION_RISK = "CONCENTRATION_RISK"      # Client revenue concentration & HHI tiers
    UNIT_ECONOMICS = "UNIT_ECONOMICS"              # Margin of safety & operating margin tiers
    REVENUE_VOLATILITY = "REVENUE_VOLATILITY"      # Weekly inflow coefficient of variation tiers
    FACILITY_MATCHING = "FACILITY_MATCHING"        # Pre-qualified financing catalog, pricing & suitability
    AGENT_PERSONA = "AGENT_PERSONA"                # Agent personality directives, system prompts & subagent routing
    BANK_STATEMENT_PROFILE = "BANK_STATEMENT_PROFILE"      # PDF statement column header & format normalization
    RECONCILIATION_TOLERANCE = "RECONCILIATION_TOLERANCE"  # Accounting tie-out proofs & discrepancy classification



class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: DecisionDomain
    input_state: Dict[str, Any]
    candidate_options: List[str] = Field(default_factory=list)
    execution_mode: str = "AUTO"           # "AUTO" | "DETERMINISTIC_ONLY" | "PROBABILISTIC_ONLY"
    fallback_on_low_confidence: bool = True
    confidence_threshold: float = 0.60
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DecisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: DecisionDomain
    selected_choice: str
    confidence_score: float                # 1.0 for deterministic JDM tables; 0.0-1.0 calibrated for models
    engine_id: str                         # e.g., "zen-engine@2.1.3", "system-one@kev-0.8b", "fallback-rules"
    matched_rule_id: Optional[str] = None  # Exact rule ID from JDM table (e.g. "rule_prime", "rule_high_risk")
    matched_rule_description: Optional[str] = None
    adverse_factors: List[str] = Field(default_factory=list)  # ECOA/FCRA adverse action reason codes
    evaluation_duration_us: Optional[int] = None              # Execution latency in microseconds
    rationale: Optional[str] = None
    output_payload: Dict[str, Any] = Field(default_factory=dict)
