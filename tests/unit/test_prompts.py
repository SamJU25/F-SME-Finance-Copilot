"""Unit tests for CFO personality prompts and response sanitization.

Verifies:
1. Stripping conversational pleasantries and throat-clearing openers.
2. Preserving genuine professional CFO domain advice.
3. System prompts enforce non-hallucinatory persona contracts.
"""

from services.agent.prompts import (
    COPILOT_PERSONA_BASE,
    get_cash_diagnostic_prompt,
    get_conversational_system_prompt,
    get_credit_underwriting_prompt,
    sanitize_cfo_reply,
)


def test_sanitize_cfo_reply_removes_throat_clearing():
    """Verify throat-clearing phrases are deterministically stripped."""
    dirty_replies = [
        (
            "Hello! As a financial copilot, your runway is 45 days. You should reduce discretionary burn.",
            "Your runway is 45 days. You should reduce discretionary burn.",
        ),
        (
            "I would be happy to help with that. To underwrite your business, upload your bank statement.",
            "To underwrite your business, upload your bank statement.",
        ),
        (
            "Certainly! Here is the breakdown: Daily Average Balance is $25,000.",
            "Daily Average Balance is $25,000.",
        ),
        (
            "Sure thing! Based on your statements, your cash conversion cycle is 42 days.",
            "Your cash conversion cycle is 42 days.",
        ),
        (
            "I'd love to assist you. Your burn rate requires immediate attention.",
            "Your burn rate requires immediate attention.",
        ),
        (
            "Here's what you need to know: WeBank credit facilities require at least $10,000 DAB.",
            "WeBank credit facilities require at least $10,000 DAB.",
        ),
    ]

    for dirty, expected in dirty_replies:
        cleaned = sanitize_cfo_reply(dirty)
        assert cleaned == expected, f"Expected '{expected}', got '{cleaned}'"


def test_sanitize_cfo_reply_removes_user_screenshot_slop():
    """Verify quotes, slop openers, metric echoes, and fluff from user screenshot are stripped."""
    slop_input = (
        '"Your bank statement CSV has been successfully uploaded. Now, let\'s dive into the numbers. Here are the results:\n\n'
        '- **Current Balance**: $9,500.00\n'
        '- **Average Daily Burn**: $100.00/day\n'
        '- **Estimated Historical Runway**: 95 days\n'
        '- **Status**: WATCH (Threshold: 30 days)\n'
        '- **Healthiest Liquidity**: Operations solvent across all 90-day forecast windows\n'
        '- **Projected 90-day Reserve**: $500.00\n\n'
        'Operations remain solvent across the 90-day window, but your $500 reserve provides minimal cushion.\n\n'
        'These verified accounting metrics provide a clear picture of your business\'s financial health. '
        'With this information, you can make informed decisions to optimize your cash runway, manage your working capital effectively, and mitigate potential cash deficits."'
    )
    expected = "Operations remain solvent across the 90-day window, but your $500 reserve provides minimal cushion."
    assert sanitize_cfo_reply(slop_input) == expected


def test_sanitize_cfo_reply_strips_dangling_list_numbers():
    """Verify dangling list markers at the end of generation are trimmed."""
    truncated = (
        "1. Data Collection: The SME provides access to financial records.\n"
        "2."
    )
    expected = "1. Data Collection: The SME provides access to financial records."
    assert sanitize_cfo_reply(truncated) == expected



def test_prompts_contain_cfo_invariants():
    """Verify system prompts contain mandatory institutional and working-capital directives."""
    conv_prompt = get_conversational_system_prompt()
    assert "Chief Financial Officer (CFO)" in conv_prompt
    assert "never say 'I would be happy to'" in conv_prompt
    assert "small and medium enterprise (SME) owners" in conv_prompt

    diag_prompt = get_cash_diagnostic_prompt({"runway_days": 45, "current_balance": "50000"})
    assert "never contradict or approximate verified figures" in diag_prompt
    assert "Zero Numerical Hallucinations" in diag_prompt

    uw_prompt = get_credit_underwriting_prompt({"dab": "25000", "max_limit": "50000"})
    assert "Daily Average Balance (DAB)" in uw_prompt
    assert "APR" in uw_prompt


def test_mask_pii_banking_identifiers():
    """Verify banking-grade PII scrub covers EIN, SSN, bank accounts, cards, phones, and IBANs."""
    from services.agent.llm_bridge import mask_pii

    raw_text = (
        "Client Apex Corp (EIN: 12-3456789, SSN: 123-45-6789) "
        "transferred funds to account 987654321098 via card 4111-2222-3333-4444. "
        "Contact: cfo@apex.com or (555) 019-2834. "
        "International IBAN: GB29NWBK60161331926819."
    )
    scrubbed = mask_pii(raw_text)
    assert "12-3456789" not in scrubbed
    assert "123-45-6789" not in scrubbed
    assert "987654321098" not in scrubbed
    assert "4111-2222-3333-4444" not in scrubbed
    assert "cfo@apex.com" not in scrubbed
    assert "(555) 019-2834" not in scrubbed
    assert "GB29NWBK60161331926819" not in scrubbed

    assert "[REDACTED_TAX_ID]" in scrubbed
    assert "[REDACTED_ACCOUNT]" in scrubbed
    assert "[REDACTED_EMAIL]" in scrubbed
    assert "[REDACTED_PHONE]" in scrubbed
    assert "[REDACTED_IBAN]" in scrubbed


