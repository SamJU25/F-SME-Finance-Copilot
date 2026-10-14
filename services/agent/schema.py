"""Pydantic schemas for the Autonomous AI Copilot Agent."""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class AgentChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., description="User chat query or instruction")
    tenant_id: str = Field(default="SME-DEFAULT", description="SME tenant identifier")
    csv_content: Optional[str] = Field(default=None, description="Raw CSV bank statement string for contextual analysis")
    alert_threshold_days: int = Field(default=30, gt=0, description="Runway alert threshold in days")
    nsf_count: int = Field(default=0, ge=0, description="Observed non-sufficient funds counter")
    staged_action_type: Optional[str] = Field(default=None, description="Explicit financial action to stage (e.g. DRAW_CREDIT_LINE)")
    staged_amount_cents: Optional[int] = Field(default=None, gt=0, description="Action amount in cents")
    staged_target: Optional[str] = Field(default=None, description="Action recipient or lender name")


class AgentMetricsSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_balance: Optional[str] = None
    net_period_change: Optional[str] = None
    average_daily_burn: Optional[str] = None
    runway_days: Optional[int] = None
    cash_status: Optional[str] = None
    daily_average_balance: Optional[str] = None
    risk_tier: Optional[str] = None
    max_qualified_limit: Optional[str] = None


class AgentMatchedOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    product_type: str
    facility_name: str
    max_amount: str
    term_days: int
    apr_percent: str
    is_predatory: bool
    suitability_score: int
    requires_tier_3_hitl: bool


class AgentActionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_id: str
    action_type: str
    amount_cents: int
    target_identifier: str
    status: str
    biometric_required: bool = True


class CopilotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reply: str
    intent_detected: str
    metrics: Optional[AgentMetricsSummary] = None
    matched_options: List[AgentMatchedOption] = Field(default_factory=list)
    staged_action: Optional[AgentActionProposal] = None
    requires_biometric_hitl: bool = False
