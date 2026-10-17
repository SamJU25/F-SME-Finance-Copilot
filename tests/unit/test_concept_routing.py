"""Concept questions get card-grounded answers, and questions never stage proposals."""

from unittest.mock import patch

import pytest

from services.agent.prompts import is_question
from services.agent.schema import AgentChatRequest, LLMConfig
from services.agent.supervisor import run_copilot_supervisor
from services.security.staging_ledger import staging_ledger

CLOUD = LLMConfig(provider="gemini", model_name="gemini-2.0-flash", api_key="test-key")
DSCR_QUESTION = "What is DSCR and why do lenders care about it?"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Why does the app need a passkey?", True),
        ("how does invoice factoring work", True),
        ("Can you explain staging", True),
        ("Is a factor rate the same as APR", True),
        ("Please stage an application to draw line of $25,000 for working capital", False),
        ("Stage credit line application for $10,000", False),
        ("Draw $5,000 from the credit line", False),
    ],
)
def test_is_question(text, expected):
    assert is_question(text) is expected


@pytest.mark.parametrize(
    "message",
    [
        "Why does the app need a passkey?",
        "How does drawing on the credit line work?",
        "Can you explain what staging a transfer means?",
    ],
)
def test_questions_never_stage_a_proposal(message):
    staging_ledger.clear()
    resp = run_copilot_supervisor(AgentChatRequest(message=message))
    assert resp.intent_detected != "ACTION_STAGING"
    assert resp.staged_action is None
    assert staging_ledger.list_intents() == []


def test_instruction_still_stages_a_proposal():
    staging_ledger.clear()
    resp = run_copilot_supervisor(AgentChatRequest(message="Stage credit line application for $10,000"))
    assert resp.intent_detected == "ACTION_STAGING"
    assert resp.staged_action is not None


def test_concept_question_without_model_uses_card_and_calculation_guidance():
    reply = run_copilot_supervisor(AgentChatRequest(message=DSCR_QUESTION)).reply
    assert "debt payments" in reply.lower()  # from the DSCR card
    assert "To calculate your Debt Service Coverage Ratio" in reply  # how to run it


def test_concept_question_with_model_returns_model_answer_plus_guidance():
    captured = {}
    answer = (
        "DSCR compares the cash a business earns from operations with the loan payments it owes. "
        "Lenders use it to check that repayments come from operating income rather than new borrowing."
    )

    def fake_llm(prompt, system_instruction, config, history=None):
        captured["system"] = system_instruction
        return answer

    with patch("services.agent.supervisor.query_external_llm", side_effect=fake_llm):
        reply = run_copilot_supervisor(AgentChatRequest(message=DSCR_QUESTION), llm_config=CLOUD).reply

    assert "Debt Service Coverage Ratio (DSCR)" in captured["system"]  # card in prompt
    assert reply.startswith("DSCR compares the cash")
    assert "To calculate your Debt Service Coverage Ratio" in reply


def test_concept_answer_with_invented_figure_falls_back_to_card():
    def fake_llm(prompt, system_instruction, config, history=None):
        return "DSCR is usually 7.85x for healthy firms, so lenders want at least that before approving any loan."

    with patch("services.agent.supervisor.query_external_llm", side_effect=fake_llm):
        reply = run_copilot_supervisor(AgentChatRequest(message=DSCR_QUESTION), llm_config=CLOUD).reply

    assert "7.85" not in reply
    assert "To calculate your Debt Service Coverage Ratio" in reply


def test_invoice_verification_never_uses_sample_invoice_values():
    reply = run_copilot_supervisor(AgentChatRequest(message="Why does the app need a passkey?")).reply
    assert "Canonical Cryptographic Hash" not in reply
    assert "UNREGISTERED" not in reply
    assert "passkey" in reply.lower()


def test_invoice_verification_without_details_asks_for_them():
    reply = run_copilot_supervisor(AgentChatRequest(message="Verify this invoice hash for me")).reply
    assert "please provide the supplier tax ID" in reply
    assert "Canonical Cryptographic Hash" not in reply
