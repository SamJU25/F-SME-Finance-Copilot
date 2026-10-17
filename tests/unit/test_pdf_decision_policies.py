import pytest
from services.decision.registry import DecisionEngineRegistry
from services.decision.adapters.fallback_adapter import FallbackRuleAdapter
from services.decision.adapters.zen_adapter import ZenRulesAdapter
from services.decision.types import DecisionDomain, DecisionRequest


@pytest.fixture
def registry():
    DecisionEngineRegistry.reset_instance()
    return DecisionEngineRegistry.get_instance()


@pytest.fixture
def fallback_engine():
    return FallbackRuleAdapter()


@pytest.fixture
def zen_engine():
    try:
        return ZenRulesAdapter()
    except Exception:
        pytest.skip("zen-engine not available in current environment")


class TestBankStatementProfilePolicy:
    @pytest.mark.parametrize(
        "header,expected_col,expected_mult",
        [
            ("Transaction Date", "DATE", 0),
            ("Posting Date", "DATE", 0),
            ("Description", "DESCRIPTION", 0),
            ("Memo / Reference", "DESCRIPTION", 0),
            ("Deposits & Additions", "INFLOW", 1),
            ("Credit (+)", "INFLOW", 1),
            ("Withdrawals & Debits", "OUTFLOW", -1),
            ("Checks", "OUTFLOW", -1),
            ("Ending Daily Balance", "BALANCE", 0),
            ("Ledger Balance", "BALANCE", 0),
            ("Transaction Amount", "SIGNED_AMOUNT", 1),
            ("Unrecognized Column XYZ", "UNKNOWN", 0),
        ],
    )
    def test_bank_statement_profile_fallback(self, fallback_engine, header, expected_col, expected_mult):
        req = DecisionRequest(
            domain=DecisionDomain.BANK_STATEMENT_PROFILE,
            input_state={"header_clean": header.lower()},
            execution_mode="DETERMINISTIC_ONLY",
        )
        res = fallback_engine.evaluate(req)
        assert res.selected_choice == expected_col
        assert res.output_payload["canonical_column"] == expected_col
        assert res.output_payload["sign_multiplier"] == expected_mult

    @pytest.mark.parametrize(
        "header,expected_col,expected_mult",
        [
            ("Transaction Date", "DATE", 0),
            ("Posting Date", "DATE", 0),
            ("Description", "DESCRIPTION", 0),
            ("Deposits & Additions", "INFLOW", 1),
            ("Checks & Debits", "OUTFLOW", -1),
            ("Ending Daily Balance", "BALANCE", 0),
            ("Transaction Amount", "SIGNED_AMOUNT", 1),
            ("Unrecognized Column XYZ", "UNKNOWN", 0),
        ],
    )
    def test_bank_statement_profile_zen(self, zen_engine, header, expected_col, expected_mult):
        req = DecisionRequest(
            domain=DecisionDomain.BANK_STATEMENT_PROFILE,
            input_state={"header_clean": header.lower()},
            execution_mode="DETERMINISTIC_ONLY",
        )
        res = zen_engine.evaluate(req)
        assert res.selected_choice == expected_col
        assert res.output_payload["canonical_column"] == expected_col
        assert res.output_payload["sign_multiplier"] == expected_mult


