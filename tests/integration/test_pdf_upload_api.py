"""Integration tests for PDF bank statement ingestion across FastAPI REST endpoints."""

import io
from fastapi.testclient import TestClient
import pypdf

from api.main import app
from services.security.staging_ledger import staging_ledger

client = TestClient(app)


def _create_synthetic_bank_pdf(statement_lines: list[str], encrypt_password: str = None) -> bytes:
    """Helper to generate in-memory synthetic PDF with text content."""
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    stream_ops = "BT /F1 10 Tf 50 700 Td "
    for line in statement_lines:
        safe_line = line.replace("(", "\\(").replace(")", "\\)")
        stream_ops += f"({safe_line}) Tj 0 -15 Td "
    stream_ops += "ET"

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


SAMPLE_STATEMENT_LINES = [
    "CHASE BUSINESS CHECKING ...4491",
    "CHECKING SUMMARY",
    "Beginning Balance $10,000.00",
    "TRANSACTION DETAIL",
    "DATE DESCRIPTION AMOUNT BALANCE",
    "2026-01-05 ACME CORP CLIENT PAYMENT 5,000.00 15,000.00",
    "2026-01-10 GUSTO PAYROLL SERVICES -3,000.00 12,000.00",
    "2026-01-15 WEWORK LEASE PAYMENT -2,000.00 10,000.00",
    "2026-01-20 STRIPE PAYOUT INFLOW 4,000.00 14,000.00",
    "Ending Balance $14,000.00",
]


def test_analyze_endpoint_pdf_upload():
    pdf_bytes = _create_synthetic_bank_pdf(SAMPLE_STATEMENT_LINES)
    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "30"},
        files={"file": ("chase_statement.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        headers={"X-Session-ID": "test_sess_pdf_01"},
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["accepted_count"] == 4
    assert data["current_balance"] == "14000.00"
    assert data["document_format"] == "PDF"
    assert data["page_count"] == 1
    assert data["normalized_csv"] is not None
    assert "transaction_id,posted_on,amount,currency,description,closing_balance" in data["normalized_csv"]


def test_analyze_endpoint_hybrid_upload():
    pdf_bytes = _create_synthetic_bank_pdf(SAMPLE_STATEMENT_LINES)
    csv_bytes = (
        "transaction_id,posted_on,amount,currency,description,closing_balance\n"
        "tx_c1,2026-01-25,1000.00,USD,Supplementary Invoice,15000.00\n"
    ).encode("utf-8")

    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "30"},
        files=[
            ("files", ("chase_statement.pdf", io.BytesIO(pdf_bytes), "application/pdf")),
            ("files", ("secondary_statement.csv", io.BytesIO(csv_bytes), "text/csv")),
        ],
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["accepted_count"] == 5
    assert data["document_format"] == "HYBRID"


def test_underwrite_endpoint_pdf_upload():
    pdf_bytes = _create_synthetic_bank_pdf(SAMPLE_STATEMENT_LINES)
    response = client.post(
        "/api/v1/underwrite",
        data={"nsf_count": 0},
        files={"file": ("chase_statement.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    data = response.json()

    dossier = data["dossier"]
    assert dossier["transaction_count"] == 4
    assert Decimal_valid(dossier["daily_average_balance"])
    assert len(data["matched_options"]) > 0


def test_agent_chat_with_pdf_statement():
    import base64
    pdf_bytes = _create_synthetic_bank_pdf(SAMPLE_STATEMENT_LINES)
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")

    response = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "What is my current cash runway and balance?",
            "csv_content": pdf_b64,
            "session_id": "sess_pdf_chat_01",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reply"] is not None
    assert "14,000" in body["reply"] or "14000" in body["reply"]


def test_analyze_pdf_error_handling():
    # 1. Encrypted PDF
    enc_pdf = _create_synthetic_bank_pdf(SAMPLE_STATEMENT_LINES, encrypt_password="locked")
    res_enc = client.post(
        "/api/v1/analyze",
        files={"file": ("locked.pdf", io.BytesIO(enc_pdf), "application/pdf")},
    )
    assert res_enc.status_code == 422
    assert res_enc.json()["error"]["code"] == "ENCRYPTED_PDF_ERROR"

    # 2. Corrupted PDF Header
    res_corrupt = client.post(
        "/api/v1/analyze",
        files={"file": ("corrupt.pdf", io.BytesIO(b"NOT_A_PDF_STREAM"), "application/pdf")},
    )
    assert res_corrupt.status_code == 422
    assert res_corrupt.json()["error"]["code"] == "INVALID_PDF_HEADER"

    # 3. Empty PDF
    res_empty = client.post(
        "/api/v1/analyze",
        files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
    )
    assert res_empty.status_code == 422
    assert res_empty.json()["error"]["code"] == "EMPTY_PAYLOAD"


def Decimal_valid(val_str: str) -> bool:
    from decimal import Decimal
    try:
        Decimal(val_str)
        return True
    except Exception:
        return False
