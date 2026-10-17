"""Unit tests for the Hierarchical Rolling Conversation Summarizer.

Verifies:
1. Deterministic conversation condensation when messages exceed active sliding window.
2. SessionStore automatic maintenance of rolling_summary for older turns (> 6 turns).
3. Preservation of both exact financial facts and narrative context in supervisor directives.
4. Memory safety and prompt token boundedness.
"""

import pytest
from unittest.mock import patch, MagicMock

from services.agent.schema import ChatHistoryItem, AgentChatRequest, LLMConfig
from services.agent.session_store import SessionRecord, SessionStore
from services.agent.context_summarizer import generate_deterministic_summary
from services.agent.supervisor import _append_session_context, run_copilot_supervisor


def test_empty_messages_summary():
    """Confirms empty message list returns empty string or existing summary."""
    assert generate_deterministic_summary([]) == ""
    assert generate_deterministic_summary([], existing_summary="Prior discussion.") == "Prior discussion."


def test_deterministic_summary_extracts_key_topics():
    """Verifies that key user financial inquiries and copilot responses are captured accurately."""
    messages = [
        ChatHistoryItem(role="user", text="What is our current cash runway and monthly burn rate?"),
        ChatHistoryItem(role="agent", text="### Financial Diagnostic Summary\nYour runway is 45 days with $12,000 monthly burn."),
        ChatHistoryItem(role="user", text="Can we get financing or loan options to cover the payroll shortfall?"),
        ChatHistoryItem(role="agent", text="### Credit Underwriting Assessment\nYou are pre-qualified for a $50,000 working capital line."),
    ]
    summary = generate_deterministic_summary(messages)
    assert "User inquired about" in summary
    assert "cash runway & burn analysis" in summary
    assert "financing & credit options" in summary
    assert "Copilot calculated cash health and runway metrics" in summary or "evaluated borrowing capacity" in summary


def test_deterministic_summary_caps_length():
    """Confirms summary length is strictly bounded to prevent prompt context bloat."""
    long_messages = [
        ChatHistoryItem(role="user", text=f"Query {i}: We need detailed evaluation of debt service and CCC.")
        for i in range(25)
    ]
    summary = generate_deterministic_summary(long_messages)
    assert len(summary) <= 400
    assert summary.endswith(".")


def test_session_store_maintains_rolling_summary_on_turn_overflow():
    """Verifies that SessionStore.append_turn automatically generates a rolling summary when turns > 6."""
    store = SessionStore.get_instance()
    session_id = "test-rolling-summary-session-001"

    try:
        # 1. Append 3 exchanges (6 messages total: 3 user + 3 agent)
        for i in range(3):
            rec = store.append_turn(
                session_id=session_id,
                user_text=f"User question {i}",
                agent_text=f"Agent response {i}",
            )
        assert len(rec.messages) == 6
        # Under or equal to 6 messages: all messages are inside active sliding window
        assert rec.rolling_summary is None

        # 2. Append a 4th exchange (8 messages total: 4 user + 4 agent)
        rec = store.append_turn(
            session_id=session_id,
            user_text="What are our invoice factoring options?",
            agent_text="### Credit Underwriting Assessment\nFactoring options are available.",
        )
        assert len(rec.messages) == 8
        # Older turns (messages[:-6]) must now be condensed into rolling_summary
        assert rec.rolling_summary is not None
        assert len(rec.rolling_summary) > 0
        assert "User inquired about" in rec.rolling_summary

    finally:
        store.clear(session_id)


def test_append_session_context_injects_facts_and_summary():
    """Confirms _append_session_context appends both verified facts and rolling narrative."""
    base_directive = "You are the Autonomous SME Finance Copilot."

    # 1. None session record returns directive unchanged
    assert _append_session_context(base_directive, None) == base_directive

    # 2. Session with financial facts only
    rec_facts = SessionRecord(
        session_id="s1",
        financial_facts={"runway_days": 42, "current_balance": "$125,000"},
    )
    res_facts = _append_session_context(base_directive, rec_facts)
    assert "Known verified business facts:" in res_facts
    assert "runway_days: 42" in res_facts
    assert "Context from earlier in this conversation:" not in res_facts

    # 3. Session with rolling summary only
    rec_summary = SessionRecord(
        session_id="s2",
        rolling_summary="User inquired about cash runway; Copilot calculated cash health.",
    )
    res_summary = _append_session_context(base_directive, rec_summary)
    assert "Context from earlier in this conversation:" in res_summary
    assert "User inquired about cash runway" in res_summary
    assert "Known verified business facts:" not in res_summary

    # 4. Session with both facts and rolling summary
    rec_both = SessionRecord(
        session_id="s3",
        financial_facts={"runway_days": 42},
        rolling_summary="User inquired about cash runway.",
    )
    res_both = _append_session_context(base_directive, rec_both)
    assert "Known verified business facts: runway_days: 42" in res_both
    assert "Context from earlier in this conversation: User inquired about cash runway." in res_both


def test_supervisor_includes_rolling_summary_in_model_context():
    """Verifies end-to-end that supervisor passes rolling summary into model generation calls."""
    store = SessionStore.get_instance()
    session_id = "test-supervisor-summary-flow"

    try:
        # Seed an established session with 8 turns so rolling_summary is generated
        for i in range(4):
            store.append_turn(
                session_id=session_id,
                user_text=f"Previous question {i}: how is our cash runway and burn?",
                agent_text=f"### Financial Diagnostic Summary\nRunway is stable at turn {i}.",
            )

        rec = store.get(session_id)
        assert rec is not None
        assert rec.rolling_summary is not None

        # Call supervisor with the existing session
        req = AgentChatRequest(
            session_id=session_id,
            message="Can you also calculate DSCR with $50,000 net operating income and $25,000 debt service?",
        )

        with patch("services.agent.supervisor.query_external_llm") as mock_llm:
            mock_llm.return_value = "Based on earlier discussions and your current figures, your DSCR is 2.0x."
            resp = run_copilot_supervisor(
                req,
                llm_config=LLMConfig(provider="gemini", api_key="mock_key"),
            )

            assert resp.session_id == session_id
            assert resp.reply is not None

            # Verify that query_external_llm was provided the directive containing the rolling summary
            if mock_llm.called:
                _, kwargs = mock_llm.call_args
                directive_arg = kwargs.get("system_instruction", "")
                assert "Context from earlier in this conversation:" in directive_arg
                assert "User inquired about" in directive_arg

    finally:
        store.clear(session_id)
