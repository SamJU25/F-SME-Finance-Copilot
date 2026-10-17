"""Unit tests for explicit model downloading, cache verification, and exception handling.

Verifies:
- Strict zero-silent-download invariant
- Proper exception handling when network fails or disk error occurs
- REST endpoint POST /api/v1/agent/download-model
- Multi-tier local model resolution and availability checking
"""

import os
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from api.main import app
from services.agent.local_transformers import (
    LocalTransformersEngine,
    SUPPORTED_LOCAL_MODELS,
    resolve_canonical_model_name,
)
from services.agent.schema import (
    DownloadModelRequest,
    DownloadModelResponse,
    FetchModelsRequest,
    TestConnectionRequest,
)
from services.agent.llm_bridge import fetch_remote_models, test_llm_connection as run_test_llm_connection

TestConnectionRequest.__test__ = False


@pytest.fixture
def client():
    return TestClient(app)


def test_canonical_model_resolution():
    """Confirms model aliases map cleanly to canonical IDs."""
    assert resolve_canonical_model_name(None) == "sme-finance-lora"
    assert resolve_canonical_model_name("") == "sme-finance-lora"
    assert resolve_canonical_model_name("offline") == "sme-finance-lora"
    assert resolve_canonical_model_name("local") == "sme-finance-lora"
    assert resolve_canonical_model_name("sme-finance-lora") == "sme-finance-lora"


def test_download_model_invalid_identifier():
    """Attempts to download an unknown model return clean error without crashing."""
    engine = LocalTransformersEngine.get_instance()
    res = engine.download_model("nonexistent-model-xyz")
    assert res["success"] is False
    assert "Unsupported model" in res["message"]
    assert res["downloaded_path"] is None


def test_download_model_network_exception_handling():
    """Simulates network timeout/failure during download to verify robust exception handling."""
    engine = LocalTransformersEngine.get_instance()
    with patch("huggingface_hub.snapshot_download", side_effect=ConnectionError("Failed to resolve host 'huggingface.co'")):
        res = engine.download_model("sme-finance-lora")
        assert res["success"] is False
        assert "Network connection error" in res["message"] or "Failed to resolve host" in res["message"]
        assert res["downloaded_path"] is None


def test_download_model_disk_space_exception_handling():
    """Simulates insufficient disk space to verify friendly OS error handling."""
    engine = LocalTransformersEngine.get_instance()
    with patch("huggingface_hub.snapshot_download", side_effect=OSError("No space left on device")):
        res = engine.download_model("sme-finance-lora")
        assert res["success"] is False
        assert "Insufficient disk space" in res["message"] or "space" in res["message"]


