from datetime import date
from decimal import Decimal

import pytest

from services.ingestion.csv_parser import CSVIngestionError, DemoTransaction, parse_bank_csv

HEADER = "transaction_id,posted_on,amount,currency,description,closing_balance\n"


def test_parse_bank_csv_accepts_valid_rows_and_rejects_invalid_row_with_line_number():
    content = (HEADER +
        "tx-1,2026-10-01,-10.00,USD,Office supplies,90.00\n" +
        "tx-2,2026-10-02,25.00,USD,Customer payment,115.00\n" +
        "tx-3,not-a-date,-1.00,USD,Invalid date,114.00\n").encode()

    result = parse_bank_csv(content)

    assert result.currency == "USD"
    assert len(result.accepted_rows) == 2
    assert result.accepted_rows[0].amount == Decimal("-10.00")
    assert result.accepted_rows[1].posted_on == date(2026, 10, 2)
    assert isinstance(result.accepted_rows[0], DemoTransaction)
    assert [(row.row_number, row.reason_code) for row in result.rejected_rows] == [(4, "INVALID_DATE")]


def test_parse_bank_csv_rejects_duplicate_ids_and_out_of_order_dates():
    content = (HEADER +
        "tx-1,2026-10-02,-10.00,USD,First,90.00\n" +
        "tx-1,2026-10-03,-5.00,USD,Duplicate,85.00\n" +
        "tx-2,2026-10-01,-2.00,USD,Out of order,83.00\n").encode()

    result = parse_bank_csv(content)

    assert [(row.row_number, row.reason_code) for row in result.rejected_rows] == [
        (3, "DUPLICATE_TRANSACTION_ID"), (4, "OUT_OF_ORDER_DATE")
    ]


def test_parse_bank_csv_reports_stable_file_errors():
    with pytest.raises(CSVIngestionError) as invalid_header:
        parse_bank_csv(b"wrong,header\n")
    assert invalid_header.value.code == "INVALID_HEADER"

    with pytest.raises(CSVIngestionError) as invalid_encoding:
        parse_bank_csv(b"\xff\xfe")
    assert invalid_encoding.value.code == "INVALID_ENCODING"

    with pytest.raises(CSVIngestionError) as no_valid_rows:
        parse_bank_csv((HEADER + "bad,not-a-date,1.0,USD,x,1.0\n").encode())
    assert no_valid_rows.value.code == "NO_VALID_ROWS"


def test_parse_bank_csv_rejects_mixed_currencies():
    content = (HEADER +
        "tx-1,2026-10-01,-10.00,USD,First,90.00\n" +
        "tx-2,2026-10-02,-5.00,EUR,Second,85.00\n").encode()

    with pytest.raises(CSVIngestionError) as mixed_currencies:
        parse_bank_csv(content)
    assert mixed_currencies.value.code == "MIXED_CURRENCIES"


def test_parse_bank_csv_does_not_treat_invalid_currency_row_as_mixed_currency():
    content = (HEADER +
        "tx-1,2026-10-01,-10.00,USD,First,90.00\n" +
        "tx-2,2026-10-02,-5.00,usd,Invalid currency,85.00\n").encode()

    result = parse_bank_csv(content)

    assert result.currency == "USD"
    assert [(row.row_number, row.reason_code) for row in result.rejected_rows] == [(3, "INVALID_CURRENCY")]


def test_parse_universal_chase_and_bofa_format():
    content = (
        "Date,Description,Amount,Running Bal.\n"
        "10/01/2026,Office Supplies,-45.50,954.50\n"
        "10/02/2026,Client Retainer,1500.00,2454.50\n"
    ).encode()

    result = parse_bank_csv(content)

    assert result.currency == "USD"
    assert len(result.accepted_rows) == 2
    assert result.accepted_rows[0].posted_on == date(2026, 10, 1)
    assert result.accepted_rows[0].amount == Decimal("-45.50")
    assert result.accepted_rows[0].closing_balance == Decimal("954.50")
    assert result.accepted_rows[0].transaction_id.startswith("tx_")
    assert result.accepted_rows[1].amount == Decimal("1500.00")
    assert result.accepted_rows[1].closing_balance == Decimal("2454.50")


def test_parse_universal_separate_debit_credit_format():
    content = (
        "Date,Description,Debit,Credit,Balance\n"
        "01/10/2026,Vendor Payment,300.00,,9700.00\n"
        "02/10/2026,Customer Invoice Wire,,1200.00,10900.00\n"
    ).encode()

    result = parse_bank_csv(content)

    assert result.currency == "USD"
    assert len(result.accepted_rows) == 2
    assert result.accepted_rows[0].amount == Decimal("-300.00")
    assert result.accepted_rows[0].closing_balance == Decimal("9700.00")
    assert result.accepted_rows[1].amount == Decimal("1200.00")
    assert result.accepted_rows[1].closing_balance == Decimal("10900.00")