def test_chat_history_item_resiliency():
    """Verify ChatHistoryItem handles role/sender, content/text, and ignores extraneous metadata."""
    from services.agent.schema import ChatHistoryItem

    # Standard
    item1 = ChatHistoryItem(role="user", text="Hello")
    assert item1.role == "user"
    assert item1.text == "Hello"

    # sender alias + extra client fields
    item2 = ChatHistoryItem.model_validate({"sender": "assistant", "content": "Welcome", "timestamp": 12345678})
    assert item2.role == "assistant"
    assert item2.text == "Welcome"


def test_api_key_detection_and_guidance():
    """Verify raw API keys pasted into chat are intercepted with security guidance."""
    from services.agent.supervisor import inspect_for_api_key, run_copilot_supervisor
    from services.agent.schema import AgentChatRequest

    # Test key detection regex
    assert inspect_for_api_key("sk-ant-api03-1234567890abcdefghijklmnopqrstuvwxyz")
    assert inspect_for_api_key("sk-proj-1234567890abcdefghijklmnopqrstuvwxyz")
    assert inspect_for_api_key("AIzaSyD1234567890abcdefghijklmnopqrstuvwxyz123")
    assert inspect_for_api_key("gsk_1234567890abcdefghijklmnopqrstuvwxyz")
    assert not inspect_for_api_key("What is our current monthly burn?")

    # Test supervisor response
    req = AgentChatRequest(message="Here is my API key: sk-ant-api03-1234567890abcdefghijklmnopqrstuvwxyz")
    res = run_copilot_supervisor(req)
    assert res.intent_detected == "CREDENTIAL_SECURITY_ALERT"
    assert "Security Alert: An API key or secret token was detected" in res.reply
    assert "AI Provider" in res.reply
    assert res.requires_biometric_hitl is False


def test_mask_pii_redacts_api_keys():
    """Verify mask_pii redacts API keys from prompt strings."""
    from services.agent.llm_bridge import mask_pii

    sample = "Please use key sk-proj-1234567890abcdefghijklmnopqrstuvwxyz to analyze."
    scrubbed = mask_pii(sample)
    assert "sk-proj-1234567890" not in scrubbed
    assert "[REDACTED_API_KEY]" in scrubbed


def test_pasted_csv_statement_in_chat():
    """Verify bank statement CSV pasted directly into message is parsed deterministically."""
    from services.agent.supervisor import run_copilot_supervisor
    from services.agent.schema import AgentChatRequest

    csv_text = (
        "transaction_id,posted_on,amount,currency,description,closing_balance\n"
        "tx_001,2026-01-01,1000.00,USD,Initial Client Invoice,10000.00\n"
        "tx_002,2026-01-05,-1500.00,USD,Supplier Raw Materials,8500.00\n"
        "tx_003,2026-01-10,-2000.00,USD,Warehouse Rent Expense,6500.00\n"
        "tx_004,2026-01-15,1000.00,USD,Customer Invoice Settlement,7500.00\n"
    )
    req = AgentChatRequest(message=f"Here is my statement:\n{csv_text}")
    res = run_copilot_supervisor(req)
    assert res.intent_detected == "CASH_DIAGNOSTIC"
    assert res.metrics is not None
    assert res.metrics.current_balance == "7500.00"
    assert res.metrics.runway_days == 75
    assert "7,500.00" in res.reply


