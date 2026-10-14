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
        "period_days": 2,
        "average_daily_burn": "2.50",
        "runway_days": 38,
        "alert_threshold_days": 10,
        "cash_status": "WATCH",
    }


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