def test_parse_universal_stripe_payment_processor_format():
    content = (
        "id,Created (UTC),Amount,Fee,Net,Currency,Description,Status\n"
        "ch_101,2026-10-01 12:00:00,100.00,3.20,96.80,USD,Client Subscription,Paid\n"
        "ch_102,2026-10-02 15:30:00,250.00,7.55,242.45,USD,Consulting Retainer,Paid\n"
    ).encode()

    result = parse_bank_csv(content)

    assert result.currency == "USD"
    assert len(result.accepted_rows) == 2
    # Net amount used
    assert result.accepted_rows[0].transaction_id == "ch_101"
    assert result.accepted_rows[0].amount == Decimal("96.80")
    assert result.accepted_rows[0].closing_balance == Decimal("96.80")
    assert result.accepted_rows[1].amount == Decimal("242.45")
    # Cumulative balance reconstructed
    assert result.accepted_rows[1].closing_balance == Decimal("339.25")


def test_parse_universal_founder_accounting_parentheses_format():
    content = (
        "When,Who,How Much\n"
        "2026-10-01,Initial Seed Capital,$5000.00\n"
        "2026-10-02,Server Hosting,($150.00)\n"
    ).encode()

    result = parse_bank_csv(content)

    assert result.currency == "USD"
    assert len(result.accepted_rows) == 2
    assert result.accepted_rows[0].amount == Decimal("5000.00")
    assert result.accepted_rows[0].closing_balance == Decimal("5000.00")
    assert result.accepted_rows[1].amount == Decimal("-150.00")
    assert result.accepted_rows[1].closing_balance == Decimal("4850.00")


def test_parse_universal_statement_with_metadata_headers():
    content = (
        "Commercial Checking Account: *******5678\n"
        "Statement Period: 2026-10-01 to 2026-10-31\n"
        "Date,Description,Amount,Running Bal.\n"
        "2026-10-01,Payroll Expense,-2000.00,8000.00\n"
        "2026-10-02,Accounts Receivable,4500.00,12500.00\n"
    ).encode()

    result = parse_bank_csv(content)

    assert result.currency == "USD"
    assert len(result.accepted_rows) == 2
    assert result.accepted_rows[0].amount == Decimal("-2000.00")
    assert result.accepted_rows[1].closing_balance == Decimal("12500.00")


def test_parse_multiple_bank_csv_consecutive_months():
    from services.ingestion.csv_parser import parse_multiple_bank_csv

    sept_csv = (
        "Date,Description,Amount,Running Bal.\n"
        "2026-09-15,Sept Invoice,3000.00,13000.00\n"
        "2026-09-30,Sept Software,-200.00,12800.00\n"
    ).encode()

    oct_csv = (
        "Date,Description,Amount,Running Bal.\n"
        "2026-10-05,Oct Client Wire,4000.00,16800.00\n"
        "2026-10-10,Oct Rent,-1500.00,15300.00\n"
    ).encode()

    result = parse_multiple_bank_csv([("sept.csv", sept_csv), ("oct.csv", oct_csv)])

    assert result.currency == "USD"
    assert len(result.accepted_rows) == 4
    # Chronological sort across months
    assert result.accepted_rows[0].posted_on == date(2026, 9, 15)
    assert result.accepted_rows[3].posted_on == date(2026, 10, 10)
    assert result.accepted_rows[3].closing_balance == Decimal("15300.00")


def test_parse_multiple_bank_csv_multi_account_treasury():
    from services.ingestion.csv_parser import parse_multiple_bank_csv

    chase_csv = (
        "Date,Description,Amount,Running Bal.\n"
        "2026-10-01,Client Wire,10000.00,20000.00\n"
        "2026-10-05,Office Lease,-2000.00,18000.00\n"
    ).encode()

    stripe_csv = (
        "id,Created (UTC),Amount,Fee,Net,Currency,Description,Status\n"
        "ch_a,2026-10-02 10:00:00,500.00,15.00,485.00,USD,Product Sale,Paid\n"
        "ch_b,2026-10-06 14:00:00,1000.00,30.00,970.00,USD,Product Sale,Paid\n"
    ).encode()

    result = parse_multiple_bank_csv([("chase.csv", chase_csv), ("stripe.csv", stripe_csv)])

    assert result.currency == "USD"
    assert len(result.accepted_rows) == 4
    # Closing balance reflects combined liquidity across both accounts:
    # Chase ending: 18000.00, Stripe ending: 1455.00 -> Combined: 19455.00
    assert result.accepted_rows[-1].closing_balance == Decimal("19455.00")


def test_parse_multiple_bank_csv_rejects_mixed_currencies():
    from services.ingestion.csv_parser import parse_multiple_bank_csv

    usd_csv = (
        "Date,Description,Amount,Running Bal.\n"
        "2026-10-01,Deposit,1000.00,5000.00\n"
    ).encode()

    eur_csv = (
        "Date,Description,Amount,Currency,Running Bal.\n"
        "2026-10-02,Deposit,1000.00,EUR,5000.00\n"
    ).encode()

    with pytest.raises(CSVIngestionError) as exc_info:
        parse_multiple_bank_csv([("usd.csv", usd_csv), ("eur.csv", eur_csv)])
    assert exc_info.value.code == "MIXED_CURRENCIES"


