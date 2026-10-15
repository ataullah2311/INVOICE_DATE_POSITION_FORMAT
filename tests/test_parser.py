import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from invoice_converter.parser import build_failed_row, build_rows, check_amounts, format_position, make_ref, DATE_FORMAT_OPTIONS, DEFAULT_DATE_FORMAT

# Row shape: [source_file, position, company_name, billed_to, date, ref, vat_number, GROSS_col, VAT_col, NET_col]
# GROSS_col <- model's total_amount (final, VAT-inclusive)
# NET_col   <- model's net_amount   (pre-VAT figure)
# so NET + VAT = GROSS. See parser.py's module docstring for why the
# column names and JSON field names are deliberately not 1:1.
SOURCE, POSITION, COMPANY, BILLED_TO, DATE, REF, VAT_NO, GROSS, VAT_AMT, NET = range(10)


def test_ref_uses_printed_number_when_present():
    parsed = {"ref": "6297406", "date": "04/07/2025", "supplier": "Holland Bazaar", "total_amount": None}
    assert make_ref(parsed, "img.jpg") == "6297406"


def test_ref_falls_back_to_supplier_and_date():
    parsed = {"ref": None, "date": "14/09/2025", "supplier": "Tesco", "total_amount": None}
    assert make_ref(parsed, "img.jpg") == "Tesco 14/09/2025"


def test_ref_falls_back_to_filename_when_nothing_else_known():
    parsed = {"ref": None, "date": None, "supplier": None, "total_amount": None}
    assert make_ref(parsed, "img.jpg") == "img.jpg"


def test_build_rows_returns_exactly_one_row():
    parsed = {
        "ref": "X1", "date": "01/01/2025", "supplier": "Test Co", "billed_to": "Customer Co",
        "vat_number": "GB123456789", "net_amount": 100.0, "vat_amount": 20.0, "total_amount": 120.0,
    }
    rows = build_rows(parsed, "img.jpg")
    assert len(rows) == 1


def test_row_fields_map_correctly():
    """net_amount=100, vat_amount=20, total_amount=120 (100+20=120, checks out).
    GROSS column should get the final total (120); NET column should get
    the pre-VAT figure (100) - this is the actual relationship the user
    confirmed: NET + VAT = GROSS."""
    parsed = {
        "ref": "X1", "date": "01/01/2025", "supplier": "Test Co", "billed_to": "Customer Co",
        "vat_number": "GB123456789", "net_amount": 100.0, "vat_amount": 20.0, "total_amount": 120.0,
    }
    row = build_rows(parsed, "img.jpg")[0]
    assert row[COMPANY] == "Test Co"
    assert row[BILLED_TO] == "Customer Co"
    assert row[DATE] == "01/01/2025"
    assert row[REF] == "X1"
    assert row[VAT_NO] == "GB123456789"
    assert row[GROSS] == 120.0   # the final/total figure
    assert row[VAT_AMT] == 20.0
    assert row[NET] == 100.0     # the pre-VAT figure
    assert row[NET] + row[VAT_AMT] == row[GROSS]  # the actual relationship this bug was about


def test_holland_bazaar_real_invoice_relationship():
    """Concrete real-world check: Holland Bazaar prints GOODS £119.55,
    V.A.T. £8.10, TOTAL £127.65 (119.55 + 8.10 = 127.65). This is the
    exact example used to diagnose and fix the GROSS/NET column swap."""
    parsed = {
        "ref": "6297406", "date": "04/07/2025", "supplier": "Holland Bazaar Cash & Carry",
        "billed_to": None, "vat_number": "802 6418 53",
        "net_amount": 119.55, "vat_amount": 8.10, "total_amount": 127.65,
    }
    row = build_rows(parsed, "img.jpg")[0]
    assert row[NET] == 119.55
    assert row[VAT_AMT] == 8.10
    assert row[GROSS] == 127.65
    assert round(row[NET] + row[VAT_AMT], 2) == row[GROSS]


def test_supplier_and_billed_to_are_never_confused():
    """Real invoices in this project (Caribbean Gold: 'FROM: Caribbean Gold'
    / 'TO: Common Sense') name two DIFFERENT businesses on one document -
    they must land in different columns, never merged or duplicated."""
    parsed = {
        "ref": None, "date": None, "supplier": "Caribbean Gold", "billed_to": "Common Sense",
        "vat_number": None, "net_amount": None, "vat_amount": None, "total_amount": 402.00,
    }
    row = build_rows(parsed, "img.jpg")[0]
    assert row[COMPANY] == "Caribbean Gold"
    assert row[BILLED_TO] == "Common Sense"
    assert row[COMPANY] != row[BILLED_TO]


def test_missing_billed_to_becomes_empty_string_not_none():
    """Till receipts (Tesco, Aldi) don't name a buyer at all."""
    parsed = {"ref": None, "date": "14/09/2025", "supplier": "Tesco", "billed_to": None, "total_amount": 52.01}
    row = build_rows(parsed, "img.jpg")[0]
    assert row[BILLED_TO] == ""


