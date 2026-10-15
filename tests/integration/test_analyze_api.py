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
        data={"alert_threshold_days": "10"},
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

