import sys
import os
import io
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from openpyxl import load_workbook
from invoice_converter.xlsx_writer import build_workbook, HEADERS
from invoice_converter.parser import build_rows

# Row shape (matches HEADERS order): source_file, position, company, billed_to, date, ref, vat_no, GROSS_col, VAT_col, NET_col
# GROSS_col holds the final/total figure, NET_col holds the pre-VAT figure:
# NET + VAT = GROSS. See parser.py's module docstring for the full explanation.


def test_headers_written_correctly():
    xlsx_bytes = build_workbook([["src.jpg", "1 of 1", "Test Co", "Customer Co", "01/01/2025", "X1", "GB123456789", 120.0, 20.0, 100.0]])
    wb = load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.active
    header_row = [cell.value for cell in ws[1]]
    assert header_row == HEADERS


def test_headers_are_in_the_requested_order():
    """VAT NUMBER, then GROSS AMOUNT, then VAT AMOUNT, then NET AMOUNT."""
    idx = {h: i for i, h in enumerate(HEADERS)}
    assert idx["VAT NUMBER"] < idx["GROSS AMOUNT"] < idx["VAT AMOUNT"] < idx["NET AMOUNT"]


def test_row_count_matches_input_plus_grand_total():
    rows = [
        ["src.jpg", "1 of 1", "Company A", "Customer A", "01/01/2025", "X1", "GB1", 120.0, 20.0, 100.0],
        ["src.jpg", "1 of 1", "Company B", "Customer B", "02/01/2025", "X2", "GB2", 60.0, 10.0, 50.0],
    ]
    xlsx_bytes = build_workbook(rows)
    wb = load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.active
    # header + 2 data rows + 1 grand-total row
    assert ws.max_row == len(rows) + 2


def test_grand_total_sums_gross_amount_column_not_net():
    """The grand total must sum GROSS AMOUNT (the final totals: 120 + 60 =
    180), NOT NET AMOUNT (which would wrongly give 100 + 50 = 150). This
    is exactly the bug that was reported and fixed - the grand-total
    column pointer had been left pointing at NET AMOUNT after the
    GROSS/NET column meanings were corrected."""
    rows = [
        ["src.jpg", "1 of 1", "Company A", "Customer A", "01/01/2025", "X1", "GB1", 120.0, 20.0, 100.0],
        ["src.jpg", "1 of 1", "Company B", "Customer B", "02/01/2025", "X2", "GB2", 60.0, 10.0, 50.0],
    ]
    xlsx_bytes = build_workbook(rows)
    wb = load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.active
    gross_col = HEADERS.index("GROSS AMOUNT") + 1
    last_row = ws.max_row
    assert ws.cell(row=last_row, column=1).value == "GRAND TOTAL"
    assert ws.cell(row=last_row, column=gross_col).value == 180.0


def test_malformed_row_length_raises():
    bad_rows = [["Company A", "Customer A", "01/01/2025", "X1"]]  # missing VAT NUMBER/GROSS/VAT/NET
    try:
        build_workbook(bad_rows)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_none_vat_and_net_leave_cells_blank_but_gross_still_shows():
    """Baboo Wholesale Meats: only a total is printed, no separate NET/VAT
    breakdown - NET and VAT should be blank, but GROSS (the total that IS
    known) must still show."""
    rows = [["src.jpg", "1 of 1", "Baboo Wholesale Meats Ltd", "Bedford Fish & Meat", "22/10/2025", "217501", "849022818", 634.62, None, None]]
    xlsx_bytes = build_workbook(rows)
    wb = load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.active
    gross_col = HEADERS.index("GROSS AMOUNT") + 1
    vat_col = HEADERS.index("VAT AMOUNT") + 1
    net_col = HEADERS.index("NET AMOUNT") + 1
    assert ws.cell(row=2, column=gross_col).value == 634.62
    assert ws.cell(row=2, column=vat_col).value is None
    assert ws.cell(row=2, column=net_col).value is None


def test_vat_number_column_present_and_populated():
    rows = [["src.jpg", "1 of 1", "Test Co", "Customer Co", "01/01/2025", "X1", "GB123456789", 120.0, 20.0, 100.0]]
    xlsx_bytes = build_workbook(rows)
    wb = load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.active
    vat_no_col = HEADERS.index("VAT NUMBER") + 1
    assert ws.cell(row=2, column=vat_no_col).value == "GB123456789"
    assert ws.cell(row=2, column=vat_no_col).number_format == "General"


def test_company_name_and_billed_to_are_separate_columns():
    rows = [["src.jpg", "1 of 1", "Caribbean Gold", "Common Sense", "", "", "", 402.00, None, None]]
    xlsx_bytes = build_workbook(rows)
    wb = load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.active
    company_col = HEADERS.index("COMPANY NAME") + 1
    billed_to_col = HEADERS.index("BILLED TO") + 1
    assert ws.cell(row=2, column=company_col).value == "Caribbean Gold"
    assert ws.cell(row=2, column=billed_to_col).value == "Common Sense"


