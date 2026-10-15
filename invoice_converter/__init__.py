"""
invoice_converter
------------------
Convert photographed/handwritten invoices and digital PDF invoices into a
structured .xlsx (SOURCE FILE, COMPANY NAME, BILLED TO, DATE, REF/INVOICE NO, VAT
NUMBER, GROSS AMOUNT, VAT AMOUNT, NET AMOUNT) - one row per invoice.
NET AMOUNT + VAT AMOUNT = GROSS AMOUNT.

Images go through a vision model (default: qwen/qwen3.7-plus via
an OpenAI-compatible API). Digital PDFs (ones with a real text layer, not
scans) go through pdfplumber for text extraction, then the same model as
plain text - cheaper and more accurate than treating them as images.
Scanned/photographed PDFs (no text layer - often a batch of several
invoices stapled into one file) fall back to rendering each page as an
image and running it through the vision model separately, one row per
page.

The DATE column's output format is selectable (see DATE_FORMAT_OPTIONS) -
app.py exposes this as a dropdown before conversion.

Public API:
    from invoice_converter import extract_invoices, extract_invoices_from_text
    from invoice_converter import extract_text_from_pdf, render_pdf_pages_to_images
    from invoice_converter import build_rows, build_workbook
    from invoice_converter import DATE_FORMAT_OPTIONS, DEFAULT_DATE_FORMAT
    from invoice_converter import (
        InvoiceConverterError, ConfigError, VisionAPIError, ParseError, PDFExtractionError,
    )
"""

from .exceptions import (
    InvoiceConverterError,
    ConfigError,
    VisionAPIError,
    ParseError,
    PDFExtractionError,
)
from .vision_client import extract_invoices, extract_invoices_from_text
from .pdf_extractor import extract_text_from_pdf, render_pdf_pages_to_images
from .parser import build_rows, build_failed_row, check_amounts, format_position, make_ref, DATE_FORMAT_OPTIONS, DEFAULT_DATE_FORMAT
from .xlsx_writer import build_workbook, HEADERS
from .config import Settings, load_settings

__version__ = "0.7.1"

__all__ = [
    "extract_invoices",
    "extract_invoices_from_text",
    "extract_text_from_pdf",
    "render_pdf_pages_to_images",
    "build_rows",
    "build_failed_row",
    "check_amounts",
    "format_position",
    "make_ref",
    "DATE_FORMAT_OPTIONS",
    "DEFAULT_DATE_FORMAT",
    "build_workbook",
    "HEADERS",
    "Settings",
    "load_settings",
    "InvoiceConverterError",
    "ConfigError",
    "VisionAPIError",
    "ParseError",
    "PDFExtractionError",
    "__version__",
]
