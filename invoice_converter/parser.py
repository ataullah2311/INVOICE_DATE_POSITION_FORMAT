"""
Turns a validated invoice dict (as returned by vision_client.extract_invoice)
into the flat row shape the spreadsheet writer expects:

    [SOURCE FILE, POSITION, COMPANY NAME, BILLED TO, DATE, REF/INVOICE NO, VAT NUMBER, GROSS AMOUNT, VAT AMOUNT, NET AMOUNT]

SOURCE FILE is the uploaded file name (plus "(page N)" for scanned
multi-invoice PDFs). It is filled from the filename the app already
knows - never from the AI model - so it is always exactly right.

POSITION says which invoice on that page/photo the row is, e.g.
"2 of 4 - top right" - the "2 of 4" is the row's order in what the model
returned, the "top right" is the model's own description of where it sits.

This order must always match xlsx_writer.HEADERS exactly - both files
list the same columns independently (as a plain positional list here,
by name there), so a reorder/rename in one requires the same change in
the other. See xlsx_writer.py's module docstring for the same note from
its side.

IMPORTANT - the spreadsheet's GROSS/NET columns are the OPPOSITE way
round from the model's JSON field names, on purpose:

    Spreadsheet column "NET AMOUNT"   <- model's "net_amount" field
                                          (the pre-VAT figure, labelled
                                          "Net"/"Goods"/"Sub Total" etc.
                                          on the actual document)
    Spreadsheet column "GROSS AMOUNT" <- model's "total_amount" field
                                          (the final, VAT-inclusive
                                          total - "Gross" in standard UK
                                          accounting terms)

    NET AMOUNT + VAT AMOUNT = GROSS AMOUNT

If that relationship stops holding in an actual spreadsheet, the mapping
below (not the model's extraction) is almost certainly what broke -
check GROSS_COL/VAT_COL/NET_COL in build_rows() first.

One row per invoice - the output is invoice-level summary data only, not
individual line items.

Kept free of any API/network code so it can be unit-tested with plain dicts
(see tests/test_parser.py).
"""
import datetime as _dt
import re
from typing import Optional

try:
    from dateutil import parser as _dateutil_parser
except ImportError:  # pragma: no cover - dateutil is in requirements.txt,
    _dateutil_parser = None  # but degrade gracefully rather than crash on import.


# Output date formats the app.py UI lets the person choose from before
# converting. Keys are the human-readable labels shown in the dropdown;
# values are the matching strftime pattern.
DATE_FORMAT_OPTIONS = {
    "DD/MM/YYYY (UK)": "%d/%m/%Y",
    "MM/DD/YYYY (US)": "%m/%d/%Y",
    "YYYY-MM-DD (ISO)": "%Y-%m-%d",
    "DD-MM-YYYY": "%d-%m-%Y",
    "DD Mon YYYY": "%d %b %Y",
}
DEFAULT_DATE_FORMAT = "DD/MM/YYYY (UK)"

# Matching Excel number formats, so xlsx_writer can store each date as a
# REAL Excel date (which Excel's filter groups by Year > Month > Day) while
# still displaying it in the format chosen in the dropdown.
EXCEL_DATE_FORMATS = {
    "DD/MM/YYYY (UK)": "dd/mm/yyyy",
    "MM/DD/YYYY (US)": "mm/dd/yyyy",
    "YYYY-MM-DD (ISO)": "yyyy-mm-dd",
    "DD-MM-YYYY": "dd-mm-yyyy",
    "DD Mon YYYY": "dd mmm yyyy",
}

# The extraction prompt always asks the model for DD/MM/YYYY, so that's
# tried first; the rest are fallbacks for anything that slips through in
# a different shape. Day-first always wins when ambiguous (UK convention).
_KNOWN_INPUT_FORMATS = (
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d %b %Y", "%d %B %Y",
    "%d/%m/%y", "%d-%m-%y", "%d.%m.%y", "%d %b %y",
    "%m/%d/%Y",
)
_MIN_YEAR, _MAX_YEAR = 1990, 2100


def _year_is_printed(text: str, year: int) -> bool:
    """True only if the year actually appears in the text as a full 4-digit
    year or a 2-digit year - so a scribbled "20-8-2" is never read as 2002."""
    tokens = re.findall(r"\d+", text)
    return str(year) in tokens or f"{year % 100:02d}" in tokens


def _parse_date_strict(date_str: str):
    """Parse a date only if day, month AND year are all genuinely present.
    Returns a date, or None if anything is missing/ambiguous - never fills
    in a missing year/day from today's date."""
    cleaned = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", date_str, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(mon|tue|wed|thu|fri|sat|sun)[a-z]*,?\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    for fmt in _KNOWN_INPUT_FORMATS:
        try:
            d = _dt.datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
        if _MIN_YEAR <= d.year <= _MAX_YEAR and _year_is_printed(cleaned, d.year):
            return d
        return None

    if _dateutil_parser is None:
        return None
    # "Two different defaults" check: if any part (day/month/year) was
    # missing, dateutil fills it from the default - so parsing with two
    # different defaults gives two different answers. Reject that.
    try:
        d1 = _dateutil_parser.parse(cleaned, dayfirst=True, default=_dt.datetime(2004, 1, 1)).date()
        d2 = _dateutil_parser.parse(cleaned, dayfirst=True, default=_dt.datetime(2008, 2, 2)).date()
    except (ValueError, OverflowError, TypeError):
        return None
    if d1 != d2 or not (_MIN_YEAR <= d1.year <= _MAX_YEAR) or not _year_is_printed(cleaned, d1.year):
        return None
    return d1


