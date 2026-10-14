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
