from fastapi.testclient import TestClient
import pytest

from api.main import app

client = TestClient(app)


def test_list_decision_engines_api():
    response = client.get("/api/v1/decision/engines")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert data["total_engines"] >= 2

    engine_ids = [e["engine_id"] for e in data["engines"]]
    assert "zen-engine@2.1.3" in engine_ids
    assert "fallback-rules@1.0.0" in engine_ids


def test_evaluate_underwriting_decision_api():
    payload = {
        "domain": "UNDERWRITING",
        "input_state": {
            "dab": 18500.00,
            "nsf_count": 0,
        },
        "execution_mode": "DETERMINISTIC_ONLY",
    }
    response = client.post("/api/v1/decision/evaluate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["domain"] == "UNDERWRITING"
    assert data["selected_choice"] == "PRIME"
    assert data["confidence_score"] == 1.0
    assert data["matched_rule_id"] == "rule_prime"
    assert data["adverse_factors"] == []
    assert data["evaluation_duration_us"] is not None


def test_evaluate_adverse_action_underwriting_api():
    payload = {
        "domain": "UNDERWRITING",
        "input_state": {
            "dab": 1200.00,
            "nsf_count": 3,
        },
        "execution_mode": "DETERMINISTIC_ONLY",
    }
    response = client.post("/api/v1/decision/evaluate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["selected_choice"] == "HIGH_RISK"
    assert data["matched_rule_id"] == "rule_high_risk"
    assert "DAB_BELOW_MINIMUM_THRESHOLD" in data["adverse_factors"]
    assert "EXCESSIVE_NSF_COUNT" in data["adverse_factors"]


def test_evaluate_security_gate_decision_api():
    payload = {
        "domain": "SECURITY_GATE",
        "input_state": {
            "action_type": "TRANSFER",
        },
    }
    response = client.post("/api/v1/decision/evaluate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["selected_choice"] == "TIER_3_EXECUTION"
    assert data["matched_rule_id"] == "rule_tier_3"
    assert data["output_payload"]["requires_biometric_execution"] is True


def test_evaluate_working_capital_decision_api():
    payload = {
        "domain": "WORKING_CAPITAL_RISK",
        "input_state": {
            "metric": "CCC",
            "value": 50,
        },
    }
    response = client.post("/api/v1/decision/evaluate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["selected_choice"] == "WORKING_CAPITAL_TRAP"
    assert data["output_payload"]["is_risk"] is True
    assert data["matched_rule_id"] == "rule_ccc_trap"


def test_reload_decision_tables_api():
    response = client.post("/api/v1/decision/reload")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert "zen-engine@2.1.3" in data["reload_summary"]
    zen_status = data["reload_summary"]["zen-engine@2.1.3"]
    assert zen_status["UNDERWRITING"] == "COMPILED"
    assert zen_status["WORKING_CAPITAL_RISK"] == "COMPILED"
