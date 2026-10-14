"""CSV parsing for the synthetic, read-only first-demo analysis flow."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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


def redact_pii_string(raw_text: str) -> str:
    """Masks basic IBAN-shaped values and US phone numbers in existing call sites."""
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


def parse_bank_csv(content: bytes) -> IngestionResult:
    """Parse the exact demo CSV schema, preserving row numbers and safe reason codes."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CSVIngestionError("INVALID_ENCODING", "Upload must be UTF-8 encoded CSV.") from exc

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader)
    except (StopIteration, csv.Error) as exc:
        raise CSVIngestionError("INVALID_HEADER", "CSV header is missing or malformed.") from exc
    if header != EXPECTED_HEADER:
        raise CSVIngestionError("INVALID_HEADER", "CSV header does not match the required demo schema.")

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
