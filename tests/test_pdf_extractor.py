import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from invoice_converter.pdf_extractor import extract_text_from_pdf, render_pdf_pages_to_images
from invoice_converter.exceptions import PDFExtractionError

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _read_fixture(name):
    with open(os.path.join(FIXTURES_DIR, name), "rb") as f:
        return f.read()


# --- extract_text_from_pdf: digital PDFs with a real text layer ---

def test_extracts_text_from_a_real_pdf():
    text = extract_text_from_pdf(_read_fixture("sample_utility_bill.pdf"))
    assert "Test Energy Co" in text
    assert "Invoice number: TEST-0001" in text


def test_extracted_text_preserves_the_period_total_vs_balance_distinction():
    """This mirrors the real trap in utility-bill PDFs (see EDF sample this
    was built against): a 'Total charges for this period' figure sits right
    next to an unrelated, much larger 'Current balance' figure. The prompt
    (not this function) is responsible for picking the right one - this
    test just confirms both distinct strings survive extraction so the
    model actually has the chance to tell them apart."""
    text = extract_text_from_pdf(_read_fixture("sample_utility_bill.pdf"))
    assert "Total charges for this period" in text
    assert "120.00" in text
    assert "Current balance" in text
    assert "9999.00" in text


def test_raises_pdf_extraction_error_on_garbage_bytes():
    try:
        extract_text_from_pdf(b"this is not a real pdf file")
        assert False, "expected PDFExtractionError"
    except PDFExtractionError:
        pass


def test_raises_pdf_extraction_error_on_empty_bytes():
    try:
        extract_text_from_pdf(b"")
        assert False, "expected PDFExtractionError"
    except PDFExtractionError:
        pass


def test_scanned_pdf_with_no_text_layer_raises_not_returns_empty():
    """A scanned/photographed PDF (image-only page, no text) must raise
    PDFExtractionError - this is the signal app.py relies on to fall back
    to render_pdf_pages_to_images(), not an empty string it might
    silently send to the model as if there were nothing on the page."""
    try:
        extract_text_from_pdf(_read_fixture("scanned_no_text.pdf"))
        assert False, "expected PDFExtractionError"
    except PDFExtractionError:
        pass


# --- render_pdf_pages_to_images: scanned/photographed PDFs, no text layer ---

def test_renders_one_image_per_page():
    images = render_pdf_pages_to_images(_read_fixture("scanned_no_text.pdf"))
    assert len(images) == 2  # fixture has 2 pages


def test_rendered_pages_are_valid_png_images():
    images = render_pdf_pages_to_images(_read_fixture("scanned_no_text.pdf"))
    for img_bytes in images:
        assert img_bytes[:8] == b"\x89PNG\r\n\x1a\n"  # PNG file signature
        assert len(img_bytes) > 1000  # sanity check it's not a truncated/blank image


def test_render_raises_pdf_extraction_error_on_garbage_bytes():
    try:
        render_pdf_pages_to_images(b"this is not a real pdf file")
        assert False, "expected PDFExtractionError"
    except PDFExtractionError:
        pass


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
