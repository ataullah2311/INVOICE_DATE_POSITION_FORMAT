"""
Custom exceptions.

Catching these specifically (instead of bare `except Exception`) means the
Streamlit UI - or any caller - can tell "the API call failed" apart from
"the API answered but the JSON was garbage" apart from "config is missing",
and show/handle each differently instead of one generic failure message.
"""


class InvoiceConverterError(Exception):
    """Base class for all errors raised by this package."""


class ConfigError(InvoiceConverterError):
    """Raised when required configuration (API key, base URL, model) is missing."""


class VisionAPIError(InvoiceConverterError):
    """Raised when the vision model API call itself fails (network, auth, rate limit)."""


class ParseError(InvoiceConverterError):
    """Raised when the model responded but its output could not be parsed into
    the expected invoice JSON shape."""


class PDFExtractionError(InvoiceConverterError):
    """Raised when no usable text can be pulled from a PDF - typically means
    it's a scanned/image-only PDF with no real text layer, which pdfplumber
    can't read (that would need OCR/vision, not plain text extraction)."""
