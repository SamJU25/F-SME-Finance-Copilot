"""
Unit tests for Consortium Blockchain Invoice Registry Service (FISCO BCOS Alignment).
Verifies deterministic SHA-256 canonical hashing and double-financing defense.
"""

import pytest

from services.blockchain import (
    ConsortiumInvoiceRegistry,
    InvoiceStatus,
    InvoiceAlreadyPledgedError,
    InvoiceNotPledgedError,
    calculate_canonical_invoice_hash,
)


@pytest.fixture
def registry():
    reg = ConsortiumInvoiceRegistry()
    yield reg
    reg.clear()


def test_canonical_invoice_hashing_is_deterministic():
    hash1 = calculate_canonical_invoice_hash("US-TAX-101", "BUYER-CORP-A", "INV-2026-001", 1500000)
    hash2 = calculate_canonical_invoice_hash("us-tax-101", "buyer-corp-a", "inv-2026-001", 1500000)
    hash3 = calculate_canonical_invoice_hash("US-TAX-101", "BUYER-CORP-B", "INV-2026-001", 1500000)

    assert hash1.startswith("0x")
    assert len(hash1) == 66  # "0x" + 64 hex chars
    # Case insensitive normalization matches
    assert hash1 == hash2
    # Different buyer produces different hash
    assert hash1 != hash3


def test_canonical_invoice_hashing_validates_inputs():
    with pytest.raises(ValueError):
        calculate_canonical_invoice_hash("", "BUYER", "INV-1", 1000)
    with pytest.raises(ValueError):
        calculate_canonical_invoice_hash("TAX", "BUYER", "INV-1", 0)


def test_pledge_invoice_lifecycle(registry):
    inv_hash = calculate_canonical_invoice_hash("TAX-99", "BUYER-1", "INV-555", 250000)
    assert registry.get_invoice_status(inv_hash) == InvoiceStatus.UNREGISTERED

    # Pledge to Lender 1
    record = registry.pledge_invoice(inv_hash, lender_id=101)
    assert record.status == InvoiceStatus.PLEDGED
    assert record.lender_id == 101
    assert registry.get_invoice_status(inv_hash) == InvoiceStatus.PLEDGED

    # Second pledge attempt by Lender 2 must fail (double-financing defense)
    with pytest.raises(InvoiceAlreadyPledgedError):
        registry.pledge_invoice(inv_hash, lender_id=102)


def test_settle_invoice_lifecycle(registry):
    inv_hash = calculate_canonical_invoice_hash("TAX-99", "BUYER-1", "INV-777", 400000)
    
    # Cannot settle unpledged invoice
    with pytest.raises(InvoiceNotPledgedError):
        registry.settle_invoice(inv_hash)

    # Pledge first, then settle
    registry.pledge_invoice(inv_hash, lender_id=101)
    settled = registry.settle_invoice(inv_hash)
    assert settled.status == InvoiceStatus.SETTLED
    assert registry.get_invoice_status(inv_hash) == InvoiceStatus.SETTLED

    # Cannot pledge settled invoice again
    with pytest.raises(InvoiceAlreadyPledgedError):
        registry.pledge_invoice(inv_hash, lender_id=103)
