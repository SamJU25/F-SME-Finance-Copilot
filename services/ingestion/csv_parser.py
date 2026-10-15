"""Universal bank statement and financial table data ingestion and sanitization service."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field

from services.agent.schema import LLMConfig
from services.ingestion.dynamic_profiler import ProfiledSchema, profile_table_content
from services.ingestion.financial_parsers import (
    _CURRENCY_SYMBOL_MAP,
    _detect_delimiter,
    _normalize_col_name,
    _parse_universal_amount,
    _parse_universal_date,
)
from services.ingestion.llm_schema_resolver import resolve_schema_with_llm

EXPECTED_HEADER = [
    "transaction_id",
    "posted_on",
    "amount",
    "currency",
    "description",
    "closing_balance",
]


class CSVIngestionError(ValueError):
    """A file-level input error with a stable response code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class NormalizedTransaction(BaseModel):
    """Existing finance-ingestion schema retained for existing callers/tests."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    tenant_id: str
    post_date: date
    amount: Decimal = Field(decimal_places=2)
    counterparty: str = Field(min_length=1, max_length=120)
    category: str
    is_nsf: bool = False


@dataclass(frozen=True)
class DemoTransaction:
    row_number: int
    transaction_id: str
    posted_on: date
    amount: Decimal
    currency: str
    description: str
    closing_balance: Decimal


@dataclass(frozen=True)
class RejectedRow:
    row_number: int
    reason_code: str


@dataclass(frozen=True)
class IngestionResult:
    currency: str
    accepted_rows: list[DemoTransaction]
    rejected_rows: list[RejectedRow]
    treasury: Any | None = None


def redact_pii_string(raw_text: str) -> str:
    """Masks basic IBAN-shaped values and US phone numbers in transaction text."""
    masked = re.sub(r"\b[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}\b", "[REDACTED_IBAN]", raw_text)
    return re.sub(r"\b\d{3}[-.\s]??\d{3}[-.\s]??\d{4}\b", "[REDACTED_PHONE]", masked)


def parse_bank_records(records: list[dict[str, Any]], tenant_id: str) -> list[NormalizedTransaction]:
    """Parse legacy transaction objects using the original Pydantic boundary."""
    normalized = []
    for item in records:
        normalized.append(
            NormalizedTransaction(
                id=str(item["id"]),
                tenant_id=tenant_id,
                post_date=date.fromisoformat(str(item["post_date"])),
                amount=Decimal(str(item["amount"])),
                counterparty=redact_pii_string(str(item.get("counterparty", "Unknown"))),
                category=str(item.get("category", "GENERAL")),
                is_nsf=bool(item.get("is_nsf", False)),
            )
        )
    return normalized


# ---------------------------------------------------------------------------
# Universal Financial Table Parser (Multi-Bank, Payment Processors, Accounting)
# ---------------------------------------------------------------------------

_DATE_ALIASES = {
    "date", "postedon", "postdate", "postingdate", "transactiondate", "transdate",
    "bookingdate", "effectivedate", "valuedate", "created", "createdat", "createdutc",
    "time", "timestamp", "when", "activitydate", "operationdate", "settlementdate",
    "txndate", "processdate", "cleareddate",
}

_AMOUNT_ALIASES = {
    "amount", "transactionamount", "transamount", "value", "total", "howmuch",
    "sum", "price", "subtotal", "txnamount",
}

_NET_ALIASES = {"net", "netamount"}

_DEBIT_ALIASES = {
    "debit", "withdrawal", "withdrawals", "moneyout", "paidout", "debitamount",
    "dr", "expense", "charges", "outflow", "spent", "debits", "payments",
}

_CREDIT_ALIASES = {
    "credit", "deposit", "deposits", "moneyin", "paidin", "creditamount",
    "cr", "income", "receipts", "inflow", "received", "credits",
}

_DESCRIPTION_ALIASES = {
    "description", "details", "memo", "name", "counterparty", "payee", "payer",
    "merchant", "narrative", "transactiondetails", "notes", "who", "reference",
    "particulars", "split", "item", "title", "vendor", "payeename", "descriptionnarrative",
}

_BALANCE_ALIASES = {
    "closingbalance", "balance", "runningbal", "runningbalance", "accountbalance",
    "currentbalance", "availablebalance", "endingbalance", "ledgerbalance", "bal",
}

_TX_ID_ALIASES = {
    "transactionid", "id", "transid", "txid", "referenceid", "refno",
    "referencenumber", "checknumber", "documentnumber", "num", "receiptid",
    "orderid", "fitid", "chequeno", "checkorslip", "checkslip", "checkno",
}

_CURRENCY_ALIASES = {
    "currency", "curr", "ccy", "currencycode", "isocurrency",
}


def _detect_columns(header: list[str]) -> dict[str, int] | None:
    norm_cols = [_normalize_col_name(c) for c in header]
    mapping: dict[str, int] = {}

    for idx, col in enumerate(norm_cols):
        if not col:
            continue
        if "tx_id" not in mapping and col in _TX_ID_ALIASES:
            mapping["tx_id"] = idx
        elif "date" not in mapping and col in _DATE_ALIASES:
            mapping["date"] = idx
        elif "balance" not in mapping and col in _BALANCE_ALIASES:
            mapping["balance"] = idx
        elif "debit" not in mapping and col in _DEBIT_ALIASES:
            mapping["debit"] = idx
        elif "credit" not in mapping and col in _CREDIT_ALIASES:
            mapping["credit"] = idx
        elif col in _NET_ALIASES:
            # Net amount has priority over gross amount
            mapping["amount"] = idx
        elif "amount" not in mapping and col in _AMOUNT_ALIASES:
            mapping["amount"] = idx
        elif "description" not in mapping and col in _DESCRIPTION_ALIASES:
            mapping["description"] = idx
        elif "currency" not in mapping and col in _CURRENCY_ALIASES:
            mapping["currency"] = idx

    has_date = "date" in mapping
    has_amount = "amount" in mapping or "debit" in mapping or "credit" in mapping
    if not (has_date and has_amount):
        return None

    return mapping





def _profiled_to_col_map(profiled: ProfiledSchema) -> dict[str, int]:
    col_map: dict[str, int] = {"date": profiled.date_col}
    if profiled.amount_col is not None:
        col_map["amount"] = profiled.amount_col
    if profiled.debit_col is not None:
        col_map["debit"] = profiled.debit_col
    if profiled.credit_col is not None:
        col_map["credit"] = profiled.credit_col
    if profiled.balance_col is not None:
        col_map["balance"] = profiled.balance_col
    if profiled.description_col is not None:
        col_map["description"] = profiled.description_col
    if profiled.currency_col is not None:
        col_map["currency"] = profiled.currency_col
    if profiled.tx_id_col is not None:
        col_map["tx_id"] = profiled.tx_id_col
    return col_map


def parse_bank_csv(content: bytes, llm_config: LLMConfig | None = None) -> IngestionResult:
    """Universal bank statement and financial table CSV parser.
    
    Dynamically infers semantic roles via:
    1. Fast path for standard schema.
    2. Stage 1: Mathematical Content Profiler (balance invariant proofs B[i+1]-B[i]==A[i+1], data types).
    3. Stage 2: Dynamic LLM Schema Resolver (for ambiguous or foreign tables).
    4. Stage 3: Semantic header alias mapping fallback.
    """
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CSVIngestionError("INVALID_ENCODING", "Upload must be UTF-8 encoded CSV.") from exc

    delimiter = _detect_delimiter(text)
    raw_lines = [line for line in text.splitlines() if line.strip()]
    if not raw_lines:
        raise CSVIngestionError("INVALID_HEADER", "CSV header is missing or malformed.")

    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    try:
        header = next(reader)
    except (StopIteration, csv.Error) as exc:
        raise CSVIngestionError("INVALID_HEADER", "CSV header is missing or malformed.") from exc

    # 1. Fast path: exact match with standard baseline schema
    if header == EXPECTED_HEADER:
        return _parse_standard_csv(reader)

    # 2. Extract sample matrix for content profiling
    sample_matrix: list[list[str]] = []
    for line in raw_lines[:25]:
        try:
            r = next(csv.reader([line], delimiter=delimiter))
            sample_matrix.append(r)
        except Exception:
            continue

    detected: dict[str, int] | None = None
    header_offset = 1
    is_headerless = False

    # Stage 1A: Test if the file is completely headerless (row 0 has a valid date)
    if len(sample_matrix) >= 2:
        profiled_all = profile_table_content(sample_matrix)
        if profiled_all and profiled_all.confidence >= 0.85:
            try:
                _parse_universal_date(sample_matrix[0][profiled_all.date_col])
                # Row 0 contains a valid date in date_col -> headerless table!
                detected = _profiled_to_col_map(profiled_all)
                header_offset = 0
                is_headerless = True
                reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
            except Exception:
                pass

    # Stage 1B: Test if row 0 was a header and remaining rows are data
    if detected is None and len(sample_matrix) >= 3:
        profiled_data = profile_table_content(sample_matrix[1:])
        if profiled_data and profiled_data.confidence >= 0.85:
            detected = _profiled_to_col_map(profiled_data)
            header_offset = 1
            remaining_text = "\n".join(raw_lines[header_offset:])
            reader = csv.reader(io.StringIO(remaining_text, newline=""), delimiter=delimiter, strict=True)

    # Stage 2: Dynamic LLM Schema Resolver (if profiling uncertain)
    if detected is None and llm_config is not None:
        llm_profiled = resolve_schema_with_llm(sample_matrix[:5], llm_config)
        if llm_profiled:
            detected = _profiled_to_col_map(llm_profiled)
            header_offset = 1
            remaining_text = "\n".join(raw_lines[header_offset:])
            reader = csv.reader(io.StringIO(remaining_text, newline=""), delimiter=delimiter, strict=True)

    # If headers are present, enrich detected mapping with explicit header matches (e.g. tx_id)
    if detected is not None and not is_headerless and header:
        header_cols = _detect_columns(header)
        if header_cols:
            if "tx_id" in header_cols and "tx_id" not in detected:
                detected["tx_id"] = header_cols["tx_id"]
            if "description" in header_cols and "description" not in detected:
                detected["description"] = header_cols["description"]
            if "currency" in header_cols and "currency" not in detected:
                detected["currency"] = header_cols["currency"]

    # Stage 3: Semantic header detection fallback
    if detected is None:
        detected = _detect_columns(header)
        header_offset = 1
        if detected is None:
            # Search within first 10 lines for header
            for idx in range(1, min(10, len(raw_lines))):
                try:
                    candidate = next(csv.reader([raw_lines[idx]], delimiter=delimiter))
                    detected = _detect_columns(candidate)
                    if detected is not None:
                        header = candidate
                        header_offset = idx + 1
                        remaining_text = "\n".join(raw_lines[header_offset:])
                        reader = csv.reader(io.StringIO(remaining_text, newline=""), delimiter=delimiter, strict=True)
                        break
                except Exception:
                    continue

    if detected is None:
        raise CSVIngestionError("INVALID_HEADER", "CSV header does not match required schema: " + ",".join(EXPECTED_HEADER))

    return _parse_universal_csv(reader, detected, start_row=header_offset + 1)


def _parse_standard_csv(reader: Any) -> IngestionResult:
    """Parses standard schema while preserving strict test invariants."""
    accepted: list[DemoTransaction] = []
    rejected: list[RejectedRow] = []
    seen_ids: set[str] = set()
    previous_date: date | None = None
    currencies: set[str] = set()

    try:
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(EXPECTED_HEADER):
                rejected.append(RejectedRow(row_number, "INVALID_ROW_SHAPE"))
                continue

            transaction_id, posted_on_raw, amount_raw, currency, description, balance_raw = row
            if not re.fullmatch(r"[A-Z]{3}", currency):
                rejected.append(RejectedRow(row_number, "INVALID_CURRENCY"))
                continue
            try:
                amount = Decimal(amount_raw)
                closing_balance = Decimal(balance_raw)
                if not amount.is_finite() or not closing_balance.is_finite():
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                rejected.append(RejectedRow(row_number, "INVALID_AMOUNT"))
                continue

            currencies.add(currency)
            if len(currencies) > 1:
                raise CSVIngestionError("MIXED_CURRENCIES", "All rows in one upload must use the same currency.")

            try:
                posted_on = date.fromisoformat(posted_on_raw)
                if posted_on.isoformat() != posted_on_raw:
                    raise ValueError("date must use ISO YYYY-MM-DD")
            except ValueError:
                rejected.append(RejectedRow(row_number, "INVALID_DATE"))
                continue

            if not transaction_id.strip() or transaction_id in seen_ids:
                rejected.append(RejectedRow(row_number, "DUPLICATE_TRANSACTION_ID"))
                continue
            if previous_date is not None and posted_on < previous_date:
                rejected.append(RejectedRow(row_number, "OUT_OF_ORDER_DATE"))
                continue

            accepted.append(
                DemoTransaction(
                    row_number=row_number,
                    transaction_id=transaction_id,
                    posted_on=posted_on,
                    amount=amount,
                    currency=currency,
                    description=description,
                    closing_balance=closing_balance,
                )
            )
            seen_ids.add(transaction_id)
            previous_date = posted_on
    except csv.Error as exc:
        raise CSVIngestionError("INVALID_ROW_SHAPE", "CSV contains malformed quoting.") from exc

    if not accepted:
        raise CSVIngestionError("NO_VALID_ROWS", "CSV contains no valid transaction rows.")
    return IngestionResult(currency=accepted[0].currency, accepted_rows=accepted, rejected_rows=rejected)


def _parse_universal_csv(reader: Any, col_map: dict[str, int], start_row: int) -> IngestionResult:
    """Parses universal columns, normalizes notations, backfills balances and hashes IDs."""
    raw_accepted: list[dict[str, Any]] = []
    rejected: list[RejectedRow] = []
    currencies: set[str] = set()

    date_idx = col_map["date"]
    amount_idx = col_map.get("amount")
    debit_idx = col_map.get("debit")
    credit_idx = col_map.get("credit")
    balance_idx = col_map.get("balance")
    desc_idx = col_map.get("description")
    id_idx = col_map.get("tx_id")
    curr_idx = col_map.get("currency")

    max_required_idx = max(filter(lambda x: x is not None, [date_idx, amount_idx, debit_idx, credit_idx]))

    try:
        for row_number, row in enumerate(reader, start=start_row):
            if not row or all(not cell.strip() for cell in row):
                continue
            if len(row) <= max_required_idx:
                rejected.append(RejectedRow(row_number, "INVALID_ROW_SHAPE"))
                continue

            # 1. Parse Date
            try:
                posted_on = _parse_universal_date(row[date_idx])
            except (ValueError, IndexError):
                rejected.append(RejectedRow(row_number, "INVALID_DATE"))
                continue

            # 2. Parse Amount (or Debit / Credit)
            detected_sym_ccy: str | None = None
            try:
                if amount_idx is not None and amount_idx < len(row) and row[amount_idx].strip():
                    amount, detected_sym_ccy = _parse_universal_amount(row[amount_idx])
                elif debit_idx is not None or credit_idx is not None:
                    credit_val = Decimal("0.00")
                    debit_val = Decimal("0.00")
                    if credit_idx is not None and credit_idx < len(row) and row[credit_idx].strip():
                        credit_val, sym1 = _parse_universal_amount(row[credit_idx])
                        detected_sym_ccy = detected_sym_ccy or sym1
                    if debit_idx is not None and debit_idx < len(row) and row[debit_idx].strip():
                        debit_val, sym2 = _parse_universal_amount(row[debit_idx])
                        detected_sym_ccy = detected_sym_ccy or sym2
                    amount = credit_val - abs(debit_val)
                else:
                    rejected.append(RejectedRow(row_number, "INVALID_AMOUNT"))
                    continue
            except (InvalidOperation, ValueError, IndexError):
                rejected.append(RejectedRow(row_number, "INVALID_AMOUNT"))
                continue

            # 3. Parse Currency
            currency = "USD"
            if curr_idx is not None and curr_idx < len(row) and row[curr_idx].strip():
                cur_candidate = row[curr_idx].strip().upper()
                if re.fullmatch(r"[A-Z]{3}", cur_candidate):
                    currency = cur_candidate
                elif detected_sym_ccy:
                    currency = detected_sym_ccy
            elif detected_sym_ccy:
                currency = detected_sym_ccy

            currencies.add(currency)
            if len(currencies) > 1:
                raise CSVIngestionError("MIXED_CURRENCIES", "All rows in one upload must use the same currency.")

            # 4. Parse Description
            if desc_idx is not None and desc_idx < len(row):
                description = redact_pii_string(row[desc_idx].strip() or "Transaction")
            else:
                description = "Transaction"

            # 5. Parse Closing Balance (if present)
            closing_balance: Decimal | None = None
            if balance_idx is not None and balance_idx < len(row) and row[balance_idx].strip():
                try:
                    bal_val, _ = _parse_universal_amount(row[balance_idx])
                    closing_balance = bal_val
                except (InvalidOperation, ValueError):
                    closing_balance = None

            # 6. Parse Transaction ID
            if id_idx is not None and id_idx < len(row) and row[id_idx].strip():
                tx_id = row[id_idx].strip()
            else:
                raw_hash = hashlib.sha256(f"{row_number}_{posted_on}_{amount}_{description}".encode("utf-8")).hexdigest()[:12]
                tx_id = f"tx_{raw_hash}"

            raw_accepted.append({
                "row_number": row_number,
                "transaction_id": tx_id,
                "posted_on": posted_on,
                "amount": amount,
                "currency": currency,
                "description": description,
                "closing_balance": closing_balance,
            })
    except csv.Error as exc:
        raise CSVIngestionError("INVALID_ROW_SHAPE", "CSV contains malformed quoting.") from exc

    if not raw_accepted:
        raise CSVIngestionError("NO_VALID_ROWS", "CSV contains no valid transaction rows.")

    # Sort chronologically by posted_on
    raw_accepted.sort(key=lambda item: (item["posted_on"], item["row_number"]))

    # Reconstruct running balance if balance column was omitted or partially populated
    has_explicit_balances = all(item["closing_balance"] is not None for item in raw_accepted)
    if not has_explicit_balances:
        # Reconstruct running balance cumulatively from net cash movements
        cumulative = Decimal("0.00")
        for item in raw_accepted:
            if item["closing_balance"] is not None:
                cumulative = item["closing_balance"]
            else:
                cumulative += item["amount"]
                item["closing_balance"] = cumulative

    accepted_rows = [
        DemoTransaction(
            row_number=item["row_number"],
            transaction_id=item["transaction_id"],
            posted_on=item["posted_on"],
            amount=item["amount"],
            currency=item["currency"],
            description=item["description"],
            closing_balance=item["closing_balance"],
        )
        for item in raw_accepted
    ]

    return IngestionResult(currency=accepted_rows[0].currency, accepted_rows=accepted_rows, rejected_rows=rejected)


def parse_multiple_bank_csv(
    files: Sequence[tuple[str, bytes]],
    llm_config: LLMConfig | None = None,
) -> IngestionResult:
    """Parses and consolidates multiple CSV statements across accounts or sequential periods."""
    if not files:
        raise CSVIngestionError("NO_FILES", "No statement files provided.")
    if len(files) == 1:
        return parse_bank_csv(files[0][1], llm_config=llm_config)

    file_results: list[tuple[str, IngestionResult]] = []
    for filename, content in files:
        result = parse_bank_csv(content, llm_config=llm_config)
        file_results.append((filename, result))

    currencies = {res.currency for _, res in file_results}
    if len(currencies) > 1:
        raise CSVIngestionError(
            "MIXED_CURRENCIES",
            f"Statements use conflicting currencies: {', '.join(sorted(currencies))}. All merged files must share the same currency.",
        )

    from services.ingestion.portfolio_consolidator import consolidate_multi_statement_treasury
    treasury = consolidate_multi_statement_treasury(file_results)

    if not treasury.accepted_rows:
        raise CSVIngestionError("NO_VALID_ROWS", "Merged CSV statements contain no valid transactions.")

    return IngestionResult(
        currency=treasury.currency,
        accepted_rows=treasury.accepted_rows,
        rejected_rows=treasury.rejected_rows,
        treasury=treasury,
    )