def test_missing_supplier_becomes_empty_string_not_none():
    """Handwritten invoice #11: the issuer's own name is illegible, but the
    'Bill to' customer name is clear - supplier being unknown must not
    block the rest of the row."""
    parsed = {"ref": "11", "date": "13/11/2025", "supplier": None, "billed_to": "Shah, Dalston Limited", "total_amount": 450.0}
    row = build_rows(parsed, "img.jpg")[0]
    assert row[COMPANY] == ""
    assert row[BILLED_TO] == "Shah, Dalston Limited"


def test_missing_vat_number_becomes_empty_string_not_none():
    parsed = {"ref": "X1", "date": "01/01/2025", "supplier": "Test Co", "vat_number": None, "total_amount": 5}
    row = build_rows(parsed, "img.jpg")[0]
    assert row[VAT_NO] == ""


def test_missing_net_and_vat_amount_become_none_not_zero():
    """Several real samples (Baboo Meats, Caribbean Gold) only print a total,
    no separate VAT/net breakdown - must stay None, not silently become 0.
    GROSS (the total) is still populated even when NET/VAT aren't known."""
    parsed = {"ref": "X1", "date": "01/01/2025", "supplier": "Test Co", "vat_number": "849022818", "total_amount": 634.62}
    row = build_rows(parsed, "img.jpg")[0]
    assert row[NET] is None
    assert row[VAT_AMT] is None
    assert row[GROSS] == 634.62


def test_vat_number_is_never_confused_with_vat_amount():
    """vat_number (a registration ID, may contain letters like 'GB') and
    vat_amount (a currency figure) must land in different columns."""
    parsed = {
        "ref": "X1", "date": "01/01/2025", "supplier": "Test Co", "vat_number": "GB170405145",
        "net_amount": 268.82, "vat_amount": 14.80, "total_amount": 283.62,
    }
    row = build_rows(parsed, "img.jpg")[0]
    assert row[VAT_NO] == "GB170405145"
    assert row[VAT_AMT] == 14.80


def test_malformed_numeric_string_does_not_crash():
    parsed = {
        "ref": "X1", "date": "01/01/2025", "supplier": "Test Co", "vat_number": "GB1",
        "net_amount": "£100.00", "vat_amount": "not a number", "total_amount": None,
    }
    row = build_rows(parsed, "img.jpg")[0]
    assert row[NET] == 100.00         # "£100.00" -> 100.00
    assert row[VAT_AMT] is None       # "not a number" -> None, no crash
    assert row[GROSS] is None         # total_amount was None


def test_all_real_samples_produce_exactly_one_row_each():
    from tests.sample_data import SAMPLES
    for sample in SAMPLES:
        rows = build_rows(sample, "sample.jpg")
        assert len(rows) == 1, f"{sample.get('supplier')}: expected 1 row, got {len(rows)}"


def test_all_real_samples_with_both_figures_satisfy_net_plus_vat_equals_gross():
    """Every real sample where net_amount AND vat_amount are both known
    should satisfy the accounting identity once mapped into row columns."""
    from tests.sample_data import SAMPLES
    checked = 0
    for sample in SAMPLES:
        if sample.get("net_amount") is not None and sample.get("vat_amount") is not None:
            row = build_rows(sample, "sample.jpg")[0]
            assert round(row[NET] + row[VAT_AMT], 2) == round(row[GROSS], 2), sample["supplier"]
            checked += 1
    assert checked >= 3  # sanity check the test actually exercised real samples


# --- date format selection ---

def test_default_date_format_is_uk_style():
    parsed = {"ref": "X1", "date": "05/09/2026", "supplier": "Test Co", "total_amount": 10}
    row = build_rows(parsed, "img.jpg")[0]  # date_format not passed -> default
    assert row[DATE] == "05/09/2026"


def test_reformats_into_each_selectable_option():
    """A single real date, run through every option in the dropdown,
    should come out correctly in each format."""
    parsed = {"ref": "X1", "date": "05/09/2026", "supplier": "Test Co", "total_amount": 10}
    expected = {
        "DD/MM/YYYY (UK)": "05/09/2026",
        "MM/DD/YYYY (US)": "09/05/2026",
        "YYYY-MM-DD (ISO)": "2026-09-05",
        "DD-MM-YYYY": "05-09-2026",
        "DD Mon YYYY": "05 Sep 2026",
    }
    assert set(expected.keys()) == set(DATE_FORMAT_OPTIONS.keys())  # catches a forgotten option on either side
    for date_format, expected_value in expected.items():
        row = build_rows(parsed, "img.jpg", date_format=date_format)[0]
        assert row[DATE] == expected_value, date_format


def test_reformatting_is_dayfirst_not_us_style():
    """05/09/2026 must be read as 5 September (UK/day-first), not 9 May
    (US) - this is what the extraction prompt always produces, so
    parsing must assume the same convention."""
    parsed = {"ref": "X1", "date": "05/09/2026", "supplier": "Test Co", "total_amount": 10}
    row = build_rows(parsed, "img.jpg", date_format="YYYY-MM-DD (ISO)")[0]
    assert row[DATE] == "2026-09-05"  # NOT 2026-05-09


