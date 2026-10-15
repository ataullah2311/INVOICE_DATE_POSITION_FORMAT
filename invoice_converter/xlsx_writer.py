"""
Writes a list of spreadsheet rows (as produced by parser.build_rows) to a
formatted .xlsx, returned as bytes so callers (Streamlit, a CLI, tests) can
either write it to disk or stream it as a download.

Each row is one complete invoice's summary - there's no per-invoice
grouping/blank-until-last-row logic needed here, since every row already
carries its own GROSS/VAT/NET figures.

Column positions are derived from HEADERS by name rather than hardcoded as
cell letters, so adding/reordering a column only requires editing HEADERS +
the matching row-building logic in parser.py (both must list the SAME
columns in the SAME order - see parser.py's module docstring for the same
note from its side).

IMPORTANT: the "final total" column name is used in 5 places below
(HEADERS, _MONEY_HEADERS, _TOTAL_COL_LETTER, _COLUMN_WIDTHS, and inside
build_workbook where grand_total is accumulated) - if you rename that
column, update all 5, not just HEADERS. A leftover old name in any one
of them throws `ValueError: '<old name>' is not in list` at import time.
"""
import datetime as _dt
import io
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

HEADERS = [
    "SOURCE FILE", "POSITION", "COMPANY NAME", "BILLED TO", "DATE", "REF/INVOICE NO", "VAT NUMBER",
    "GROSS AMOUNT", "VAT AMOUNT", "NET AMOUNT",
]

# This is the column that holds each invoice's final/grand total figure -
# used for the bolded GRAND TOTAL row at the bottom of the sheet. This is
# "GROSS AMOUNT" (the VAT-inclusive final total, per parser.py's mapping),
# NOT "NET AMOUNT" (which holds the pre-VAT figure) - if you change what
# parser.py puts in the GROSS AMOUNT column, update this to match.
_FINAL_TOTAL_HEADER = "GROSS AMOUNT"

_MONEY_FORMAT = "#,##0.00"
_HEADER_FILL_COLOR = "305496"
_MONEY_HEADERS = {"GROSS AMOUNT", "VAT AMOUNT", "NET AMOUNT"}

_MONEY_COL_LETTERS = [get_column_letter(HEADERS.index(h) + 1) for h in _MONEY_HEADERS]
_TOTAL_COL_LETTER = get_column_letter(HEADERS.index(_FINAL_TOTAL_HEADER) + 1)

_COLUMN_WIDTHS = {
    "SOURCE FILE": 34, "POSITION": 22, "COMPANY NAME": 26, "BILLED TO": 26, "DATE": 12, "REF/INVOICE NO": 20,
    "VAT NUMBER": 16, "GROSS AMOUNT": 14, "VAT AMOUNT": 14, "NET AMOUNT": 16,
}


from .parser import DATE_FORMAT_OPTIONS, DEFAULT_DATE_FORMAT, EXCEL_DATE_FORMATS

_DATE_COL_INDEX = HEADERS.index("DATE")


def _to_excel_date(value, date_format: str):
    """Turn a DATE cell value produced by parser.build_rows back into a real
    date. build_rows formats every date it could fully read with exactly
    DATE_FORMAT_OPTIONS[date_format], so reading it back with the same
    pattern is exact. Anything that doesn't match (a date left as printed
    because part of it was illegible, e.g. "20-8-2") returns None and is
    kept as text, so it stands out in the filter instead of being guessed."""
    if not isinstance(value, str) or not value.strip():
        return None
    pattern = DATE_FORMAT_OPTIONS.get(date_format, DATE_FORMAT_OPTIONS[DEFAULT_DATE_FORMAT])
    try:
        return _dt.datetime.strptime(value.strip(), pattern)
    except ValueError:
        return None


_FAILED_FILL = PatternFill(start_color="F8CBAD", end_color="F8CBAD", fill_type="solid")
_WARN_FILL = PatternFill(start_color="FFE699", end_color="FFE699", fill_type="solid")


