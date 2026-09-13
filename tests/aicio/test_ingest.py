"""Statement parsing: what it reads, and what it refuses to guess."""

from __future__ import annotations

import io
import zipfile
from datetime import date

import pytest

from aicio.domain import AssetType, TxnType
from aicio.ingest import parse_statement, sniff_format
from aicio.ingest.cas import parse_cas
from aicio.ingest.csv_statement import guess_asset_type, guess_txn_type, map_columns, parse_csv
from aicio.ingest.normalize import Correction, normalise, resolve_asset
from aicio.ingest.parser import read_date
from aicio.ingest.pdf_text import PdfError, extract_text
from aicio.ingest.xlsx import XlsxError, parse_xlsx, read_rows
from aicio.domain import Asset

HOLDINGS_CSV = """Scheme Name,ISIN,Folio Number,Units,NAV,Average Cost,Market Value,Category
Parag Parikh Flexi Cap Fund - Direct Growth,INF879O01027,12345/67,1520.4567,78.12,45.10,118777.48,Flexi Cap
HDFC Liquid Fund - Direct Growth,INF179K01XQ0,998877,120.0000,4800.00,4500.00,576000.00,Liquid
Total,,,,,,694777.48,
"""


def test_csv_holdings_parse_with_full_confidence():
    result = parse_csv(HOLDINGS_CSV, source_name="holdings.csv", user_id="u1")
    assert len(result.holdings) == 2
    assert result.confidence == 1.0
    assert result.clean


def test_totals_rows_do_not_become_phantom_holdings():
    result = parse_csv(HOLDINGS_CSV, user_id="u1")
    assert all("total" not in h.asset_id.lower() for h in result.holdings)
    assert len(result.holdings) == 2


def test_columns_are_matched_by_meaning_not_position():
    mapping = map_columns(["Trading Symbol", "Qty.", "Avg. Price", "LTP"])
    assert {"name", "units", "cost", "price"} <= mapping.keys()


def test_a_title_block_before_the_header_is_skipped():
    text = "My Broker Pvt Ltd\nHoldings as on 12-Sep-2026\n\n" + HOLDINGS_CSV
    result = parse_csv(text, user_id="u1")
    assert len(result.holdings) == 2


def test_unreadable_rows_become_exceptions_not_silence():
    text = HOLDINGS_CSV + "Broken Fund,INF000000001,555,not-a-number,10,10,100,Equity\n"
    result = parse_csv(text, user_id="u1")
    assert len(result.exceptions) == 1
    assert result.confidence < 1.0
    assert result.exceptions[0].suggestion


def test_a_row_with_no_price_or_value_is_rejected_rather_than_guessed():
    text = "Scheme Name,Units\nMystery Fund,100\n"
    result = parse_csv(text, user_id="u1")
    assert not result.holdings
    assert "price" in result.exceptions[0].reason


def test_missing_cost_basis_is_recorded_as_a_limitation():
    text = "Scheme Name,ISIN,Units,NAV\nSome Fund,INF000000001,100,50\n"
    result = parse_csv(text, user_id="u1")
    assert result.holdings
    assert any("cost basis" in note for note in result.notes)


def test_transaction_files_are_recognised_and_typed():
    text = (
        "Date,Scheme Name,Transaction Type,Units,NAV,Amount\n"
        "05-Jan-2025,Some Equity Fund,SIP Purchase,100.5,50.00,5025.00\n"
        "05-Feb-2025,Some Equity Fund,Redemption,50.0,55.00,2750.00\n"
    )
    result = parse_csv(text, user_id="u1")
    assert [t.txn_type for t in result.transactions] == [TxnType.SIP, TxnType.SELL]
    assert result.transactions[0].trade_date == date(2025, 1, 5)


@pytest.mark.parametrize("name,expected", [
    ("Mirae Asset ELSS Tax Saver Fund", AssetType.ELSS),
    ("HDFC Liquid Fund", AssetType.LIQUID_FUND),
    ("UTI Nifty 50 Index Fund", AssetType.INDEX_FUND),
    ("Nippon India Gold BeES ETF", AssetType.GOLD_ETF),
    ("ICICI Prudential Corporate Bond Fund", AssetType.DEBT_FUND),
    ("Parag Parikh Flexi Cap Fund", AssetType.EQUITY_FUND),
    ("Sovereign Gold Bond 2030", AssetType.SGB),
    ("RELIANCE", AssetType.STOCK),
])
def test_scheme_names_classify_themselves(name, expected):
    """Indian scheme names state their category by regulation, which makes
    name-based classification reliable here in a way it usually is not."""
    assert guess_asset_type(name) is expected


def test_switch_out_is_not_read_as_switch_in():
    assert guess_txn_type("Switch Out - to another scheme") is TxnType.SWITCH_OUT
    assert guess_txn_type("Switch In") is TxnType.SWITCH_IN


@pytest.mark.parametrize("raw,expected", [
    ("2026-09-12", date(2026, 9, 12)),
    ("12-Sep-2026", date(2026, 9, 12)),
    ("12/09/2026", date(2026, 9, 12)),      # day first: this is India-first
])
def test_dates_parse_without_swapping_day_and_month(raw, expected):
    assert read_date(raw) == expected


def test_unparseable_date_raises():
    with pytest.raises(ValueError):
        read_date("sometime last spring")


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------