def test_api_download_model_route(client):
    """Verifies POST /api/v1/agent/download-model endpoint."""
    with patch.object(
        LocalTransformersEngine,
        "download_model",
        return_value={
            "success": True,
            "model_name": "sme-finance-lora",
            "message": "Model 'sme-finance-lora' downloaded successfully (5886.0 MB).",
            "downloaded_path": "/mock/path/models/base/Qwen2.5-3B-Instruct",
            "size_mb": 5886.0,
        },
    ):
        resp = client.post("/api/v1/agent/download-model", json={"model_name": "sme-finance-lora"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["model_name"] == "sme-finance-lora"
        assert data["size_mb"] == 5886.0
        assert "downloaded successfully" in data["message"]


def test_fetch_remote_models_reports_only_flagship_adapter():
    """Ensures discovery endpoint lists only the fine-tuned 3B adapter, omitting base foundation models."""
    resp = fetch_remote_models(FetchModelsRequest(provider="offline"))
    assert resp.success is True
    ids = [m.id for m in resp.models]
    assert ids == ["sme-finance-lora"]


def test_download_model_saves_into_folder():
    """Verifies download_model passes local_dir to snapshot_download to store weights inside project models folder."""
    engine = LocalTransformersEngine.get_instance()
    with patch("huggingface_hub.snapshot_download") as mock_snapshot:
        mock_snapshot.return_value = "F:/SME Finance Copilot/models/base/Qwen2.5-3B-Instruct"
        res = engine.download_model("sme-finance-lora")
        assert res["success"] is True
        mock_snapshot.assert_called_once()
        _, kwargs = mock_snapshot.call_args
        assert "local_dir" in kwargs
        assert kwargs["local_dir"].endswith("Qwen2.5-3B-Instruct")


def test_test_connection_missing_model_handling():
    """Verifies that test_connection returns actionable guidance asking to download a model first."""
    engine = LocalTransformersEngine.get_instance()
    with patch.object(engine, "is_available", return_value=False):
        resp = run_test_llm_connection(TestConnectionRequest(provider="offline", model_name="sme-finance-lora"))
        assert resp.success is False
        assert "not installed locally on disk" in resp.message
        assert "Download Model" in resp.message


def test_fetch_remote_models_message_when_none_installed():
    """Verifies that discovery message prompts the user to download a model first when 0 models are ready."""
    engine = LocalTransformersEngine.get_instance()
    with patch.object(engine, "is_available", return_value=False):
        resp = fetch_remote_models(FetchModelsRequest(provider="offline"))
        assert resp.success is True
        assert "Download Model" in resp.message


def test_supervisor_asks_to_download_model_when_none_installed():
    """Verifies supervisor prompts the user to download a model first when in local mode with 0 models installed."""
    import os
    from services.agent.supervisor import run_copilot_supervisor
    from services.agent.schema import AgentChatRequest, LLMConfig
    from services.agent.local_transformers import LocalTransformersEngine

    engine = LocalTransformersEngine.get_instance()
    # Temporarily remove PYTEST_CURRENT_TEST to test production user guidance flow
    old_test_env = os.environ.pop("PYTEST_CURRENT_TEST", None)
    try:
        with patch.object(engine, "is_available", return_value=False):
            req = AgentChatRequest(
                message="Hello, how can you help my business?",
                llm_config=LLMConfig(provider="offline", model_name="sme-finance-lora"),
            )
            resp = run_copilot_supervisor(req, llm_config=req.llm_config)
            assert "Autonomous SME Finance Copilot" in resp.reply
            assert "Please download a model first" in resp.reply
            assert "Download Model" in resp.reply
    finally:
        if old_test_env is not None:
            os.environ["PYTEST_CURRENT_TEST"] = old_test_env


def test_delete_model_protects_adapters(tmp_path):
    """Verifies that delete_model only targets base model directory and strictly preserves adapters."""
    from services.agent.local_transformers import LORA_MODEL_DIR
    engine = LocalTransformersEngine.get_instance()

    # Confirm the adapter folder exists and is never deleted
    assert os.path.exists(LORA_MODEL_DIR)

    with patch("shutil.rmtree") as mock_rmtree:
        engine.delete_model("sme-finance-lora")
        for call_args in mock_rmtree.call_args_list:
            target_deleted = call_args[0][0]
            assert target_deleted != LORA_MODEL_DIR
            assert "base" in target_deleted or "hub" in target_deleted


def test_api_delete_model_route(client):
    """Verifies POST /api/v1/agent/delete-model endpoint."""
    with patch.object(
        LocalTransformersEngine,
        "delete_model",
        return_value={
            "success": True,
            "model_name": "sme-finance-lora",
            "message": "Model 'sme-finance-lora' removed successfully (5886.0 MB freed).",
            "deleted_path": "/mock/path/models/base/Qwen2.5-3B-Instruct",
            "freed_mb": 5886.0,
        },
    ):
        resp = client.post("/api/v1/agent/delete-model", json={"model_name": "sme-finance-lora"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["model_name"] == "sme-finance-lora"
        assert data["freed_mb"] == 5886.0
        assert "removed successfully" in data["message"]