def test_off_topic_query_redirects_to_cfo_domain():
    """Verify off-topic non-financial queries receive institutional CFO domain redirect."""
    from services.agent.dynamic_router import is_off_topic_query
    from services.agent.supervisor import run_copilot_supervisor
    from services.agent.schema import AgentChatRequest

    # 1. Unit detection tests across diverse non-financial topics (without hardcoding them)
    assert is_off_topic_query("How do I make chocolate chip cookies?")
    assert is_off_topic_query("Who won the 2022 World Cup?")
    assert is_off_topic_query("Tell me a funny joke")
    assert is_off_topic_query("Can you write a python script for quicksort?")
    assert is_off_topic_query("What is the weather in Tokyo?")
    assert is_off_topic_query("What causes quantum entanglement?")
    assert is_off_topic_query("How do I fix a leaking faucet in my bathroom?")
    assert is_off_topic_query("My tomato plants are dying what should I do?")
    assert is_off_topic_query("Can you recommend a romantic movie?")
    assert is_off_topic_query("Tell me about the Roman Empire")
    assert is_off_topic_query("What is the capital of France?")
    assert is_off_topic_query("What is the meaning of life?")

    # In-domain financial queries (even if mentioning outside industries)
    assert not is_off_topic_query("Hello, who are you?")
    assert not is_off_topic_query("What is my cash runway?")
    assert not is_off_topic_query("I run a bakery, our recipe ingredient costs are $4,000. What is our burn rate?")
    assert not is_off_topic_query("Our football club needs a $50,000 working capital loan.")
    assert not is_off_topic_query("How do I manage accounts receivable and DSO?")

    # 2. Supervisor execution without CSV
    req1 = AgentChatRequest(message="How do I bake chocolate chip cookies?")
    res1 = run_copilot_supervisor(req1)
    assert res1.intent_detected == "GENERAL_ASSISTANCE"
    assert "specialize exclusively in SME business liquidity" in res1.reply
    assert "unable to assist with non-financial topics" in res1.reply
    assert "cash runway, burn rate, overdraft forecast" in res1.reply
    assert res1.requires_biometric_hitl is False

    # 3. Supervisor execution even when CSV is already in session
    csv_sample = (
        "transaction_id,posted_on,amount,currency,description,closing_balance\n"
        "tx_1,2026-01-01,5000.00,USD,Client Retainer,10000.00\n"
    )
    req2 = AgentChatRequest(
        message="Who won the 2022 World Cup in football?",
        csv_content=csv_sample,
    )
    res2 = run_copilot_supervisor(req2)
    assert res2.intent_detected == "GENERAL_ASSISTANCE"
    assert "specialize exclusively in SME business liquidity" in res2.reply
    assert "unable to assist with non-financial topics" in res2.reply
    assert res2.metrics is None


def test_is_ai_disclaimer_vector_detection():
    """Verify vector semantic detection flags unhelpful AI disclaimers and preserves real CFO recommendations."""
    from services.agent.dynamic_router import is_ai_disclaimer

    # Disclaimers / refusals
    assert is_ai_disclaimer("I cannot access your bank records.")
    assert is_ai_disclaimer("I am not privy to private banking statements.")
    assert is_ai_disclaimer("I do not have access to your bank account.")
    assert is_ai_disclaimer("As an AI, I cannot provide personal financial data.")
    assert is_ai_disclaimer("I cannot check your account balance.")

    # Legitimate strategic financial recommendations
    assert not is_ai_disclaimer("Your current burn rate is sustainable if you maintain healthy accounts receivable.")
    assert not is_ai_disclaimer("To extend your cash runway, accelerate collections on overdue customer invoices.")
    assert not is_ai_disclaimer("Consider drawing down $25,000 from your prime line of credit to buffer against upcoming commitments.")
    assert not is_ai_disclaimer("With a Daily Average Balance of $25,000, your business qualifies for prime working capital loans.")


def test_pasted_csv_dynamic_intent_routing():
    """Verify pasted CSVs route dynamically to credit underwriting or cash diagnostics without keyword lists."""
    from services.agent.schema import AgentChatRequest
    from services.agent.supervisor import run_copilot_supervisor

    raw_csv = (
        "transaction_id,posted_on,amount,currency,description,closing_balance\n"
        "tx_001,2026-01-01,1000.00,USD,Initial Client Invoice,10000.00\n"
        "tx_002,2026-01-05,-1500.00,USD,Supplier Raw Materials,8500.00\n"
        "tx_003,2026-01-10,-2000.00,USD,Warehouse Rent Expense,6500.00\n"
        "tx_004,2026-01-15,1000.00,USD,Customer Invoice Settlement,7500.00\n"
    )

    # 1. Pasted CSV with financing inquiry -> CREDIT_UNDERWRITING
    req_credit = AgentChatRequest(message=f"What financing facilities can our company qualify for?\n{raw_csv}")
    res_credit = run_copilot_supervisor(req_credit)
    assert res_credit.intent_detected == "CREDIT_UNDERWRITING"
    assert res_credit.metrics is not None
    assert len(res_credit.matched_options) >= 1

    # 2. Raw pasted CSV alone -> CASH_DIAGNOSTIC
    req_raw = AgentChatRequest(message=raw_csv)
    res_raw = run_copilot_supervisor(req_raw)
    assert res_raw.intent_detected == "CASH_DIAGNOSTIC"
    assert res_raw.metrics is not None
    assert res_raw.metrics.current_balance == "7500.00"


def test_vector_greeting_routing_zero_keywords():
    """Verify greetings classify into GENERAL_ASSISTANCE via semantic embeddings without keyword checks."""
    from services.agent.dynamic_router import FastEmbedSemanticRouter

    router = FastEmbedSemanticRouter.get_instance()
    for greeting in ["Hello", "Good morning", "Good afternoon", "Hi there", "Hey, who are you?"]:
        intent, _, _ = router.classify(greeting)
        assert intent == "GENERAL_ASSISTANCE", f"Failed for '{greeting}': got {intent}"