def _reformat_date(date_str: str, date_format: str) -> str:
    """Reformat an extracted date string into the chosen output format.

    If the string can't be confidently parsed - including when the year,
    month or day is missing or illegible - it's returned UNCHANGED rather
    than guessed at or blanked out: a date the person can see and fix by
    eye is better than one silently made up.
    """
    if not date_str:
        return date_str
    date_str = date_str.strip()
    if not date_str:
        return date_str

    output_pattern = DATE_FORMAT_OPTIONS.get(date_format, DATE_FORMAT_OPTIONS[DEFAULT_DATE_FORMAT])
    parsed_date = _parse_date_strict(date_str)
    if parsed_date is None:
        return date_str  # couldn't parse it confidently - leave it exactly as extracted
    return parsed_date.strftime(output_pattern)


def make_ref(parsed: dict, filename: str) -> str:
    """Return the invoice's reference number, or a fallback built from
    supplier + date (or the filename as a last resort) when the document
    has no printed reference number - common on till receipts."""
    ref = parsed.get("ref")
    if ref:
        return str(ref)
    supplier = (parsed.get("supplier") or "").strip()
    date = (parsed.get("date") or "").strip()
    fallback = f"{supplier} {date}".strip()
    return fallback if fallback else filename


def _to_number(value) -> Optional[float]:
    """Best-effort coercion of a value to float; returns None rather than
    raising, since a single malformed field shouldn't sink the whole row."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        cleaned = str(value).replace(",", "").replace("£", "").strip()
        return float(cleaned) if cleaned else None
    except (ValueError, TypeError):
        return None


def format_position(index: int, count: int, where: str = None) -> str:
    """'2 of 4 - top right' (index is 0-based). Just '1 of 1' when the
    page held a single invoice and the model gave no extra description."""
    label = f"{index + 1} of {count}"
    where = (where or "").strip()
    if where and not (count == 1 and where.lower() in ("full page", "full document")):
        label += f" - {where}"
    return label


def check_amounts(parsed: dict):
    """Return a warning message if NET + VAT doesn't equal GROSS (to the
    penny, allowing 1p rounding), else None. Only checked when all three
    figures are present - a missing figure is not an error."""
    net = _to_number(parsed.get("net_amount"))
    vat = _to_number(parsed.get("vat_amount"))
    gross = _to_number(parsed.get("total_amount"))
    if None in (net, vat, gross):
        return None
    if abs(round(net + vat, 2) - round(gross, 2)) > 0.011:
        return (
            f"NET {net:.2f} + VAT {vat:.2f} = {net + vat:.2f}, but GROSS is "
            f"{gross:.2f} - check this invoice against the source."
        )
    return None


def build_rows(parsed: dict, filename: str, date_format: str = DEFAULT_DATE_FORMAT,
               position: str = "") -> list:
    """Turn one parsed invoice into a single-row list:
    [[source_file, position, company_name, billed_to, date, ref, vat_number, GROSS_COL, VAT_COL, NET_COL]]

    GROSS_COL = parsed["total_amount"] (the final VAT-inclusive total)
    VAT_COL   = parsed["vat_amount"]
    NET_COL   = parsed["net_amount"]   (the pre-VAT figure)

    so that in the spreadsheet: NET AMOUNT + VAT AMOUNT = GROSS AMOUNT.
    See this module's docstring for why the column names and the
    underlying JSON field names don't match 1:1.

    `date_format` is one of the keys in DATE_FORMAT_OPTIONS (defaults to
    DD/MM/YYYY) - the DATE column is reformatted into it; a date that
    can't be confidently parsed is left exactly as extracted rather than
    guessed at.

    Returns a list (not a bare row) so callers can keep doing
    `all_rows.extend(build_rows(parsed, filename))` regardless of whether
    the underlying extraction is per-invoice or per-line-item.
    """
    company_name = (parsed.get("supplier") or "").strip()
    billed_to = (parsed.get("billed_to") or "").strip()
    date = _reformat_date(parsed.get("date") or "", date_format)
    ref = make_ref({**parsed, "date": date}, filename)
    vat_number = (parsed.get("vat_number") or "").strip()

    net_amount = _to_number(parsed.get("net_amount"))
    vat_amount = _to_number(parsed.get("vat_amount"))
    total_amount = _to_number(parsed.get("total_amount"))

    gross_col_value = total_amount
    vat_col_value = vat_amount
    net_col_value = net_amount

    source_file = filename

    return [[source_file, position, company_name, billed_to, date, ref, vat_number, gross_col_value, vat_col_value, net_col_value]]


def build_failed_row(filename: str) -> list:
    """A placeholder row for a file/page that could NOT be extracted, so it
    still appears in the spreadsheet (with its SOURCE FILE) instead of
    silently vanishing. Every uploaded invoice is then accounted for."""
    return [filename, "", "EXTRACTION FAILED - check source", "", "", "", "", None, None, None]
