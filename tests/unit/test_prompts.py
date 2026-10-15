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
