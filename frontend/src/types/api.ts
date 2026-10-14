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
  period_days: number;
  average_daily_burn: string;
  runway_days: number | null;
  alert_threshold_days: number;
  cash_status: CashStatus;
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
