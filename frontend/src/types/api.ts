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