def test_full_pipeline_on_real_samples():
    from tests.sample_data import SAMPLES
    all_rows = []
    for i, sample in enumerate(SAMPLES):
        all_rows.extend(build_rows(sample, f"sample_{i}.jpg"))
    xlsx_bytes = build_workbook(all_rows)
    wb = load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.active

    # header + one row per sample + grand total row
    assert ws.max_row == len(SAMPLES) + 2

    gross_col = HEADERS.index("GROSS AMOUNT") + 1
    net_col = HEADERS.index("NET AMOUNT") + 1
    vat_no_col = HEADERS.index("VAT NUMBER") + 1
    billed_to_col = HEADERS.index("BILLED TO") + 1

    # GROSS AMOUNT holds each invoice's final total
    totals = [
        row[0].value for row in ws.iter_rows(min_row=2, max_row=ws.max_row - 1, min_col=gross_col, max_col=gross_col)
    ]
    assert 402.00 in totals  # Caribbean Gold
    assert 283.62 in totals  # Major Foods

    # NET AMOUNT holds the pre-VAT figure - Holland Bazaar's GOODS value
    net_values = [
        row[0].value for row in ws.iter_rows(min_row=2, max_row=ws.max_row - 1, min_col=net_col, max_col=net_col)
    ]
    assert 119.55 in net_values  # Holland Bazaar's pre-VAT "GOODS" figure

    vat_numbers = [
        row[0].value for row in ws.iter_rows(min_row=2, max_row=ws.max_row - 1, min_col=vat_no_col, max_col=vat_no_col)
    ]
    assert "849022818" in vat_numbers  # Baboo Wholesale Meats

    billed_tos = [
        row[0].value for row in ws.iter_rows(min_row=2, max_row=ws.max_row - 1, min_col=billed_to_col, max_col=billed_to_col)
    ]
    assert "Common Sense" in billed_tos              # Caribbean Gold's customer
    assert "Shah, Dalston Limited" in billed_tos      # handwritten repair invoice #11's customer
    assert "Bedford Fish & Meat" in billed_tos        # Baboo Wholesale Meats' customer

    # Grand total sums GROSS AMOUNT (the final totals), not NET AMOUNT
    expected_grand_total = round(sum(s["total_amount"] for s in SAMPLES), 2)
    actual_grand_total = round(ws.cell(row=ws.max_row, column=gross_col).value, 2)
    assert actual_grand_total == expected_grand_total



def test_source_file_is_first_column_and_written():
    xlsx_bytes = build_workbook([["Invoice 12.pdf (page 4)", "1 of 1", "Co", "", "01/01/2025", "X1", "", 12.0, 2.0, 10.0]])
    ws = load_workbook(io.BytesIO(xlsx_bytes)).active
    assert HEADERS[0] == "SOURCE FILE" and HEADERS[1] == "POSITION"
    assert ws.cell(row=2, column=1).value == "Invoice 12.pdf (page 4)"


def test_failed_rows_are_red_with_comment_and_dont_affect_total():
    from invoice_converter.parser import build_failed_row
    rows = [["a.jpg", "1 of 1", "Co", "", "", "", "", 50.0, None, None], build_failed_row("b.pdf")]
    ws = load_workbook(io.BytesIO(build_workbook(rows, failed={1: "API timeout"}))).active
    assert ws.cell(row=3, column=1).value == "b.pdf"
    assert ws.cell(row=3, column=1).fill.start_color.rgb.endswith("F8CBAD")
    assert "API timeout" in ws.cell(row=3, column=1).comment.text
    gross_col = HEADERS.index("GROSS AMOUNT") + 1
    assert ws.cell(row=ws.max_row, column=gross_col).value == 50.0



def test_warning_rows_are_amber_with_comment():
    rows = [["a.jpg", "1 of 2", "Co", "", "", "", "", 10.0, 2.0, 7.0],
            ["a.jpg", "2 of 2", "Co2", "", "", "", "", 5.0, None, None]]
    ws = load_workbook(io.BytesIO(build_workbook(rows, warnings={0: "NET + VAT != GROSS"}))).active
    assert ws.cell(row=2, column=1).fill.start_color.rgb.endswith("FFE699")
    assert "NET + VAT" in ws.cell(row=2, column=1).comment.text
    assert ws.cell(row=3, column=1).comment is None


def _row(date):
    return ["a.jpg", "1 of 1", "Co", "", date, "R1", "", 10.0, None, None]


def test_dates_are_real_excel_dates_in_every_format():
    """Real dates (not text) are what make Excel's filter group by
    Year > Month > Day."""
    import datetime as dt
    from invoice_converter.parser import build_rows, DATE_FORMAT_OPTIONS, EXCEL_DATE_FORMATS
    assert set(EXCEL_DATE_FORMATS) == set(DATE_FORMAT_OPTIONS)
    for fmt in DATE_FORMAT_OPTIONS:
        rows = build_rows({"ref": "R1", "supplier": "Co", "date": "05/09/2026", "total_amount": 1.0},
                          "a.jpg", date_format=fmt)
        ws = load_workbook(io.BytesIO(build_workbook(rows, date_format=fmt))).active
        cell = ws.cell(row=2, column=HEADERS.index("DATE") + 1)
        assert isinstance(cell.value, dt.datetime), fmt
        assert cell.value.date() == dt.date(2026, 9, 5), fmt
        assert cell.number_format == EXCEL_DATE_FORMATS[fmt], fmt


def test_partial_dates_stay_text_not_guessed():
    for raw in ["20-8-2", "30/07/2?24", "05 Sep", ""]:
        ws = load_workbook(io.BytesIO(build_workbook([_row(raw)]))).active
        val = ws.cell(row=2, column=HEADERS.index("DATE") + 1).value
        assert val == (raw or None), raw

if __name__ == "__main__":
    import traceback
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {t.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
