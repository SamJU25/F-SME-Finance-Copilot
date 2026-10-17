from fastapi.testclient import TestClient

from api.main import app
from api.routes import analyze

client = TestClient(app)
CSV = (
    "transaction_id,posted_on,amount,currency,description,closing_balance\n"
    "tx-1,2026-10-01,-10.00,USD,Office supplies,90.00\n"
    "tx-2,2026-10-02,5.00,USD,Customer payment,95.00\n"
)


def test_analyze_api_returns_decimal_strings_and_row_provenance():
    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "10", "as_of_date": "2026-10-02"},
        files={"file": ("synthetic.csv", CSV.encode(), "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "currency": "USD",
        "accepted_count": 2,
        "rejected_rows": [],
        "current_balance": "95.00",
        "net_period_change": "-5.00",
        "gross_inflows": "5.00",
        "gross_outflows": "10.00",
        "period_days": 2,
        "average_daily_burn": "2.50",
        "runway_days": 38,
        "alert_threshold_days": 10,
        "cash_status": "WATCH",
        "cash_conversion_cycle_days": None,
        "working_capital_status": None,
        "working_capital_rationale": None,
        "start_date": "2026-10-01",
        "end_date": "2026-10-02",
        "statement_age_days": 0,
        "analysis_mode": "LIVE_OPERATING",
        "projected_depletion_date": "2026-11-09",
        "alert_boundary_date": "2026-10-12",
        "accounts_breakdown": None,
        "internal_transfers_excluded": None,
        "internal_transfers": None,
        "calendar_gaps": None,
        "has_overlaps_deduped": None,
        "operational_inflows": None,
        "operational_outflows": None,
        "document_format": "CSV",
        "page_count": None,
        "normalized_csv": None,
    }


def test_analyze_api_with_cash_conversion_cycle():
    response = client.post(
        "/api/v1/analyze",
        data={
            "alert_threshold_days": "10",
            "dso_days": "45",
            "dpo_days": "15",
            "dio_days": "0",
        },
        files={"file": ("synthetic.csv", CSV.encode(), "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cash_conversion_cycle_days"] == 30
    assert body["working_capital_status"] == "BALANCED"
    assert "balanced at 30 days" in body["working_capital_rationale"]


def test_analyze_api_reports_file_errors_in_stable_shape():
    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "10"},
        files={"file": ("invalid.csv", b"bad,header\n", "text/csv")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_HEADER"


def test_analyze_api_rejects_invalid_threshold():
    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "0"},
        files={"file": ("synthetic.csv", CSV.encode(), "text/csv")},
    )
    assert response.status_code == 422


def test_analyze_api_enforces_configured_upload_limit(monkeypatch):
    monkeypatch.setattr(analyze, "MAX_UPLOAD_BYTES", 8)
    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "10"},
        files={"file": ("large.csv", CSV.encode(), "text/csv")},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "UPLOAD_TOO_LARGE"


