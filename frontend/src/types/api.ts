// Types for the first-demo POST /api/v1/analyze contract.
export type CashStatus = 'CASH_NONPOSITIVE' | 'LOW_RUNWAY' | 'WATCH' | 'NO_BURN';

export interface RejectedRow {
  row_number: number;
  reason_code: string;
}

export interface CashAnalysisResponse {
  currency: string;
  accepted_count: number;
  rejected_rows: RejectedRow[];
  current_balance: string;
  net_period_change: string;
  gross_inflows?: string;
  gross_outflows?: string;
  period_days: number;
  average_daily_burn: string;
  runway_days: number | null;
  alert_threshold_days: number;
  cash_status: CashStatus;
  cash_conversion_cycle_days?: number | null;
  working_capital_status?: 'WORKING_CAPITAL_TRAP' | 'BALANCED' | 'CASH_GENERATIVE' | null;
  working_capital_rationale?: string | null;
}

// Three-Tier Security Gate & Staged Action Intents
export type ActionType = 'FACTOR_INVOICE' | 'DRAW_CREDIT_LINE' | 'TRANSFER' | 'PLEDGE_INVOICE';
export type ActionStatus = 'STAGED_PENDING_HITL' | 'EXECUTED' | 'REJECTED';

export interface StagedActionIntent {
  id: string;
  tenant_id: string;
  action_type: ActionType;
  amount_cents: number;
  target_identifier: string;
  status: ActionStatus;
  staged_at: string;
  biometric_signature: string | null;
}

export interface StagingRequest {
  tenant_id: string;
  action_type: ActionType;
  amount_cents: number;
  target_identifier: string;
}

export interface ExecutionRequest {
  biometric_signature?: string;
}

// Digital Transactional Underwriting & Financing Matcher
export type RiskTier = 'PRIME' | 'NEAR_PRIME' | 'HIGH_RISK';
export type ProductType = 'WORKING_CAPITAL_LINE' | 'INVOICE_FACTORING' | 'REVENUE_BASED_FINANCING';

export interface UnderwritingDossier {
  currency: string;
  daily_average_balance: string;
  transaction_count: number;
  nsf_count: number;
  risk_tier: RiskTier;
  max_qualified_limit: string;
  recommended_product_types: ProductType[];
  revenue_volatility_cv?: string | null;
  volatility_tier?: 'LOW' | 'MODERATE' | 'HIGH' | null;
}

export interface FinancingOption {
  provider: string;
  product_type: ProductType;
  facility_name: string;
  max_amount: string;
  term_days: number;
  apr_percent: string;
  is_predatory: boolean;
  suitability_score: number;
  requires_tier_3_hitl: boolean;
}

export interface UnderwriteApiResponse {
  dossier: UnderwritingDossier;
  matched_options: FinancingOption[];
}

// Autonomous Agent Copilot Chat Types
export interface AgentMetricsSummary {
  current_balance?: string;
  net_period_change?: string;
  gross_inflows?: string;
  gross_outflows?: string;
  average_daily_burn?: string;
  runway_days?: number | null;
  cash_status?: string;
  daily_average_balance?: string;
  risk_tier?: string;
  max_qualified_limit?: string;
  has_projected_deficit?: boolean;
  deficit_severity?: string;
  days_until_deficit?: number | null;
  projected_deficit_date?: string | null;
  projected_shortfall_amount?: string;
  recommended_bridge_amount?: string;
  target_horizon_days?: number | null;
  target_horizon_date?: string | null;
  forecast_target_balance?: string | null;
  confidence_tier?: 'HIGH' | 'INDICATIVE' | null;
  horizon_capped?: boolean | null;
  advisory_note?: string | null;
  detected_recurring_rent?: string | null;
  detected_recurring_debt?: string | null;
  primary_deficit_trigger?: string | null;
  revenue_volatility_cv?: string | null;
  volatility_tier?: 'LOW' | 'MODERATE' | 'HIGH' | null;
  cash_conversion_cycle_days?: number | null;
  working_capital_status?: 'WORKING_CAPITAL_TRAP' | 'BALANCED' | 'CASH_GENERATIVE' | null;
  working_capital_rationale?: string | null;
}


export interface AgentActionProposal {
  intent_id: string;
  action_type: string;
  amount_cents: number;
  target_identifier: string;
  status: string;
  biometric_required: boolean;
}

export interface CopilotResponse {
  reply: string;
  intent_detected: string;
  metrics?: AgentMetricsSummary | null;
  matched_options: FinancingOption[];
  staged_action?: AgentActionProposal | null;
  requires_biometric_hitl: boolean;
}

export type LLMProviderId =
  | 'offline'
  | 'gemini'
  | 'anthropic'
  | 'openai'
  | 'deepseek'
  | 'groq'
  | 'ollama'
  | 'custom';

export interface LLMConfig {
  provider: LLMProviderId;
  api_key?: string;
  base_url?: string;
  model_name?: string;
}

export interface TestConnectionRequest {
  provider: LLMProviderId;
  api_key?: string;
  base_url?: string;
  model_name?: string;
}

export interface TestConnectionResponse {
  success: boolean;
  message: string;
  provider: string;
  model_name?: string;
  latency_ms?: number | null;
}

export interface ModelItem {
  id: string;
  name: string;
}

export interface FetchModelsRequest {
  provider: LLMProviderId;
  api_key?: string;
  base_url?: string;
}

export interface FetchModelsResponse {
  success: boolean;
  provider: string;
  models: ModelItem[];
  message?: string;
}



