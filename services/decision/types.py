from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DecisionDomain(str, Enum):
    UNDERWRITING = "UNDERWRITING"          # Credit risk tiering, limits, APR suitability
    SECURITY_GATE = "SECURITY_GATE"        # 3-Tier Security Matrix authorization
    INTENT_ROUTING = "INTENT_ROUTING"      # Conversational query classification
    EXPENSE_TRIAGE = "EXPENSE_TRIAGE"      # Bank memo expense categorization (Payroll/Rent/Debt)
    DEFICIT_SEVERITY = "DEFICIT_SEVERITY"  # Runway crunch horizon classification


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    domain: DecisionDomain
    input_state: Dict[str, Any]
    candidate_options: List[str] = Field(default_factory=list)
    execution_mode: str = "AUTO"           # "AUTO" | "DETERMINISTIC_ONLY" | "PROBABILISTIC_ONLY"
    fallback_on_low_confidence: bool = True
    confidence_threshold: float = 0.60
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DecisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    domain: DecisionDomain
    selected_choice: str
    confidence_score: float                # 1.0 for deterministic JDM tables; 0.0-1.0 calibrated for models
    engine_id: str                         # e.g., "zen-engine@2.1.3", "system-one@kev-0.8b", "fallback-rules"
    rationale: Optional[str] = None
    output_payload: Dict[str, Any] = Field(default_factory=dict)