def _workbook(rows: list[list[str]]) -> bytes:
    """A minimal but valid XLSX, built without a library."""
    cells = []
    for r, row in enumerate(rows, start=1):
        parts = "".join(
            f'<c r="{chr(64 + c)}{r}" t="inlineStr"><is><t>{v}</t></is></c>'
            for c, v in enumerate(row, start=1) if v != ""
        )
        cells.append(f'<row r="{r}">{parts}</row>')
    sheet = (
        '<?xml version="1.0"?><worksheet '
        'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(cells)}</sheetData></worksheet>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()


def test_xlsx_rows_preserve_gaps():
    """A gap read as a missing cell shifts every later column and produces a
    plausible, wrong portfolio."""
    data = _workbook([["A", "", "C"]])
    assert read_rows(data) == [["A", "", "C"]]


def test_xlsx_shares_the_csv_column_mapping():
    rows = [line.split(",") for line in HOLDINGS_CSV.strip().splitlines()]
    result = parse_xlsx(_workbook(rows), source_name="holdings.xlsx", user_id="u1")
    assert result.source_format == "xlsx"
    assert len(result.holdings) == 2


def test_a_corrupt_workbook_reports_rather_than_raises():
    result = parse_xlsx(b"not a zip", source_name="bad.xlsx")
    assert result.confidence == 0.0
    assert result.exceptions


# ---------------------------------------------------------------------------
# PDF and CAS
# ---------------------------------------------------------------------------

def test_encrypted_pdf_says_what_to_do_about_it():
    data = b"%PDF-1.4\n/Encrypt 1 0 R\nstream\nx\nendstream"
    with pytest.raises(PdfError, match="password-protected"):
        extract_text(data)


def test_a_scan_is_reported_as_a_scan():
    data = b"%PDF-1.4\nstream\n\nendstream\n"
    with pytest.raises(PdfError, match="scan"):
        extract_text(data)


CAS_TEXT = """
Consolidated Account Statement
01-Apr-2025 to 12-Sep-2026
PPFAS Mutual Fund
Folio No: 12345678 / 90   PAN: ABCDE1234F
INF879O01027 Parag Parikh Flexi Cap Fund - Direct Plan Growth
05-Jan-2026 SIP Purchase 25,000.00 320.1234 78.1200 1,520.4567
05-Feb-2026 Redemption 10,000.00 128.0000 78.1200 1,392.4567
Closing Unit Balance: 1,392.4567 NAV on 12-Sep-2026: INR 78.1200
"""


def test_cas_extracts_folios_schemes_and_history():
    result = parse_cas(CAS_TEXT, source_name="cas.pdf", user_id="u1")
    assert result.accounts and result.assets
    assert result.assets[0].isin == "INF879O01027"
    assert len(result.transactions) == 2
    assert result.holdings and float(result.holdings[0].units) == pytest.approx(1392.4567)


def test_folio_numbers_are_masked():
    result = parse_cas(CAS_TEXT, user_id="u1")
    masked = result.accounts[0].identifier_masked
    assert masked.endswith("8990") or masked.endswith("90")
    assert "*" in masked


def test_a_statement_we_cannot_read_says_so():
    result = parse_cas("Some unrelated document\nwith no folios at all", user_id="u1")
    assert result.exceptions
    assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def test_the_same_isin_from_two_sources_is_one_asset():
    left = Asset(id="a1", name="Fund A - Direct Growth", asset_type=AssetType.EQUITY_FUND,
                 isin="INF123456789")
    right = Asset(id="a2", name="FUND A DIRECT PLAN", asset_type=AssetType.EQUITY_FUND,
                  isin="INF123456789")
    assert resolve_asset(right, [left]) is left


def test_different_isins_never_merge_on_name_similarity():
    """"HDFC Small Cap" and "HDFC Mid Cap" score highly on raw similarity and
    must not become one holding."""
    left = Asset(id="a1", name="HDFC Small Cap Fund", asset_type=AssetType.EQUITY_FUND,
                 isin="INF000000001")
    right = Asset(id="a2", name="HDFC Mid Cap Fund", asset_type=AssetType.EQUITY_FUND,
                  isin="INF000000002")
    assert resolve_asset(right, [left]) is None


def test_re_importing_the_same_file_does_not_double_the_portfolio():
    first = parse_csv(HOLDINGS_CSV, source_name="h.csv", user_id="u1")
    second = parse_csv(HOLDINGS_CSV, source_name="h.csv", user_id="u1")
    portfolio, report = normalise([first, second], user_id="u1")
    assert len(portfolio.holdings) == 2
    assert report.duplicate_holdings


def test_a_user_correction_wins_over_parsed_data():
    result = parse_csv(HOLDINGS_CSV, user_id="u1")
    target = result.holdings[0]
    from aicio.money import money as to_money
    portfolio, report = normalise(
        [result], user_id="u1",
        corrections=[Correction("holding", target.id, "average_cost", to_money(60),
                                note="statement showed the wrong basis")],
    )
    fixed = next(h for h in portfolio.holdings if h.id == target.id)
    assert float(fixed.average_cost) == 60.0
    assert report.corrections_applied == 1
    assert "user corrected" in fixed.provenance.transformation


def test_format_is_sniffed_from_bytes_not_the_extension():
    """A .xls that is really a CSV is routine, and trusting the extension
    fails on exactly the files users are most likely to send."""
    assert sniff_format("statement.xls", b"Name,Units\nA,1\n") == "csv"
    assert sniff_format("statement.txt", b"%PDF-1.7 ...") == "pdf"
    assert sniff_format("x.csv", b"PK\x03\x04rest") == "xlsx"


def test_unknown_format_returns_an_actionable_exception(tmp_path):
    path = tmp_path / "mystery.bin"
    path.write_bytes(b"\x00\x01\x02\x03")
    result = parse_statement(path, user_id="u1")
    assert result.confidence == 0.0
    assert "CSV" in result.exceptions[0].suggestion