def test_parse_dynamic_german_statement_content_profiling():
    # Semicolon delimited German bank export with German non-English headers
    # Mathematical profiler proves Saldo[1] - Saldo[0] == Betrag[1] (2379.50 - 1879.50 == 500.00)
    german_csv = (
        "Buchungstag;Verwendungszweck;Betrag;Saldo\n"
        "2026-10-01;Buerobedarf;-120,50;1879,50\n"
        "2026-10-02;Zahlung Kunde;500,00;2379,50\n"
    ).encode()

    result = parse_bank_csv(german_csv)

    assert result.currency == "USD"
    assert len(result.accepted_rows) == 2
    assert result.accepted_rows[0].posted_on == date(2026, 10, 1)
    assert result.accepted_rows[0].amount == Decimal("-120.50")
    assert result.accepted_rows[0].closing_balance == Decimal("1879.50")
    assert result.accepted_rows[1].amount == Decimal("500.00")
    assert result.accepted_rows[1].closing_balance == Decimal("2379.50")


def test_parse_dynamic_headerless_csv_content_profiling():
    # Completely headerless CSV: row 1 is already transaction data
    headerless_csv = (
        "2026-10-01,Office Supplies,-45.50,954.50\n"
        "2026-10-02,Client Retainer,1500.00,2454.50\n"
        "2026-10-03,Software Tool,-50.00,2404.50\n"
    ).encode()

    result = parse_bank_csv(headerless_csv)

    assert len(result.accepted_rows) == 3
    assert result.accepted_rows[0].posted_on == date(2026, 10, 1)
    assert result.accepted_rows[0].amount == Decimal("-45.50")
    assert result.accepted_rows[0].closing_balance == Decimal("954.50")
    assert result.accepted_rows[2].amount == Decimal("-50.00")
    assert result.accepted_rows[2].closing_balance == Decimal("2404.50")


def test_dynamic_profiler_mathematical_balance_invariant():
    from services.ingestion.dynamic_profiler import profile_table_content

    # Matrix with arbitrary non-standard column names
    rows = [
        ["col_alpha", "col_beta", "col_gamma", "col_delta"],
        ["2026-10-01", "Vendor Payment", "-300.00", "4700.00"],
        ["2026-10-02", "Client Retainer", "1000.00", "5700.00"],
        ["2026-10-03", "Software Cloud", "-100.00", "5600.00"],
    ]

    schema = profile_table_content(rows[1:])
    assert schema is not None
    assert schema.date_col == 0
    assert schema.amount_col == 2
    assert schema.balance_col == 3
    assert schema.confidence == 1.0
    assert schema.detection_method == "mathematical_balance_proof"


def test_dynamic_profiler_debit_credit_balance_invariant():
    from services.ingestion.dynamic_profiler import profile_table_content

    rows = [
        ["ColA", "ColB", "ColC", "ColD", "ColE"],
        ["2026-10-01", "Supplier Invoice", "250.00", "", "9750.00"],
        ["2026-10-02", "Customer Wire", "", "1500.00", "11250.00"],
    ]

    schema = profile_table_content(rows[1:])
    assert schema is not None
    assert schema.date_col == 0
    assert schema.debit_col == 2
    assert schema.credit_col == 3
    assert schema.balance_col == 4
    assert schema.confidence == 1.0
    assert schema.detection_method == "mathematical_debit_credit_balance_proof"


def test_llm_schema_resolver_structured_mapping(monkeypatch):
    from services.ingestion.llm_schema_resolver import resolve_schema_with_llm
    from services.agent.schema import LLMConfig

    # Mock query_external_llm to simulate an intelligent LLM response for ambiguous columns
    def mock_query(prompt, system_instruction, config):
        return '{"date_col": 0, "amount_col": 3, "debit_col": null, "credit_col": null, "balance_col": 4, "description_col": 1, "currency_col": null}'

    import services.ingestion.llm_schema_resolver as resolver_module
    monkeypatch.setattr(resolver_module, "query_external_llm", mock_query)

    dummy_config = LLMConfig(provider="gemini", api_key="test-key", model_name="gemini-2.5-flash")
    sample_rows = [
        ["Date", "Notes", "Category", "Net Movement", "Total Balance"],
        ["2026-10-01", "Client A", "Revenue", "5000.00", "15000.00"],
    ]

    schema = resolve_schema_with_llm(sample_rows, llm_config=dummy_config)
    assert schema is not None
    assert schema.date_col == 0
    assert schema.amount_col == 3
    assert schema.balance_col == 4
    assert schema.description_col == 1
    assert schema.confidence == 0.95
    assert schema.detection_method == "llm_semantic_resolution"