def test_analyze_api_defaults_threshold_to_30_when_omitted():
    response = client.post(
        "/api/v1/analyze",
        files={"file": ("synthetic.csv", CSV.encode(), "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["alert_threshold_days"] == 30


def test_analyze_api_adapts_to_historical_audit_mode_for_outdated_statement():
    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "10", "as_of_date": "2027-01-01"},
        files={"file": ("synthetic.csv", CSV.encode(), "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["statement_age_days"] == 91
    assert body["analysis_mode"] == "HISTORICAL_AUDIT"


def test_analyze_api_with_multiple_csv_files():
    file1 = (
        "Date,Description,Amount,Running Bal.\n"
        "2026-10-01,Invoice payment,1000.00,5000.00\n"
        "2026-10-02,Software subscription,-50.00,4950.00\n"
    ).encode()
    file2 = (
        "Date,Description,Amount,Running Bal.\n"
        "2026-10-03,Client retainer,2000.00,6950.00\n"
        "2026-10-04,Office supply,-150.00,6800.00\n"
    ).encode()

    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "15"},
        files=[
            ("files", ("oct_part1.csv", file1, "text/csv")),
            ("files", ("oct_part2.csv", file2, "text/csv")),
        ],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted_count"] == 4
    assert body["current_balance"] == "6800.00"
    assert body["period_days"] == 4


def test_analyze_api_with_universal_bofa_format():
    bofa_csv = (
        "Date,Description,Amount,Running Bal.\n"
        "10/01/2026,Deposit,3000.00,10000.00\n"
        "10/05/2026,Office Depot,-200.00,9800.00\n"
    ).encode()

    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "30"},
        files={"file": ("bofa_statement.csv", bofa_csv, "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted_count"] == 2
    assert body["current_balance"] == "9800.00"


def test_analyze_api_multi_account_portfolio_consolidation_and_contra_transfer():
    chase_csv = (
        "Date,Description,Amount,Running Bal.\n"
        "2026-10-01,Client Payment,5000.00,15000.00\n"
        "2026-10-02,Wire to SVB Checking,-2000.00,13000.00\n"
    ).encode()
    svb_csv = (
        "Date,Description,Amount,Running Bal.\n"
        "2026-10-02,Wire from Chase,2000.00,7000.00\n"
        "2026-10-03,Cloud Infrastructure Hosting,-500.00,6500.00\n"
    ).encode()

    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "30"},
        files=[
            ("files", ("chase_operating.csv", chase_csv, "text/csv")),
            ("files", ("svb_payroll.csv", svb_csv, "text/csv")),
        ],
    )
    assert response.status_code == 200
    body = response.json()

    assert body["accepted_count"] == 4
    # Multi-account total treasury: 13000 + 6500 = 19500
    assert body["current_balance"] == "19500.00"

    # Accounts breakdown
    assert len(body["accounts_breakdown"]) == 2
    assert body["accounts_breakdown"][0]["file_name"] == "chase_operating.csv"
    assert body["accounts_breakdown"][0]["closing_balance"] == "13000.00"
    assert body["accounts_breakdown"][1]["file_name"] == "svb_payroll.csv"
    assert body["accounts_breakdown"][1]["closing_balance"] == "6500.00"

    # Contra-transfer elimination
    assert body["internal_transfers_excluded"] == "2000.00"
    assert len(body["internal_transfers"]) == 1
    assert body["internal_transfers"][0]["amount"] == "2000.00"

    # Operational flows with contra-transfers excluded
    assert body["operational_inflows"] == "5000.00"
    assert body["operational_outflows"] == "500.00"


def test_analyze_api_with_multiple_csv_files_under_file_field():
    f1 = b"Date,Description,Amount,Running Bal.\n2026-10-01,Dep1,1000.00,5000.00\n"
    f2 = b"Date,Description,Amount,Running Bal.\n2026-10-02,Dep2,2000.00,7000.00\n"

    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "30"},
        files=[
            ("file", ("statement_a.csv", f1, "text/csv")),
            ("file", ("statement_b.csv", f2, "text/csv")),
        ],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted_count"] == 2
    assert body["accounts_breakdown"] is not None
    assert len(body["accounts_breakdown"]) == 2


def test_analyze_api_deduplicates_duplicate_uploaded_statement_files():
    f1 = b"Date,Description,Amount,Running Bal.\n2026-10-01,Dep1,1000.00,5000.00\n"
    f2 = b"Date,Description,Amount,Running Bal.\n2026-10-02,Dep2,2000.00,7000.00\n"

    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "30"},
        files=[
            ("files", ("statement_a.csv", f1, "text/csv")),
            ("files", ("statement_b.csv", f2, "text/csv")),
            ("files", ("statement_b.csv", f2, "text/csv")),
        ],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accounts_breakdown"] is not None
    assert len(body["accounts_breakdown"]) == 2