def build_workbook(all_rows: list, failed: dict = None, warnings: dict = None,
                   date_format: str = DEFAULT_DATE_FORMAT) -> bytes:
    """Build the invoices workbook and return it as bytes (ready to write
    to disk or hand to a download button). Each row must have exactly
    len(HEADERS) values, in HEADERS order.

    `failed` optionally maps a 0-based index into all_rows -> error
    message. Those rows are shaded red and the error is attached as a
    comment on their SOURCE FILE cell, so a failed file is visible in the
    sheet rather than missing from it.

    `warnings` works the same way but shades the row amber - used for rows
    that were extracted but need a human check (e.g. NET + VAT != GROSS,
    or the model's invoice count for that page didn't match its list).

    `date_format` is the dropdown choice (a DATE_FORMAT_OPTIONS key). Dates
    are written as real Excel dates displayed in that format, so Excel's
    filter groups them by Year > Month > Day.
    """
    failed = failed or {}
    warnings = warnings or {}
    excel_date_fmt = EXCEL_DATE_FORMATS.get(date_format, EXCEL_DATE_FORMATS[DEFAULT_DATE_FORMAT])
    wb = Workbook()
    ws = wb.active
    ws.title = "Invoices"

    ws.append(HEADERS)
    header_font = Font(bold=True, name="Arial", color="FFFFFF")
    header_fill = PatternFill(start_color=_HEADER_FILL_COLOR, end_color=_HEADER_FILL_COLOR, fill_type="solid")
    for col_idx in range(1, len(HEADERS) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    ws.freeze_panes = "A2"

    total_font = Font(bold=True, name="Arial")
    body_font = Font(name="Arial")

    row_num = 2
    grand_total = 0.0
    any_total_seen = False
    for row in all_rows:
        if len(row) != len(HEADERS):
            raise ValueError(
                f"Row {row_num - 1} has {len(row)} values, expected {len(HEADERS)} "
                f"matching columns {HEADERS}: {row}"
            )
        row = list(row)
        real_date = _to_excel_date(row[_DATE_COL_INDEX], date_format)
        if real_date is not None:
            row[_DATE_COL_INDEX] = real_date
        ws.append(row)
        if real_date is not None:
            date_cell = ws.cell(row=row_num, column=_DATE_COL_INDEX + 1)
            date_cell.number_format = excel_date_fmt
            date_cell.alignment = Alignment(horizontal="left")
        for col_letter in _MONEY_COL_LETTERS:
            cell = ws[f"{col_letter}{row_num}"]
            if cell.value is not None:
                cell.number_format = _MONEY_FORMAT
        for col_idx in range(1, len(HEADERS) + 1):
            ws.cell(row=row_num, column=col_idx).font = body_font
        if (row_num - 2) in warnings and (row_num - 2) not in failed:
            for col_idx in range(1, len(HEADERS) + 1):
                ws.cell(row=row_num, column=col_idx).fill = _WARN_FILL
            ws.cell(row=row_num, column=1).comment = Comment(
                f"Check this row: {warnings[row_num - 2]}", "Invoice Converter"
            )
        if (row_num - 2) in failed:
            for col_idx in range(1, len(HEADERS) + 1):
                ws.cell(row=row_num, column=col_idx).fill = _FAILED_FILL
            ws.cell(row=row_num, column=1).comment = Comment(
                f"Extraction failed: {failed[row_num - 2]}", "Invoice Converter"
            )
        total_val = row[HEADERS.index(_FINAL_TOTAL_HEADER)]
        if total_val is not None:
            grand_total += total_val
            any_total_seen = True
        row_num += 1

    # Filter buttons on the header row, covering the invoice rows only (not
    # the GRAND TOTAL row) - DATE filters group by Year > Month > Day.
    if row_num > 2:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(HEADERS))}{row_num - 1}"

    # Grand-total row at the bottom, summing the final-total column across all invoices
    if any_total_seen:
        label_cell = ws.cell(row=row_num, column=1, value="GRAND TOTAL")
        label_cell.font = total_font
        grand_cell = ws[f"{_TOTAL_COL_LETTER}{row_num}"]
        grand_cell.value = grand_total
        grand_cell.font = total_font
        grand_cell.number_format = _MONEY_FORMAT

    for header, width in _COLUMN_WIDTHS.items():
        col_letter = get_column_letter(HEADERS.index(header) + 1)
        ws.column_dimensions[col_letter].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
