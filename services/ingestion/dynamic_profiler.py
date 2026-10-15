"""Statistical and mathematical content-based column profiler for universal financial tables.

Analyzes cell content directly without relying on static column name lists:
1. Date detection: measures parse success rate across formats.
2. Decimal detection: measures numeric financial parse rate.
3. Mathematical Balance Invariant Verification:
   B[i+1] - B[i] == A[i+1]  (chronological)
   B[i] - B[i+1] == A[i]    (reverse chronological)
   Proves which column is Net Amount and which is Running Balance with mathematical certainty.
4. Debit / Credit / Balance Invariant Verification:
   B[i+1] - B[i] == Credit[i+1] - Debit[i+1]
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from services.ingestion.financial_parsers import _parse_universal_amount, _parse_universal_date


@dataclass(frozen=True)
class ProfiledSchema:
    date_col: int
    amount_col: int | None
    debit_col: int | None
    credit_col: int | None
    balance_col: int | None
    description_col: int | None
    currency_col: int | None
    tx_id_col: int | None = None
    confidence: float = 1.0
    detection_method: str = "mathematical_balance_proof"
    is_reverse_chronological: bool = False


def profile_table_content(sample_rows: Sequence[Sequence[str]]) -> ProfiledSchema | None:
    """Profiles actual cell values to discover semantic financial column roles."""
    if not sample_rows:
        return None

    # Filter out empty rows
    valid_rows = [r for r in sample_rows if r and any(cell.strip() for cell in r)]
    if len(valid_rows) < 2:
        return None

    # Determine standard column width
    col_counts = [len(r) for r in valid_rows]
    target_width = max(set(col_counts), key=col_counts.count)
    standard_rows = [r for r in valid_rows if len(r) >= target_width][:25]
    if len(standard_rows) < 2:
        return None

    # 1. Profile each column
    date_scores: dict[int, float] = {}
    numeric_data: dict[int, list[tuple[int, Decimal]]] = {}
    text_scores: dict[int, float] = {}
    currency_cols: list[int] = []

    for col_idx in range(target_width):
        col_cells = [row[col_idx].strip() for row in standard_rows]
        non_empty = [c for c in col_cells if c]
        if not non_empty:
            continue

        # Check for currency ISO code column
        if all(re.fullmatch(r"[A-Z]{3}", c) for c in non_empty):
            currency_cols.append(col_idx)
            continue

        # Date parsing evaluation
        date_success = 0
        for cell in non_empty:
            try:
                _parse_universal_date(cell)
                date_success += 1
            except Exception:
                pass
        date_rate = date_success / len(non_empty)
        if date_rate >= 0.60:
            date_scores[col_idx] = date_rate

        # Numeric parsing evaluation
        parsed_numbers: list[tuple[int, Decimal]] = []
        for row_idx, row in enumerate(standard_rows):
            cell = row[col_idx].strip()
            if cell:
                try:
                    num, _ = _parse_universal_amount(cell)
                    parsed_numbers.append((row_idx, num))
                except Exception:
                    pass
        if len(parsed_numbers) >= len(non_empty) * 0.70:
            numeric_data[col_idx] = parsed_numbers

        # Text evaluation (alnum words, length)
        text_count = sum(1 for c in non_empty if re.search(r"[a-zA-Z]{2,}", c))
        text_scores[col_idx] = text_count / len(non_empty)

    # 2. Select Date Column
    if not date_scores:
        return None
    date_col = max(date_scores, key=date_scores.get)

    # 3. Test Mathematical Balance Invariant
    # If pairs of numeric columns satisfy B[i+1] - B[i] == A[i+1], they are mathematically proven
    numeric_cols = sorted(numeric_data.keys())
    if date_col in numeric_cols:
        numeric_cols.remove(date_col)

    # 3A. Test 2-Column (Amount, Balance) Invariant
    for col_a in numeric_cols:
        for col_b in numeric_cols:
            if col_a == col_b:
                continue

            dict_a = dict(numeric_data[col_a])
            dict_b = dict(numeric_data[col_b])
            common_rows = sorted(set(dict_a.keys()) & set(dict_b.keys()))
            if len(common_rows) < 2:
                continue

            # Forward chronological check: B[i+1] - B[i] == A[i+1]
            forward_matches = 0
            forward_checks = 0
            for i in range(len(common_rows) - 1):
                r1 = common_rows[i]
                r2 = common_rows[i + 1]
                delta_b = dict_b[r2] - dict_b[r1]
                amt_a = dict_a[r2]
                if abs(delta_b - amt_a) < Decimal("0.005"):
                    forward_matches += 1
                forward_checks += 1

            if forward_checks >= 1 and forward_matches == forward_checks:
                desc_col = _find_best_text_col(text_scores, exclude={date_col, col_a, col_b})
                curr_col = currency_cols[0] if currency_cols else None
                tx_id = _find_best_tx_id_col(standard_rows, exclude={date_col, col_a, col_b, desc_col or -1})
                return ProfiledSchema(
                    date_col=date_col,
                    amount_col=col_a,
                    debit_col=None,
                    credit_col=None,
                    balance_col=col_b,
                    description_col=desc_col,
                    currency_col=curr_col,
                    tx_id_col=tx_id,
                    confidence=1.0,
                    detection_method="mathematical_balance_proof",
                    is_reverse_chronological=False,
                )

            # Reverse chronological check: B[i] - B[i+1] == A[i]
            reverse_matches = 0
            reverse_checks = 0
            for i in range(len(common_rows) - 1):
                r1 = common_rows[i]
                r2 = common_rows[i + 1]
                delta_b = dict_b[r1] - dict_b[r2]
                amt_a = dict_a[r1]
                if abs(delta_b - amt_a) < Decimal("0.005"):
                    reverse_matches += 1
                reverse_checks += 1

            if reverse_checks >= 1 and reverse_matches == reverse_checks:
                desc_col = _find_best_text_col(text_scores, exclude={date_col, col_a, col_b})
                curr_col = currency_cols[0] if currency_cols else None
                tx_id = _find_best_tx_id_col(standard_rows, exclude={date_col, col_a, col_b, desc_col or -1})
                return ProfiledSchema(
                    date_col=date_col,
                    amount_col=col_a,
                    debit_col=None,
                    credit_col=None,
                    balance_col=col_b,
                    description_col=desc_col,
                    currency_col=curr_col,
                    tx_id_col=tx_id,
                    confidence=1.0,
                    detection_method="mathematical_balance_proof",
                    is_reverse_chronological=True,
                )

    # 3B. Test 3-Column (Debit, Credit, Balance) Invariant
    # B[i+1] - B[i] == Credit[i+1] - Debit[i+1]
    if len(numeric_cols) >= 3:
        for col_bal in numeric_cols:
            other_nums = [c for c in numeric_cols if c != col_bal]
            for col_deb in other_nums:
                for col_cred in other_nums:
                    if col_deb == col_cred:
                        continue
                    dict_b = dict(numeric_data[col_bal])
                    dict_d = dict(numeric_data[col_deb])
                    dict_c = dict(numeric_data[col_cred])
                    all_rows = sorted(set(dict_b.keys()))
                    if len(all_rows) < 2:
                        continue

                    matches = 0
                    checks = 0
                    for i in range(len(all_rows) - 1):
                        r1 = all_rows[i]
                        r2 = all_rows[i + 1]
                        delta_b = dict_b[r2] - dict_b[r1]
                        c_val = dict_c.get(r2, Decimal("0.00"))
                        d_val = dict_d.get(r2, Decimal("0.00"))
                        net = c_val - abs(d_val)
                        if abs(delta_b - net) < Decimal("0.005"):
                            matches += 1
                        checks += 1

                    if checks >= 1 and matches == checks:
                        desc_col = _find_best_text_col(text_scores, exclude={date_col, col_bal, col_deb, col_cred})
                        curr_col = currency_cols[0] if currency_cols else None
                        tx_id = _find_best_tx_id_col(standard_rows, exclude={date_col, col_bal, col_deb, col_cred, desc_col or -1})
                        return ProfiledSchema(
                            date_col=date_col,
                            amount_col=None,
                            debit_col=col_deb,
                            credit_col=col_cred,
                            balance_col=col_bal,
                            description_col=desc_col,
                            currency_col=curr_col,
                            tx_id_col=tx_id,
                            confidence=1.0,
                            detection_method="mathematical_debit_credit_balance_proof",
                        )

    # 4. Single Numeric Column fallback (e.g. founder 3-col format: Date, Description, Amount)
    if len(numeric_cols) == 1:
        amount_col = numeric_cols[0]
        desc_col = _find_best_text_col(text_scores, exclude={date_col, amount_col})
        curr_col = currency_cols[0] if currency_cols else None
        tx_id = _find_best_tx_id_col(standard_rows, exclude={date_col, amount_col, desc_col or -1})
        return ProfiledSchema(
            date_col=date_col,
            amount_col=amount_col,
            debit_col=None,
            credit_col=None,
            balance_col=None,
            description_col=desc_col,
            currency_col=curr_col,
            tx_id_col=tx_id,
            confidence=0.90,
            detection_method="single_numeric_column_profile",
        )

    # If multiple numeric columns exist without balance proof, statistical confidence is low
    return None


def _find_best_text_col(text_scores: dict[int, float], exclude: set[int]) -> int | None:
    candidates = {k: v for k, v in text_scores.items() if k not in exclude and v >= 0.30}
    if not candidates:
        return None
    return max(candidates, key=candidates.get)


def _find_best_tx_id_col(rows: Sequence[Sequence[str]], exclude: set[int]) -> int | None:
    if not rows:
        return None
    target_width = len(rows[0])
    for col_idx in range(target_width):
        if col_idx in exclude:
            continue
        vals = [r[col_idx].strip() for r in rows if len(r) > col_idx and r[col_idx].strip()]
        if len(vals) >= 2 and len(set(vals)) == len(vals):
            if all(1 <= len(v) <= 40 and " " not in v for v in vals):
                return col_idx
    return None