def test_unparseable_date_is_left_unchanged_not_blanked():
    """A date the parser can't confidently read should stay visible and
    editable by the person, not silently disappear or get mangled."""
    parsed = {"ref": "X1", "date": "sometime last week", "supplier": "Test Co", "total_amount": 10}
    row = build_rows(parsed, "img.jpg", date_format="YYYY-MM-DD (ISO)")[0]
    assert row[DATE] == "sometime last week"


def test_missing_date_stays_empty_in_any_format():
    parsed = {"ref": "X1", "date": None, "supplier": "Test Co", "total_amount": 10}
    row = build_rows(parsed, "img.jpg", date_format="YYYY-MM-DD (ISO)")[0]
    assert row[DATE] == ""


def test_iso_and_other_common_input_shapes_are_also_recognized():
    """Real samples in this project include dates that arrive already in
    ISO shape (e.g. Nella Cutlery invoices) even though the prompt asks
    for DD/MM/YYYY - the parser should handle both without configuration."""
    parsed_iso = {"ref": "X1", "date": "2026-09-05", "supplier": "Test Co", "total_amount": 10}
    row = build_rows(parsed_iso, "img.jpg", date_format="DD/MM/YYYY (UK)")[0]
    assert row[DATE] == "05/09/2026"


def test_all_real_samples_reformat_without_crashing():
    """Every real sample's date should survive a reformat pass in every
    selectable format without raising."""
    from tests.sample_data import SAMPLES
    for date_format in DATE_FORMAT_OPTIONS:
        for sample in SAMPLES:
            build_rows(sample, "sample.jpg", date_format=date_format)  # must not raise



def test_source_file_column_is_the_exact_filename():
    parsed = {"ref": "X1", "date": "01/01/2025", "supplier": "Test Co", "total_amount": 10.0}
    assert build_rows(parsed, "Holland Bazaar Oct.pdf")[0][SOURCE] == "Holland Bazaar Oct.pdf"
    assert build_rows(parsed, "scan.pdf (page 3)")[0][SOURCE] == "scan.pdf (page 3)"


def test_source_file_ignores_anything_the_model_returns():
    parsed = {"ref": "X1", "supplier": "Test Co", "source_file": "made-up.pdf", "total_amount": 10.0}
    assert build_rows(parsed, "real.jpg")[0][SOURCE] == "real.jpg"


def test_failed_row_keeps_source_and_has_no_amounts():
    row = build_failed_row("bad.pdf (page 2)")
    assert row[SOURCE] == "bad.pdf (page 2)"
    assert row[GROSS] is None and row[VAT_AMT] is None and row[NET] is None
    assert len(row) == 10



def test_position_column_written():
    parsed = {"ref": "X1", "supplier": "Co", "total_amount": 1.0}
    row = build_rows(parsed, "scan.pdf (page 3)", position="2 of 4 - top right")[0]
    assert row[SOURCE] == "scan.pdf (page 3)"
    assert row[POSITION] == "2 of 4 - top right"


def test_format_position():
    assert format_position(0, 1, "full page") == "1 of 1"
    assert format_position(0, 1, None) == "1 of 1"
    assert format_position(1, 4, "top right") == "2 of 4 - top right"
    assert format_position(3, 4, "") == "4 of 4"


def test_check_amounts_flags_mismatch_only_when_all_three_present():
    assert check_amounts({"net_amount": 33.34, "vat_amount": 6.67, "total_amount": 40.01}) is None
    assert check_amounts({"net_amount": 33.34, "vat_amount": 6.67, "total_amount": 40.00}) is None  # 1p rounding ok
    assert check_amounts({"net_amount": 7.49, "vat_amount": 1.49, "total_amount": 9.99}) is not None
    assert check_amounts({"net_amount": None, "vat_amount": None, "total_amount": 30.0}) is None


def test_partial_or_illegible_dates_are_never_completed_by_guessing():
    from invoice_converter.parser import _reformat_date
    for raw in ["20-8-2", "05 Sep", "Sep 2026", "30/07/2?24", "29/02/2025", "13/13/2026"]:
        assert _reformat_date(raw, "DD/MM/YYYY (UK)") == raw, raw


def test_real_receipt_date_styles():
    from invoice_converter.parser import _reformat_date
    cases = {"Mon 24 Aug 2026": "24/08/2026", "24/08/26": "24/08/2026", "2026-07-11": "11/07/2026",
             "16-07-2026": "16/07/2026", "5th Sep 2026": "05/09/2026", "05.09.2026": "05/09/2026"}
    for raw, want in cases.items():
        assert _reformat_date(raw, "DD/MM/YYYY (UK)") == want, raw


def test_ref_fallback_uses_the_chosen_date_format():
    row = build_rows({"ref": None, "supplier": "Tesco", "date": "2026-09-05"}, "x.jpg", "DD/MM/YYYY (UK)")[0]
    assert row[DATE] == "05/09/2026"
    assert row[REF] == "Tesco 05/09/2026"

if __name__ == "__main__":
    # Allow `python tests/test_parser.py` without pytest installed
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
