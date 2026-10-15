"""
Handles two very different kinds of PDF, and picks between them
automatically:

1. DIGITAL PDFs with a real text layer (an emailed utility bill, an
   invoice exported from accounting software) - pulled with pdfplumber,
   no vision model needed. Usually ONE invoice spanning one or more pages
   (see the EDF energy bill this was originally built against).

2. SCANNED/PHOTOGRAPHED PDFs with no text layer at all - each page is
   just an embedded image, commonly produced by scanning or photographing
   a stack of paper invoices into one PDF file. In this case each page is
   typically a SEPARATE invoice, not one invoice spread across pages - so
   each page is rendered to an image and sent through the vision model
   independently, producing one row per page rather than one row for the
   whole file.

extract_text_from_pdf() handles case 1 and raises PDFExtractionError if
the PDF has no text (signalling case 2). render_pdf_pages_to_images()
handles case 2. app.py tries the former first and falls back to the
latter - see its PDF handling block for the actual decision logic.
"""
import io

from .exceptions import PDFExtractionError


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract all text from a PDF's pages, concatenated with blank lines
    between pages. Raises PDFExtractionError if the PDF can't be opened or
    contains no extractable text at all (which usually means it's a
    scanned/photographed document - see render_pdf_pages_to_images for
    that case instead).
    """
    try:
        import pdfplumber
    except ImportError as e:
        raise PDFExtractionError(
            "The 'pdfplumber' package is required to read PDF invoices. "
            "Install it with: pip install pdfplumber"
        ) from e

    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages_text = [page.extract_text() or "" for page in pdf.pages]
    except Exception as e:
        raise PDFExtractionError(f"Could not open/read this PDF: {e}") from e

    text = "\n\n".join(t for t in pages_text if t.strip())

    if not text.strip():
        raise PDFExtractionError(
            "No readable text layer found in this PDF - it looks like a "
            "scanned or photographed document rather than a digitally "
            "generated one."
        )

    return text


def render_pdf_pages_to_images(file_bytes: bytes, scale: float = 2.5) -> list:
    """Render every page of a PDF to a PNG image, returned as a list of
    PNG bytes (one entry per page, in page order). Used for scanned/
    photographed PDFs that have no text layer - each page can then be sent
    through the vision model the same way an uploaded photo would be.

    `scale` controls render resolution (2.5 ~= 180 DPI - raised from 2.0 because
    a scanned A4 page often holds 3-4 small receipts; 2.0 ~= 144 DPI from a standard
    72-DPI PDF page) - higher improves legibility of small print/
    handwriting at the cost of larger images and more tokens per call.

    Raises PDFExtractionError if the PDF can't be opened or rendered.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError as e:
        raise PDFExtractionError(
            "The 'pypdfium2' package is required to render scanned PDF "
            "pages as images. Install it with: pip install pypdfium2"
        ) from e

    try:
        pdf = pdfium.PdfDocument(file_bytes)
        images = []
        for page in pdf:
            bitmap = page.render(scale=scale)
            pil_image = bitmap.to_pil()
            buf = io.BytesIO()
            pil_image.save(buf, format="PNG")
            images.append(buf.getvalue())
        return images
    except PDFExtractionError:
        raise
    except Exception as e:
        raise PDFExtractionError(f"Could not render this PDF's pages as images: {e}") from e
