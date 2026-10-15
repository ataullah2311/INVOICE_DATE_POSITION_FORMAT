"""
Streamlit front-end for the invoice converter.

Run:
    pip install -r requirements.txt
    cp .env.example .env   # then fill in your values
    streamlit run app.py
"""
import datetime as dt
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

from invoice_converter import (
    extract_invoices,
    extract_invoices_from_text,
    extract_text_from_pdf,
    render_pdf_pages_to_images,
    build_rows,
    build_failed_row,
    check_amounts,
    format_position,
    build_workbook,
    load_settings,
    DATE_FORMAT_OPTIONS,
    DEFAULT_DATE_FORMAT,
    ConfigError,
    VisionAPIError,
    ParseError,
    PDFExtractionError,
)

st.set_page_config(page_title="Invoice Converter Pro", layout="wide", page_icon="🧾")

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
_css_path = Path(__file__).parent / "assets" / "styles.css"
st.markdown(f"<style>{_css_path.read_text()}</style>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Topbar
# ---------------------------------------------------------------------------
with st.container(key="topbar"):
    st.markdown(
        """
        <div class="topbar-brand">🧾 Invoice Converter Pro</div>
        """,
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Hero + upload card
# ---------------------------------------------------------------------------
with st.container(key="hero"):
    col_text, col_upload = st.columns([1.15, 1], gap="large")

    with col_text:
        st.markdown(
            """
            <div class="hero-title">Turn Invoice Photos<br/>into Clean Spreadsheets</div>
            <div class="hero-subtitle">
                Upload photos of invoices, till receipts, handwritten supplier
                notes, or digital PDF invoices/bills. AI-powered extraction
                pulls the key totals straight into a ready-to-use Excel
                file - no manual typing.
            </div>
            <ul class="hero-bullets">
                <li><span class="dot"></span> Reads handwritten, printed, and PDF invoices</li>
                <li><span class="dot"></span> Picks out Gross, VAT and Total automatically</li>
                <li><span class="dot"></span> One clean row per invoice, ready to file</li>
            </ul>
            """,
            unsafe_allow_html=True,
        )

    with col_upload:
        with st.container(key="upload-card"):
            st.markdown(
                """
                <div class="upload-icon">📤</div>
                <div class="upload-title">Drop your invoices here</div>
                <div class="upload-subtitle">Images (JPG, PNG, WEBP) or digital PDFs</div>
                """,
                unsafe_allow_html=True,
            )
            uploaded_files = st.file_uploader(
                "Upload invoice/receipt files",
                type=["jpg", "jpeg", "png", "webp", "pdf"],
                accept_multiple_files=True,
                label_visibility="collapsed",
            )
            date_format = st.selectbox(
                "Date format",
                options=list(DATE_FORMAT_OPTIONS.keys()),
                index=list(DATE_FORMAT_OPTIONS.keys()).index(DEFAULT_DATE_FORMAT),
                help="Applied to the DATE column for every invoice in the output spreadsheet.",
            )
            convert_clicked = False
            if uploaded_files:
                convert_clicked = st.button(
                    f"Convert {len(uploaded_files)} file(s)", use_container_width=True
                )

# ---------------------------------------------------------------------------
# Feature cards
# ---------------------------------------------------------------------------
feat_col1, feat_col2, feat_col3 = st.columns(3, gap="medium")
with feat_col1:
    st.markdown(
        """
        <div class="feature-card">
            <div class="feature-icon">🎯</div>
            <div class="feature-title">Accurate</div>
            <div class="feature-desc">Reads messy handwriting and faded till
            receipts, not just clean printed invoices.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with feat_col2:
    st.markdown(
        """
        <div class="feature-card">
            <div class="feature-icon">⚡</div>
            <div class="feature-title">Fast</div>
            <div class="feature-desc">Convert a whole batch of invoice photos
            into one spreadsheet in seconds.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with feat_col3:
    st.markdown(
        """
        <div class="feature-card">
            <div class="feature-icon">📊</div>
            <div class="feature-title">Bookkeeping-Ready</div>
            <div class="feature-desc">Source File, Company, Billed To, Date, Ref, VAT
            Number, VAT, Net/Gross and Total - one row per invoice.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Config check (shown after the hero so the page still renders nicely if
# something's misconfigured)
# ---------------------------------------------------------------------------
try:
    settings = load_settings()
except ConfigError as e:
    st.error(f"Configuration problem: {e}")
    st.stop()

# ---------------------------------------------------------------------------
# Conversion + results
# ---------------------------------------------------------------------------
if uploaded_files and convert_clicked:
    with st.container(key="results-card"):
        st.markdown('<div class="results-heading">Results</div>', unsafe_allow_html=True)

        all_rows = []
        progress = st.progress(0.0)
        status = st.empty()
        errors = []
        failed_rows = {}  # index into all_rows -> error message

        def _record_failure(label, message):
            """Keep a red placeholder row for a failed file/page so it still
            shows in the spreadsheet with its SOURCE FILE."""
            errors.append((label, message))
            failed_rows[len(all_rows)] = message
            all_rows.extend([build_failed_row(label)])

        # Give every upload a unique label: if two files share a name,
        # later ones get "(upload N)" so SOURCE FILE is never ambiguous.
        _seen_names = {}
        def _unique_label(name):
            _seen_names[name] = _seen_names.get(name, 0) + 1
            n = _seen_names[name]
            return name if n == 1 else f"{name} (upload {n})"

        warn_rows = {}  # index into all_rows -> "please check" message

        def _add_invoices(label, result):
            """Turn one extraction result (which may hold SEVERAL invoices -
            e.g. 4 fuel receipts on one scanned page) into one row per
            invoice, with POSITION saying which one it is ("2 of 4 - top
            right"). Flags rows amber when something needs a human check."""
            invoices = result["invoices"]
            if not invoices:
                _record_failure(label, "No invoice or receipt was found on this page/image.")
                with st.expander(f"❌ {label} - no invoices found"):
                    st.error("The model found no invoice or receipt here.")
                return

            count = len(invoices)
            mismatch_msg = None
            if result.get("count_mismatch"):
                mismatch_msg = (
                    f"The model said this page/image has {result['reported_count']} "
                    f"invoice(s) but returned {count}. One may be missing or "
                    f"duplicated - check the source."
                )

            for idx, inv in enumerate(invoices):
                position = format_position(idx, count, inv.get("position"))
                row_index = len(all_rows)
                all_rows.extend(build_rows(inv, label, date_format=date_format, position=position))
                msgs = [m for m in (mismatch_msg, check_amounts(inv)) if m]
                if msgs:
                    warn_rows[row_index] = " | ".join(msgs)

            icon = "⚠️" if mismatch_msg else "✅"
            suppliers = ", ".join((inv.get("supplier") or "?") for inv in invoices)
            with st.expander(f"{icon} {label} - {count} invoice(s): {suppliers}"):
                if mismatch_msg:
                    st.warning(mismatch_msg)
                st.json(invoices)

        def _process_image(label, image_bytes, mime):
            """Run one image (photo, or one page of a scanned PDF) through
            the vision model and add a row for EVERY invoice found on it."""
            try:
                _add_invoices(label, extract_invoices(image_bytes, mime, settings))
            except (VisionAPIError, ParseError) as e:
                _record_failure(label, str(e))
                with st.expander(f"❌ {label} - failed"):
                    st.error(str(e))

        for i, f in enumerate(uploaded_files):
            status.write(f"Processing **{f.name}**...")
            file_bytes = f.read()
            label = _unique_label(f.name)
            is_pdf = f.name.lower().endswith(".pdf") or f.type == "application/pdf"

            if not is_pdf:
                _process_image(label, file_bytes, f.type or "image/jpeg")
                progress.progress((i + 1) / len(uploaded_files))
                continue

            # PDF: try the digital text layer first (cheap, exact, and
            # correct for a single invoice spread across pages, e.g. a
            # multi-page utility bill).
            try:
                text = extract_text_from_pdf(file_bytes)
            except PDFExtractionError:
                text = None  # no text layer -> fall back to page images below

            if text is not None:
                try:
                    _add_invoices(label, extract_invoices_from_text(text, settings))
                except (VisionAPIError, ParseError) as e:
                    _record_failure(label, str(e))
                    with st.expander(f"❌ {label} - failed"):
                        st.error(str(e))
            else:
                # No text layer -> this is a scanned/photographed PDF.
                # Render each page and run it through the vision model
                # separately; each page may itself hold several receipts,
                # and every one of them gets its own row.
                try:
                    page_images = render_pdf_pages_to_images(file_bytes)
                except PDFExtractionError as e:
                    _record_failure(label, str(e))
                    with st.expander(f"❌ {label} - failed (unreadable PDF)"):
                        st.error(str(e))
                    page_images = []

                for page_num, page_png in enumerate(page_images, start=1):
                    page_label = f"{label} (page {page_num})" if len(page_images) > 1 else label
                    _process_image(page_label, page_png, "image/png")

            progress.progress((i + 1) / len(uploaded_files))

        status.write("Done.")

        ok_count = len(all_rows) - len(failed_rows)
        if ok_count:
            xlsx_bytes = build_workbook(
                all_rows, failed=failed_rows, warnings=warn_rows, date_format=date_format
            )
            st.success(
                f"Extracted data from {ok_count} invoice(s) across "
                f"{len(uploaded_files)} uploaded file(s). SOURCE FILE and "
                f"POSITION show exactly where each row came from."
            )
            if warn_rows:
                st.warning(
                    f"{len(warn_rows)} row(s) are shaded amber for a quick check "
                    f"(hover the SOURCE FILE cell in Excel to see why)."
                )
            if errors:
                st.warning(
                    f"{len(errors)} file(s)/page(s) failed - they are in the "
                    f"spreadsheet as red rows so you can check them by hand."
                )
            st.download_button(
                "⬇ Download invoices.xlsx",
                data=xlsx_bytes,
                file_name=f"invoices_{dt.date.today().isoformat()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        else:
            st.error("No invoices could be parsed.")
elif not uploaded_files:
    st.info("Upload one or more invoice/receipt files (images or PDFs) above to begin.")
