"""Dynamic multi-statement treasury consolidator and portfolio intelligence engine.

Handles:
1. Dynamic Account Fingerprinting (Sequential timeline vs Multi-account portfolio).
2. Content-hash deduplication across overlapping export ranges.
3. Contra-Transfer Elimination (identifies internal sweeps/wires to prevent revenue & burn inflation).
4. Calendar gap and statement discontinuity detection.
5. Consolidated treasury liquidity aggregation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Sequence

from services.ingestion.csv_parser import DemoTransaction, IngestionResult, RejectedRow


@dataclass(frozen=True)
class ContraTransferPair:
    outflow_tx_id: str
    inflow_tx_id: str
    amount: Decimal
    outflow_account: str
    inflow_account: str
    transfer_date: date


@dataclass(frozen=True)
class AccountStatementProfile:
    file_name: str
    account_id: str
    start_date: date
    end_date: date
    opening_balance: Decimal
    closing_balance: Decimal
    transaction_count: int
    currency: str


@dataclass(frozen=True)
class ConsolidatedTreasuryResult:
    currency: str
    accounts: list[AccountStatementProfile]
    accepted_rows: list[DemoTransaction]
    rejected_rows: list[RejectedRow]
    consolidated_balance: Decimal
    total_gross_inflows: Decimal
    total_gross_outflows: Decimal
    operational_inflows: Decimal
    operational_outflows: Decimal
    internal_transfers: list[ContraTransferPair]
    internal_transfer_volume: Decimal
    calendar_gaps: list[str]
    has_overlaps_deduped: bool


_TRANSFER_KEYWORDS = {
    "transfer", "wire", "internal", "sweep", "xfer", "trsf", "ach", "payroll",
    "deposit", "checking", "savings", "to", "from", "contra", "fund", "funding",
}


def consolidate_multi_statement_treasury(
    file_results: Sequence[tuple[str, IngestionResult]],
) -> ConsolidatedTreasuryResult:
    """Intelligently consolidates multiple statements into a unified treasury view."""
    if not file_results:
        raise ValueError("No statement results provided to consolidate.")

    # 1. Profile each file
    profiles: list[AccountStatementProfile] = []
    account_clusters: list[list[int]] = []  # indices of files in same account

    for idx, (filename, res) in enumerate(file_results):
        txs = res.accepted_rows
        if txs:
            s_date = min(t.posted_on for t in txs)
            e_date = max(t.posted_on for t in txs)
            op_bal = txs[0].closing_balance - txs[0].amount
            cl_bal = txs[-1].closing_balance
        else:
            s_date = date.today()
            e_date = date.today()
            op_bal = Decimal("0.00")
            cl_bal = Decimal("0.00")

        acc_id = f"Account_{idx + 1}"
        profiles.append(
            AccountStatementProfile(
                file_name=filename,
                account_id=acc_id,
                start_date=s_date,
                end_date=e_date,
                opening_balance=op_bal,
                closing_balance=cl_bal,
                transaction_count=len(txs),
                currency=res.currency,
            )
        )

    # 2. Account Fingerprinting: cluster files that belong to the same account
    # Condition A: File B's opening balance equals File A's closing balance (balance tie-out)
    # Condition B: High overlap of identical transactions
    assigned: set[int] = set()
    for i in range(len(file_results)):
        if i in assigned:
            continue
        cluster = [i]
        assigned.add(i)

        for j in range(len(file_results)):
            if j in assigned:
                continue

            prof_i = profiles[i]
            prof_j = profiles[j]

            # Balance tie-out check (consecutive periods of same account)
            tie_out_forward = (
                prof_j.start_date >= prof_i.end_date
                and abs(prof_j.opening_balance - prof_i.closing_balance) < Decimal("0.01")
            )
            tie_out_backward = (
                prof_i.start_date >= prof_j.end_date
                and abs(prof_i.opening_balance - prof_j.closing_balance) < Decimal("0.01")
            )

            # Transaction overlap check (duplicate export of same account)
            txs_i = file_results[i][1].accepted_rows
            txs_j = file_results[j][1].accepted_rows
            keys_i = {(t.posted_on, t.amount) for t in txs_i}
            keys_j = {(t.posted_on, t.amount) for t in txs_j}
            overlap_count = len(keys_i & keys_j)
            is_duplicate_export = (
                overlap_count >= 2
                and overlap_count >= min(len(keys_i), len(keys_j)) * 0.50
            )

            if tie_out_forward or tie_out_backward or is_duplicate_export:
                cluster.append(j)
                assigned.add(j)

        account_clusters.append(cluster)

    # Re-label account IDs according to clusters
    updated_profiles: list[AccountStatementProfile] = []
    file_to_account: dict[int, str] = {}
    for cluster_idx, cluster in enumerate(account_clusters, start=1):
        acc_label = f"Account_{cluster_idx}"
        for f_idx in cluster:
            file_to_account[f_idx] = acc_label
            p = profiles[f_idx]
            updated_profiles.append(
                AccountStatementProfile(
                    file_name=p.file_name,
                    account_id=acc_label,
                    start_date=p.start_date,
                    end_date=p.end_date,
                    opening_balance=p.opening_balance,
                    closing_balance=p.closing_balance,
                    transaction_count=p.transaction_count,
                    currency=p.currency,
                )
            )

    # 3. Detect Calendar Gaps in same-account sequential files
    calendar_gaps: list[str] = []
    for cluster in account_clusters:
        if len(cluster) >= 2:
            sorted_by_date = sorted(cluster, key=lambda idx: profiles[idx].start_date)
            for k in range(len(sorted_by_date) - 1):
                cur_end = profiles[sorted_by_date[k]].end_date
                nxt_start = profiles[sorted_by_date[k + 1]].start_date
                gap_days = (nxt_start - cur_end).days - 1
                if gap_days > 3:
                    calendar_gaps.append(
                        f"Calendar gap of {gap_days} unrecorded days between {cur_end} and {nxt_start} in {file_to_account[sorted_by_date[k]]}."
                    )

    # 4. Deduplicate transactions & track provenance
    has_overlaps_deduped = False
    all_accepted: list[DemoTransaction] = []
    all_rejected: list[RejectedRow] = []
    seen_tx_keys: set[tuple[str, date, Decimal, str]] = set()
    tx_to_account: dict[str, str] = {}

    for f_idx, (filename, res) in enumerate(file_results):
        acc_name = file_to_account[f_idx]
        all_rejected.extend(res.rejected_rows)

        for tx in res.accepted_rows:
            dedup_key = (acc_name, tx.posted_on, tx.amount, tx.description.strip().lower())
            if dedup_key in seen_tx_keys:
                has_overlaps_deduped = True
                continue
            seen_tx_keys.add(dedup_key)
            all_accepted.append(tx)
            tx_to_account[tx.transaction_id] = acc_name

    # 5. Detect and Eliminate Contra-Transfers (Internal Sweeps)
    # Match pairs of transactions across DIFFERENT accounts where:
    # 1. abs(date_A - date_B) <= 1 day
    # 2. amount_A + amount_B == 0
    # 3. Transfer keywords or symmetric amount matching
    contra_pairs: list[ContraTransferPair] = []
    matched_tx_ids: set[str] = set()

    outflows = [t for t in all_accepted if t.amount < 0]
    inflows = [t for t in all_accepted if t.amount > 0]

    for out_tx in outflows:
        if out_tx.transaction_id in matched_tx_ids:
            continue
        out_acc = tx_to_account.get(out_tx.transaction_id, "")

        for in_tx in inflows:
            if in_tx.transaction_id in matched_tx_ids:
                continue
            in_acc = tx_to_account.get(in_tx.transaction_id, "")
            if out_acc == in_acc:
                # Must be across different accounts
                continue

            # Amount match
            if abs(out_tx.amount + in_tx.amount) == Decimal("0.00"):
                # Date match (+/- 1 day)
                delta_days = abs((out_tx.posted_on - in_tx.posted_on).days)
                if delta_days <= 1:
                    # Semantic confirmation: transfer keywords or equal amounts
                    contra_pairs.append(
                        ContraTransferPair(
                            outflow_tx_id=out_tx.transaction_id,
                            inflow_tx_id=in_tx.transaction_id,
                            amount=in_tx.amount,
                            outflow_account=out_acc,
                            inflow_account=in_acc,
                            transfer_date=out_tx.posted_on,
                        )
                    )
                    matched_tx_ids.add(out_tx.transaction_id)
                    matched_tx_ids.add(in_tx.transaction_id)
                    break

    internal_volume = sum(p.amount for p in contra_pairs)

    # 6. Compute Consolidated Treasury Balances
    is_multi_account = len(account_clusters) > 1

    if is_multi_account:
        # Sum the latest closing balance from each unique account cluster
        consolidated_balance = Decimal("0.00")
        for cluster in account_clusters:
            # Sort cluster files by end_date
            latest_file_idx = max(cluster, key=lambda idx: profiles[idx].end_date)
            consolidated_balance += profiles[latest_file_idx].closing_balance

        # Calculate chronological running balances across all merged transactions
        all_accepted.sort(key=lambda t: (t.posted_on, t.row_number))
        total_net = sum(t.amount for t in all_accepted)
        starting_treasury = consolidated_balance - total_net

        running_bal = starting_treasury
        recomputed = []
        for idx, t in enumerate(all_accepted, start=1):
            running_bal += t.amount
            recomputed.append(
                DemoTransaction(
                    row_number=idx,
                    transaction_id=t.transaction_id,
                    posted_on=t.posted_on,
                    amount=t.amount,
                    currency=t.currency,
                    description=t.description,
                    closing_balance=running_bal,
                )
            )
        all_accepted = recomputed
    else:
        # Sequential statements for same account
        all_accepted.sort(key=lambda t: (t.posted_on, t.row_number))
        consolidated_balance = all_accepted[-1].closing_balance if all_accepted else Decimal("0.00")
        reindexed = []
        for idx, t in enumerate(all_accepted, start=1):
            reindexed.append(
                DemoTransaction(
                    row_number=idx,
                    transaction_id=t.transaction_id,
                    posted_on=t.posted_on,
                    amount=t.amount,
                    currency=t.currency,
                    description=t.description,
                    closing_balance=t.closing_balance,
                )
            )
        all_accepted = reindexed

    # 7. Compute Gross vs Operational (Contra-Eliminated) Cash Flows
    total_inflows = sum(t.amount for t in all_accepted if t.amount > 0)
    total_outflows = abs(sum(t.amount for t in all_accepted if t.amount < 0))

    # Operational flows subtract internal contra transfers
    op_inflows = max(Decimal("0.00"), total_inflows - internal_volume)
    op_outflows = max(Decimal("0.00"), total_outflows - internal_volume)

    currency = file_results[0][1].currency

    return ConsolidatedTreasuryResult(
        currency=currency,
        accounts=updated_profiles,
        accepted_rows=all_accepted,
        rejected_rows=all_rejected,
        consolidated_balance=consolidated_balance,
        total_gross_inflows=total_inflows,
        total_gross_outflows=total_outflows,
        operational_inflows=op_inflows,
        operational_outflows=op_outflows,
        internal_transfers=contra_pairs,
        internal_transfer_volume=internal_volume,
        calendar_gaps=calendar_gaps,
        has_overlaps_deduped=has_overlaps_deduped,
    )
