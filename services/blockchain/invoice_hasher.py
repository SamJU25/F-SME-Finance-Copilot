"""
Consortium Blockchain Invoice Registry Service.
Calculates deterministic canonical SHA-256 hashes for B2B e-invoices.
Maintains double-financing defense matching on-chain invoice registry contracts.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class InvoiceStatus(str, Enum):
    UNREGISTERED = "UNREGISTERED"
    PLEDGED = "PLEDGED"
    SETTLED = "SETTLED"


class InvoiceAlreadyPledgedError(Exception):
    """Raised when an invoice hash has already been pledged to a lender (double financing)."""


class InvoiceNotPledgedError(Exception):
    """Raised when trying to settle an invoice that was never pledged."""


class InvoicePledgeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    invoice_hash: str = Field(description="0x-prefixed 32-byte hexadecimal SHA-256 hash")
    lender_id: int = Field(gt=0, description="Unique identifier of lending institution")
    pledged_timestamp: int = Field(description="Unix timestamp in seconds")
    status: InvoiceStatus


def calculate_canonical_invoice_hash(
    tax_id: str,
    buyer_id: str,
    invoice_num: str,
    amount_cents: int
) -> str:
    """
    Computes a deterministic canonical SHA-256 hash of invoice identity attributes.
    Matches the input format expected by on-chain consortium registry smart contracts.
    """
    if not tax_id.strip() or not buyer_id.strip() or not invoice_num.strip():
        raise ValueError("tax_id, buyer_id, and invoice_num cannot be empty")
    if amount_cents <= 0:
        raise ValueError("amount_cents must be a positive integer")

    payload = {
        "amount_cents": amount_cents,
        "buyer_id": buyer_id.strip().upper(),
        "invoice_num": invoice_num.strip().upper(),
        "tax_id": tax_id.strip().upper(),
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    sha256_hex = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return f"0x{sha256_hex}"


class ConsortiumInvoiceRegistry:
    """Thread-safe local ledger matching the FISCO BCOS InvoiceRegistry.sol smart contract."""

    def __init__(self) -> None:
        self._records: dict[str, InvoicePledgeRecord] = {}
        self._lock = threading.Lock()

    def pledge_invoice(self, invoice_hash: str, lender_id: int) -> InvoicePledgeRecord:
        """
        Pledges an invoice to a lender. Reverts if already pledged or settled.
        Replicates require(record.status == Status.UNREGISTERED, 'ERR_INVOICE_ALREADY_PLEDGED').
        """
        if lender_id <= 0:
            raise ValueError("lender_id must be a positive integer")

        with self._lock:
            existing = self._records.get(invoice_hash)
            if existing and existing.status in (InvoiceStatus.PLEDGED, InvoiceStatus.SETTLED):
                raise InvoiceAlreadyPledgedError("ERR_INVOICE_ALREADY_PLEDGED")

            record = InvoicePledgeRecord(
                invoice_hash=invoice_hash,
                lender_id=lender_id,
                pledged_timestamp=int(time.time()),
                status=InvoiceStatus.PLEDGED,
            )
            self._records[invoice_hash] = record
            return record

    def settle_invoice(self, invoice_hash: str) -> InvoicePledgeRecord:
        """
        Settles a pledged invoice upon loan repayment.
        Replicates require(record.status == Status.PLEDGED, 'ERR_INVOICE_NOT_PLEDGED').
        """
        with self._lock:
            existing = self._records.get(invoice_hash)
            if not existing or existing.status != InvoiceStatus.PLEDGED:
                raise InvoiceNotPledgedError("ERR_INVOICE_NOT_PLEDGED")

            settled = existing.model_copy(update={"status": InvoiceStatus.SETTLED})
            self._records[invoice_hash] = settled
            return settled

    def get_invoice_status(self, invoice_hash: str) -> InvoiceStatus:
        """Queries the current on-chain status of an invoice hash."""
        with self._lock:
            record = self._records.get(invoice_hash)
            return record.status if record else InvoiceStatus.UNREGISTERED

    def get_record(self, invoice_hash: str) -> Optional[InvoicePledgeRecord]:
        """Queries the complete pledge record."""
        with self._lock:
            return self._records.get(invoice_hash)

    def clear(self) -> None:
        """Clears all records (used for test isolation)."""
        with self._lock:
            self._records.clear()


# Shared singleton instance
invoice_registry = ConsortiumInvoiceRegistry()