class TestReconciliationTolerancePolicy:
    @pytest.mark.parametrize(
        "delta_cents,fee_match,expected_status,expected_allow,expected_sev",
        [
            (0, False, "BALANCED", True, "NONE"),
            (1, False, "ROUNDING_TOLERANCE", True, "LOW"),
            (2, False, "ROUNDING_TOLERANCE", True, "LOW"),
            (1500, True, "INFERRED_BANK_FEE", True, "LOW"),
            (2500, True, "INFERRED_BANK_FEE", True, "LOW"),
            (500, False, "RECONCILIATION_BREAK", False, "HIGH"),
            (10000, False, "RECONCILIATION_BREAK", False, "HIGH"),
        ],
    )
    def test_reconciliation_tolerance_fallback(
        self, fallback_engine, delta_cents, fee_match, expected_status, expected_allow, expected_sev
    ):
        req = DecisionRequest(
            domain=DecisionDomain.RECONCILIATION_TOLERANCE,
            input_state={"delta_cents": delta_cents, "inferred_fee_match": fee_match},
            execution_mode="DETERMINISTIC_ONLY",
        )
        res = fallback_engine.evaluate(req)
        assert res.selected_choice == expected_status
        assert res.output_payload["status"] == expected_status
        assert res.output_payload["allow_auto_reconcile"] == expected_allow
        assert res.output_payload["severity"] == expected_sev

    @pytest.mark.parametrize(
        "delta_cents,fee_match,expected_status,expected_allow,expected_sev",
        [
            (0, False, "BALANCED", True, "NONE"),
            (1, False, "ROUNDING_TOLERANCE", True, "LOW"),
            (2, False, "ROUNDING_TOLERANCE", True, "LOW"),
            (1500, True, "INFERRED_BANK_FEE", True, "LOW"),
            (500, False, "RECONCILIATION_BREAK", False, "HIGH"),
        ],
    )
    def test_reconciliation_tolerance_zen(
        self, zen_engine, delta_cents, fee_match, expected_status, expected_allow, expected_sev
    ):
        req = DecisionRequest(
            domain=DecisionDomain.RECONCILIATION_TOLERANCE,
            input_state={"delta_cents": delta_cents, "inferred_fee_match": fee_match},
            execution_mode="DETERMINISTIC_ONLY",
        )
        res = zen_engine.evaluate(req)
        assert res.selected_choice == expected_status
        assert res.output_payload["status"] == expected_status
        assert res.output_payload["allow_auto_reconcile"] == expected_allow
        assert res.output_payload["severity"] == expected_sev


class TestExpenseCategorizationPolicy:
    @pytest.mark.parametrize(
        "memo,expected_cat,expected_essential",
        [
            ("GUSTO PAYROLL 0315 REF 8812", "PAYROLL", True),
            ("ADP TOTALSOURCE WAGES", "PAYROLL", True),
            ("REGUS COMMERCIAL RENT MARCH", "RENT", True),
            ("WEWORK OFFICE LEASE", "RENT", True),
            ("SBA LOAN DEBT SERVICE", "DEBT_SERVICE", True),
            ("IRS US TREASURY TAX PAYMENT", "TAX", True),
            ("COMCAST BUSINESS INTERNET", "UTILITIES", True),
            ("STRIPE PAYOUT SETTLEMENT", "REVENUE", False),
            ("RANDOM HARDWARE STORE VISIT", "GENERAL_EXPENSE", False),
        ],
    )
    def test_expense_categorization_fallback(self, fallback_engine, memo, expected_cat, expected_essential):
        req = DecisionRequest(
            domain=DecisionDomain.EXPENSE_TRIAGE,
            input_state={"memo_clean": memo.lower()},
            execution_mode="DETERMINISTIC_ONLY",
        )
        res = fallback_engine.evaluate(req)
        assert res.selected_choice == expected_cat
        assert res.output_payload["category"] == expected_cat
        assert res.output_payload["is_essential_operating"] == expected_essential

    @pytest.mark.parametrize(
        "memo,expected_cat,expected_essential",
        [
            ("GUSTO PAYROLL 0315 REF 8812", "PAYROLL", True),
            ("WEWORK OFFICE LEASE", "RENT", True),
            ("SBA LOAN DEBT SERVICE", "DEBT_SERVICE", True),
            ("STRIPE PAYOUT SETTLEMENT", "REVENUE", False),
            ("RANDOM HARDWARE STORE VISIT", "GENERAL_EXPENSE", False),
        ],
    )
    def test_expense_categorization_zen(self, zen_engine, memo, expected_cat, expected_essential):
        req = DecisionRequest(
            domain=DecisionDomain.EXPENSE_TRIAGE,
            input_state={"memo_clean": memo.lower()},
            execution_mode="DETERMINISTIC_ONLY",
        )
        res = zen_engine.evaluate(req)
        assert res.selected_choice == expected_cat
        assert res.output_payload["category"] == expected_cat
        assert res.output_payload["is_essential_operating"] == expected_essential
