import io
from decimal import Decimal
import pytest
import pypdf

from services.ingestion.pdf_validator import (
    PDFValidationError,
    validate_pdf_statement,
)
from services.ingestion.pdf_parser import (
    BankPDFParser,
    parse_pdf_statement,
)
from services.agent.tools import tool_analyze_cash_flow


def _create_synthetic_bank_pdf(statement_lines: list[str], encrypt_password: str = None) -> bytes:
    """Helper to generate in-memory synthetic PDF with text content."""
    writer = pypdf.PdfWriter()
    
    # Create a canvas page with text stream
    # pypdf allows creating blank pages and adding text or stream operations
    page = writer.add_blank_page(width=612, height=792)
    
    # We can write text content directly into page content stream
    text_content = "\n".join(statement_lines)
    # Simple PostScript/PDF text stream
    stream_ops = "BT /F1 10 Tf 50 700 Td "
    for line in statement_lines:
        safe_line = line.replace("(", "\\(").replace(")", "\\)")
        stream_ops += f"({safe_line}) Tj 0 -15 Td "
    stream_ops += "ET"
    
    # Add a simple font dictionary
    font_dict = pypdf.generic.DictionaryObject()
    font_dict[pypdf.generic.NameObject("/Type")] = pypdf.generic.NameObject("/Font")
    font_dict[pypdf.generic.NameObject("/Subtype")] = pypdf.generic.NameObject("/Type1")
    font_dict[pypdf.generic.NameObject("/BaseFont")] = pypdf.generic.NameObject("/Helvetica")
    
    res_dict = pypdf.generic.DictionaryObject()
    fonts_res = pypdf.generic.DictionaryObject()
    fonts_res[pypdf.generic.NameObject("/F1")] = font_dict
    res_dict[pypdf.generic.NameObject("/Font")] = fonts_res
    page[pypdf.generic.NameObject("/Resources")] = res_dict
    
    stream_obj = pypdf.generic.DecodedStreamObject()
    stream_obj.set_data(stream_ops.encode("latin1"))
    page[pypdf.generic.NameObject("/Contents")] = stream_obj
    
    if encrypt_password:
        writer.encrypt(encrypt_password)
        
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class TestPDFValidator:
    def test_empty_payload_fails(self):
        with pytest.raises(PDFValidationError) as exc:
            validate_pdf_statement(b"")
        assert exc.value.code == "EMPTY_PAYLOAD"

    def test_invalid_header_fails(self):
        with pytest.raises(PDFValidationError) as exc:
            validate_pdf_statement(b"NOT A REAL PDF FILE CONTENT")
        assert exc.value.code == "INVALID_PDF_HEADER"

    def test_size_limit_exceeded(self):
        fake_huge_pdf = b"%PDF-1.4 " + b"0" * 1024
        with pytest.raises(PDFValidationError) as exc:
            validate_pdf_statement(fake_huge_pdf, max_size_bytes=500)
        assert exc.value.code == "PDF_SIZE_LIMIT_EXCEEDED"

    def test_encrypted_pdf_rejected(self):
        encrypted_bytes = _create_synthetic_bank_pdf(["2026-03-01 Deposit 100.00"], encrypt_password="secretpassword")
        with pytest.raises(PDFValidationError) as exc:
            validate_pdf_statement(encrypted_bytes)
        assert exc.value.code == "ENCRYPTED_PDF_ERROR"

    def test_valid_pdf_passes(self):
        valid_bytes = _create_synthetic_bank_pdf(["Account Statement 2026", "2026-03-01 Opening Balance 10000.00"])
        reader = validate_pdf_statement(valid_bytes)
        assert len(reader.pages) == 1


class TestPDFParser:
    def test_parses_chase_style_statement(self):
        lines = [
            "COMMERCIAL CHECKING ACCOUNT STATEMENT",
            "Account Number: *******1234",
            "Date Description Amount Balance",
            "2026-03-01 STRIPE PAYOUT REVENUE 15000.00 65000.00",
            "2026-03-05 GUSTO PAYROLL DIRECT DEP -8200.00 56800.00",
            "2026-03-10 WEWORK COMMERCIAL RENT -3500.00 53300.00",
            "2026-03-15 CLIENT WIRE SETTLEMENT 12000.00 65300.00",
            "2026-03-20 SBA LOAN DEBT SERVICE -2500.00 62800.00",
        ]
        pdf_bytes = _create_synthetic_bank_pdf(lines)
        res = parse_pdf_statement(pdf_bytes)

        assert res.row_count == 5
        assert res.reconciliation_status == "BALANCED"
        assert res.total_inflows == Decimal("27000.00")
        assert res.total_outflows == Decimal("14200.00")
        assert res.net_change == Decimal("12800.00")
        assert res.closing_balance == Decimal("62800.00")
        assert len(res.reconciliation_breaks) == 0

        # Verify downstream calculation engine consumes generated CSV text with 0 errors
        analysis = tool_analyze_cash_flow(res.csv_text)
        assert analysis["current_balance"] == "62800.00"
        assert analysis["gross_inflows"] == "27000.00"
        assert analysis["gross_outflows"] == "14200.00"
        assert analysis["cash_status"] in ("HEALTHY", "NO_BURN")

    def test_parses_multiline_descriptions(self):
        lines = [
            "Date Transaction Details Amount Balance",
            "03/01/2026 WIRE TRANSFER OUTWARD",
            "BENEFICIARY: ACME SUPPLIES INC",
            "REF #998812 -4500.00 45500.00",
            "03/02/2026 CUSTOMER PAYMENT ACCT 44",
            "ACH CREDIT 10000.00 55500.00",
        ]
        pdf_bytes = _create_synthetic_bank_pdf(lines)
        res = parse_pdf_statement(pdf_bytes)

        assert res.row_count == 2
        assert "BENEFICIARY: ACME SUPPLIES INC" in res.transactions[0].description
        assert res.transactions[0].amount == Decimal("-4500.00")
        assert res.transactions[0].closing_balance == Decimal("45500.00")
        assert res.transactions[1].amount == Decimal("10000.00")
        assert res.reconciliation_status == "BALANCED"

    def test_detects_reconciliation_break(self):
        lines = [
            "Date Description Amount Balance",
            "2026-03-01 OPENING TXN 5000.00 10000.00",
            "2026-03-02 CLIENT DEPOSIT 1000.00 20000.00",  # Math break: 10000 + 1000 != 20000
        ]
        pdf_bytes = _create_synthetic_bank_pdf(lines)
        res = parse_pdf_statement(pdf_bytes)

        assert res.row_count == 2
        assert res.reconciliation_status == "RECONCILIATION_BREAK"
        assert len(res.reconciliation_breaks) == 1
        assert res.reconciliation_breaks[0]["row_index"] == 2
        assert res.reconciliation_breaks[0]["delta"] == "9000.00"
