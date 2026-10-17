"""Declarative bank statement PDF ingestion and normalization service.

Converts multi-page bank statement PDFs into normalized canonical financial transactions
with deterministic accounting tie-out proofs governed by the Decision Engine.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

import pypdf

from services.decision.registry import DecisionEngineRegistry
from services.decision.types import DecisionDomain, DecisionRequest
from services.ingestion.csv_parser import DemoTransaction, EXPECTED_HEADER
from services.ingestion.financial_parsers import (
    _CURRENCY_SYMBOL_MAP,
    _parse_universal_amount,
    _parse_universal_date,
)
from services.ingestion.pdf_validator import (
    PDFValidationError,
    validate_pdf_statement,
)

# Regex to detect lines starting with standard transaction dates
DATE_LINE_START_REGEX = re.compile(
    r"^\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|[A-Za-z]{3}\s+\d{1,2}(?:,?\s+\d{4})?|\d{1,2}\s+[A-Za-z]{3}(?:,?\s+\d{4})?)\b"
)

# Regex to detect currency and numeric tokens
AMOUNT_TOKEN_REGEX = re.compile(
    r"(?:^|\s)([-+]?\$?\s*\(?\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s*\)?[-+]?(?:\s*CR|\s*DR)?)(?:\s|$)"
)


@dataclass
class PDFStatementResult:
    """Structured result of declarative bank statement PDF parsing."""
    csv_text: str
    transactions: List[DemoTransaction]
    row_count: int
    page_count: int
    currency: str = "USD"
    opening_balance: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    total_inflows: Decimal = Decimal("0.00")
    total_outflows: Decimal = Decimal("0.00")
    net_change: Decimal = Decimal("0.00")
    reconciliation_status: str = "BALANCED"
    reconciliation_breaks: List[Dict[str, Any]] = field(default_factory=list)


class BankPDFParser:
    """Deterministic PDF statement parser governed by declarative JSON decision tables."""

    def __init__(self, registry: Optional[DecisionEngineRegistry] = None) -> None:
        self.registry = registry or DecisionEngineRegistry.get_instance()

    def parse(
        self,
        file_bytes: bytes,
        tenant_id: str = "SME-DEFAULT",
        currency: str = "USD",
    ) -> PDFStatementResult:
        """Parses bank statement PDF into canonical transactions and CSV text."""
        reader = validate_pdf_statement(file_bytes)
        page_count = len(reader.pages)

        # 1. Extract raw line streams across all pages
        raw_lines: List[str] = []
        for p_idx, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            for line in text.splitlines():
                stripped = line.strip()
                if stripped:
                    raw_lines.append(stripped)

        if not raw_lines:
            raise PDFValidationError(
                "NO_TEXT_EXTRACTED",
                "PDF contains no selectable text streams (document may be a flat image or scanned photocopy).",
            )

        # 2. Extract transactions using Date-Boundary State Machine
        parsed_records: List[Dict[str, Any]] = []
        current_record: Optional[Dict[str, Any]] = None

        for line in raw_lines:
            date_match = DATE_LINE_START_REGEX.match(line)
            if date_match:
                # Flush previous record if complete
                if current_record and self._is_record_viable(current_record):
                    parsed_records.append(current_record)

                raw_date_str = date_match.group(1)
                remainder = line[date_match.end():].strip()

                try:
                    parsed_date = _parse_universal_date(raw_date_str)
                except ValueError:
                    # If date parsing fails, treat as continuation line
                    if current_record:
                        current_record["description"] += f" {line}"
                    continue

                # Extract all numeric/amount tokens on this initial line
                matched_pairs = self._extract_amount_candidates(remainder)
                amounts = [p[1] for p in matched_pairs]
                tokens_to_strip = [p[0] for p in matched_pairs]
                desc_text = self._strip_amounts_from_text(remainder, tokens_to_strip)

                current_record = {
                    "date": parsed_date,
                    "description": desc_text,
                    "amount_tokens": amounts,
                    "raw_lines": [line],
                }
            elif current_record:
                # Continuation line: check if it contains missing amount tokens
                extra_pairs = self._extract_amount_candidates(line)
                if extra_pairs:
                    extra_amounts = [p[1] for p in extra_pairs]
                    current_record["amount_tokens"].extend(extra_amounts)
                    tokens_to_strip = [p[0] for p in extra_pairs]
                    clean_line = self._strip_amounts_from_text(line, tokens_to_strip)
                    if clean_line:
                        current_record["description"] += f" {clean_line}"
                else:
                    current_record["description"] += f" {line}"
                current_record["raw_lines"].append(line)

        # Flush final record
        if current_record and self._is_record_viable(current_record):
            parsed_records.append(current_record)

        if not parsed_records:
            raise PDFValidationError(
                "NO_TRANSACTIONS_FOUND",
                "Could not identify structured bank statement transaction rows. "
                "Ensure the statement contains transaction dates and monetary amounts.",
            )

        # 3. Assemble Demarcated DemoTransactions with Accounting Tie-Out Proof
        transactions: List[DemoTransaction] = []
        reconciliation_breaks: List[Dict[str, Any]] = []
        total_inflows = Decimal("0.00")
        total_outflows = Decimal("0.00")

        prev_balance: Optional[Decimal] = None
        opening_balance: Optional[Decimal] = None

        for idx, rec in enumerate(parsed_records):
            post_date = rec["date"]
            desc = self._clean_description(rec["description"])
            amounts = rec["amount_tokens"]

            # Resolve Amount vs Balance
            txn_amount, line_balance = self._resolve_amount_and_balance(amounts, prev_balance)

            # Classify Vendor Category via Decision Engine
            cat_req = DecisionRequest(
                domain=DecisionDomain.EXPENSE_TRIAGE,
                input_state={"memo_clean": desc.lower()},
                execution_mode="DETERMINISTIC_ONLY",
            )
            cat_res = self.registry.evaluate(cat_req)
            category = cat_res.output_payload.get("category", "GENERAL_EXPENSE")

            # Mathematical Balance Tie-Out Proof
            if prev_balance is not None and line_balance is not None:
                expected_balance = prev_balance + txn_amount
                delta = abs(expected_balance - line_balance)
                delta_cents = int(delta * 100)
                is_standard_fee = delta_cents in (1000, 1500, 2000, 2500, 3000, 3500)

                recon_req = DecisionRequest(
                    domain=DecisionDomain.RECONCILIATION_TOLERANCE,
                    input_state={"delta_cents": delta_cents, "inferred_fee_match": is_standard_fee},
                    execution_mode="DETERMINISTIC_ONLY",
                )
                recon_res = self.registry.evaluate(recon_req)
                allow_auto = recon_res.output_payload.get("allow_auto_reconcile", True)

                if not allow_auto:
                    reconciliation_breaks.append({
                        "row_index": idx + 1,
                        "date": str(post_date),
                        "description": desc,
                        "prev_balance": str(prev_balance),
                        "amount": str(txn_amount),
                        "expected_balance": str(expected_balance),
                        "actual_balance": str(line_balance),
                        "delta": str(delta),
                        "severity": recon_res.output_payload.get("severity", "HIGH"),
                    })

            if opening_balance is None and line_balance is not None:
                opening_balance = line_balance - txn_amount

            if txn_amount > 0:
                total_inflows += txn_amount
            else:
                total_outflows += abs(txn_amount)

            if line_balance is not None:
                prev_balance = line_balance

            txn_id = f"TXN-PDF-{post_date.strftime('%Y%m%d')}-{idx + 1:04d}"
            transactions.append(
                DemoTransaction(
                    row_number=idx + 1,
                    transaction_id=txn_id,
                    posted_on=post_date,
                    amount=txn_amount,
                    currency=currency,
                    description=desc,
                    closing_balance=line_balance if line_balance is not None else (prev_balance or Decimal("0.00")),
                )
            )

        # 4. Generate Standard Canonical CSV Text Representation
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(EXPECTED_HEADER)
        for t in transactions:
            writer.writerow([
                t.transaction_id,
                t.posted_on.isoformat(),
                f"{t.amount:.2f}",
                t.currency,
                t.description,
                f"{t.closing_balance:.2f}",
            ])

        overall_status = "RECONCILIATION_BREAK" if reconciliation_breaks else "BALANCED"

        return PDFStatementResult(
            csv_text=csv_buffer.getvalue(),
            transactions=transactions,
            row_count=len(transactions),
            page_count=page_count,
            currency=currency,
            opening_balance=opening_balance,
            closing_balance=prev_balance,
            total_inflows=total_inflows,
            total_outflows=total_outflows,
            net_change=total_inflows - total_outflows,
            reconciliation_status=overall_status,
            reconciliation_breaks=reconciliation_breaks,
        )

    def _is_record_viable(self, record: Dict[str, Any]) -> bool:
        """Determines if extracted line cluster contains minimal transaction elements."""
        return bool(record.get("date") and record.get("amount_tokens"))

    def _extract_amount_candidates(self, text: str) -> List[Tuple[str, Decimal]]:
        """Extracts valid monetary amount tokens from text segment with financial formatting verification."""
        candidates: List[Tuple[str, Decimal]] = []
        tokens = text.split()
        for tok in tokens:
            has_cents = bool(re.search(r'\.\d{2}[-]?(?:CR|DR)?\)?$', tok, re.IGNORECASE))
            has_currency = any(sym in tok for sym in ('$', '€', '£', '¥'))
            has_commas = ',' in tok and bool(re.search(r'\d{1,3},\d{3}', tok))
            has_parens = tok.startswith('(') and tok.endswith(')') and bool(re.search(r'\d', tok))

            if not (has_cents or has_currency or has_commas or has_parens):
                continue

            c = tok.replace('$', '').replace('€', '').replace('£', '').replace(',', '').strip()
            if not c or c in ('-', '+'):
                continue
            try:
                if c.startswith('(') and c.endswith(')'):
                    val = -Decimal(c[1:-1])
                elif c.upper().endswith('CR'):
                    val = Decimal(c[:-2].strip())
                elif c.upper().endswith('DR') or c.endswith('-'):
                    val = -Decimal(c.rstrip('DRdr-').strip())
                else:
                    val = Decimal(c)
                candidates.append((tok, val.quantize(Decimal('0.01'))))
            except (InvalidOperation, ValueError):
                continue
        return candidates

    def _strip_amounts_from_text(self, text: str, matched_tokens: List[str]) -> str:
        """Removes matched amount tokens from text to isolate vendor description."""
        words = text.split()
        filtered = [w for w in words if w not in matched_tokens]
        return " ".join(filtered).strip()

    def _clean_description(self, raw_desc: str) -> str:
        """Sanitizes transaction description and removes extraneous whitespace."""
        s = " ".join(raw_desc.split()).strip()
        # Cap length to 120 chars for database/schema compatibility
        return s[:120] if len(s) > 120 else (s or "Bank Transaction")

    def _resolve_amount_and_balance(
        self,
        amounts: List[Decimal],
        prev_balance: Optional[Decimal],
    ) -> Tuple[Decimal, Optional[Decimal]]:
        """Resolves which numeric token is the transaction flow amount and which is the running balance."""
        if len(amounts) == 1:
            return amounts[0], None

        if len(amounts) == 2:
            # Pattern: [Amount, Balance] or [Balance, Amount]
            amt_0, amt_1 = amounts[0], amounts[1]
            if prev_balance is not None:
                # Test Hypothesis 1: amt_0 is amount, amt_1 is new balance
                if abs((prev_balance + amt_0) - amt_1) <= Decimal("0.05"):
                    return amt_0, amt_1
                if abs((prev_balance - amt_0) - amt_1) <= Decimal("0.05"):
                    return -abs(amt_0), amt_1

                # Test Hypothesis 2: amt_1 is amount, amt_0 is balance
                if abs((prev_balance + amt_1) - amt_0) <= Decimal("0.05"):
                    return amt_1, amt_0
                if abs((prev_balance - amt_1) - amt_0) <= Decimal("0.05"):
                    return -abs(amt_1), amt_0

            # Default heuristic: usually bank statements place Amount first, Balance last
            return amt_0, amt_1

        # 3 or more amounts: typically [Debit, Credit, Balance]
        # In multi-column bank layouts: Debits, Credits, Balance
        return amounts[0], amounts[-1]


def parse_pdf_statement(
    file_bytes: bytes,
    tenant_id: str = "SME-DEFAULT",
    currency: str = "USD",
) -> PDFStatementResult:
    """Convenience functional interface to parse bank statement PDF."""
    parser = BankPDFParser()
    return parser.parse(file_bytes=file_bytes, tenant_id=tenant_id, currency=currency)
