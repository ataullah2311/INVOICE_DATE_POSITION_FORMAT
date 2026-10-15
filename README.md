# Invoice / Receipt → Excel Converter

Upload photos of invoices, till receipts, or handwritten supplier notes and
get back a single `.xlsx` with columns:

```
SOURCE FILE | POSITION | COMPANY NAME | BILLED TO | DATE | REF/INVOICE NO | VAT NUMBER | GROSS AMOUNT | VAT AMOUNT | NET AMOUNT
```

One row per invoice, plus a GRAND TOTAL row at the bottom summing
GROSS AMOUNT (the final total) across every invoice in the batch.
NET AMOUNT + VAT AMOUNT = GROSS AMOUNT.

Built for a small UK food/retail business's actual paperwork mix:
supermarket receipts (Tesco, Aldi, Lidl), fuel station receipts, printed
wholesale supplier invoices (Holland Bazaar, Yaseen Fruit & Veg, Major
Foods), and handwritten trade invoices (Baboo Wholesale Meats, Caribbean
Gold).

## Project structure

```
invoice_converter_project/
├── app.py                        # Streamlit UI - the thing you run
├── assets/
│   └── styles.css                  # UI theme (gradient hero, cards, buttons)
├── invoice_converter/             # the actual package - importable, testable
│   ├── __init__.py                 # public API surface
│   ├── config.py                   # env var loading + validation
│   ├── exceptions.py                # ConfigError / VisionAPIError / ParseError / PDFExtractionError
│   ├── prompts.py                    # extraction prompts (image + PDF-text variants)
│   ├── vision_client.py               # API calls (image + text) + retries + validation
│   ├── pdf_extractor.py                # pdfplumber text extraction for digital PDFs
│   ├── parser.py                       # invoice JSON -> spreadsheet row, date formatting
│   └── xlsx_writer.py                   # rows -> formatted .xlsx bytes
├── tests/
│   ├── test_vision_client.py        # multi-invoice response parsing
│   ├── sample_data.py              # hand-transcribed real sample invoices (images)
│   ├── fixtures/
│   │   ├── sample_utility_bill.pdf   # synthetic digital-text PDF fixture
│   │   └── scanned_no_text.pdf        # synthetic image-only (no text) PDF fixture
│   ├── test_parser.py               # unit tests for parser.py
│   ├── test_pdf_extractor.py         # unit tests for pdf_extractor.py
│   └── test_xlsx_writer.py           # unit tests for xlsx_writer.py
├── requirements.txt
└── .env.example                 # copy to .env and add your key
```

Why split it up this way:
- **`vision_client.py` and `parser.py`/`xlsx_writer.py` don't import each
  other's dependencies.** The row-shaping and Excel-writing code has zero
  dependency on `openai` or Streamlit, so you can unit-test it (and did,
  in `tests/`) without an API key, network access, or a browser.
- **Every failure mode has its own exception class** (`ConfigError`,
  `VisionAPIError`, `ParseError`). The Streamlit app catches
  `VisionAPIError`/`ParseError` separately and shows you exactly which
  file failed and why, instead of one generic "something broke" message.
- **The model's JSON response is validated before use**
  (`vision_client._validate_shape`), so a malformed or partial response
  fails fast with a clear error rather than silently producing a
  half-populated or crashed spreadsheet.

## Setup

```bash
cd invoice_converter_project
pip install -r requirements.txt
cp .env.example .env
# edit .env with your actual QWEN_API_KEY / QWEN_BASE_URL
streamlit run app.py
```

`QWEN_BASE_URL` should point at whatever OpenAI-compatible endpoint you're
already using for your qwen vision model (OpenRouter, DashScope
compatible-mode, a self-hosted vLLM server, etc.) — the client code is
generic and works with any of them.

## Several invoices on one page / photo

A single photo or scanned page often holds several receipts side by side
(e.g. 3-4 fuel receipts on one A4 scan). **Every one of them gets its own
row** - the model is asked to first count the invoices it can see
(`invoice_count`), then return one entry per invoice (`invoices` list).

- A receipt is included even if it has no VAT breakdown, or its totals are
  cut off: supplier, date, VAT number and ref are filled in, and any
  amount that isn't printed is left **blank** (never calculated, never 0).
- Handwritten invoices with no printed total keep GROSS blank - the model
  is told not to add up line items itself.
- The card slip printed under the same receipt, torn fragments of one
  invoice, and one invoice running over several pages each count as ONE.
- If the count the model states doesn't match the list it returns, every
  row from that page is shaded **amber** with a note, so a missed or
  duplicated receipt can't slip past unnoticed.
- Rows where NET + VAT doesn't equal GROSS (beyond 1p rounding) are also
  shaded amber with a note.

Scanned pages are rendered at 2.5x (about 180 DPI) so small receipt print
stays legible when several receipts share a page.

## Source file + position columns (cross-checking)

The first column, **SOURCE FILE**, shows which uploaded file each row came
from, so any figure can be traced straight back to its original:

- Photo / digital PDF: the file name, e.g. `Holland Bazaar Oct.pdf`
- Scanned multi-invoice PDF: file name + page, e.g. `scan_batch.pdf (page 3)`
- Two uploads with the same name: the later one is `name.jpg (upload 2)`

**POSITION** says which invoice on that page it is, e.g. `2 of 4 - top
right`. The "2 of 4" is the row's order on that page (top-to-bottom, then
left-to-right); the "top right" is the model's description of where it
sits, to find it quickly.

SOURCE FILE comes from the app itself (the uploaded file name and page
counter), **never from the AI model**, so it cannot be misread or
hallucinated - it is always exactly right.

Files/pages that fail extraction are **not dropped**: they appear as a
red row with `EXTRACTION FAILED - check source` and the error message as a
comment on the SOURCE FILE cell. So the sheet always has one row per
invoice uploaded, and nothing goes missing silently. Rows stay in upload
order.

## Date format

Before converting, the app shows a **Date format** dropdown (in the
upload card) with five options: `DD/MM/YYYY (UK)` (default),
`MM/DD/YYYY (US)`, `YYYY-MM-DD (ISO)`, `DD-MM-YYYY`, and `DD Mon YYYY`.
Whichever one is selected is applied to the DATE column for every
invoice in that conversion run.

Under the hood, `parser._reformat_date`:
- Parses the date string the model extracted (the prompt always asks for
  DD/MM/YYYY, but a few other common shapes - ISO, US - are also
  recognized as a fallback, since not every real document's date makes
  it through cleanly)
- Only converts a date when the **day, month and year are all actually
  printed**. A missing or illegible part is never filled in - e.g. a
  scribbled `20-8-2` stays `20-8-2` (not 20/08/2002), `05 Sep` stays
  `05 Sep` (no year added), `30/07/2?24` stays as is
- Always assumes **day-first** when the format is ambiguous (`05/09/2026`
  is read as 5 September, not 9 May) - this matches the UK convention
  the extraction prompt uses
- If a date genuinely can't be parsed, it's **left exactly as extracted**
  rather than guessed at or blanked out - a date the person can see and
  fix by eye is safer than one silently mangled

To add another format option, add an entry to `DATE_FORMAT_OPTIONS` in
`parser.py` (label -> strftime pattern) - `app.py`'s dropdown reads that
dict directly, so no separate UI change is needed.

### Real Excel dates (monthly filter)

Every date the app could read in full is written as a **real Excel date**,
displayed in the format chosen in the dropdown. That's what makes Excel's
filter on the DATE column group by **Year > Month > Day** (tick a whole
month at once, e.g. July 2026). Dates kept as printed because part was
illegible (e.g. `20-8-2`) stay as text and appear separately at the bottom
of the filter list, so they stand out for checking. The filter buttons are
switched on automatically when the file opens.

## PDF support

Upload a `.pdf` alongside your images and the app figures out which of
two very different kinds of PDF it's looking at, automatically:

**1. Digital PDFs with a real text layer** (an emailed utility bill, an
invoice exported from accounting software) — `pdf_extractor.
extract_text_from_pdf` pulls the text straight out with `pdfplumber`, no
vision model call needed, then that text is sent to the model as plain
text via `vision_client.extract_invoice_from_text`, using the same JSON
schema and validation as the image path. Usually **one invoice per file**,
even if it spans several pages (like the EDF energy bill example this was
built against).

**2. Scanned or photographed PDFs with no text layer at all** — common
when several paper invoices get scanned or photographed together into one
PDF (a real example: an 8-page PDF containing 8 completely different
invoices from different suppliers, one per page, with zero selectable
text on any page — Holland Bazaar, several 5 Star Food Distribution
invoices, a couple from Extra Cash & Carry, one from Nella Cutlery). In
this case `extract_text_from_pdf` correctly finds no text and raises
`PDFExtractionError`, which the app catches as the signal to fall back to
`pdf_extractor.render_pdf_pages_to_images` — each page is rendered to a
PNG with `pypdfium2` and sent through the vision model **separately**, so
a batch like that produces **one row per page**, not one row for the
whole file (which would have mashed 8 unrelated invoices into one
nonsensical extraction attempt - this was the actual bug that motivated
building the fallback rather than just leaving PDFs at "digital text
only").

Either way, results land in the same spreadsheet format. If a PDF is
completely unreadable even as images (corrupted file, etc.), that's
reported as a per-file failure without stopping the rest of the batch.

**Why not just send every PDF page through the vision model as an image,
always, and skip the text-extraction path entirely?** Because a digital
PDF's text is already exact — no OCR risk, and cheaper (a big multi-page
bill in text form is far fewer tokens than the same pages as images).
The trade-off worth knowing on the text path specifically: multi-page
utility bills carry a lot of boilerplate (payment methods, complaints
procedures, fuel-mix tables) that a photo of a single receipt never has,
and some print a "Current balance" figure right next to the actual
"Total charges for this period" - the text prompt is explicit about
using the latter, not the former, since grabbing the wrong one is an
easy mistake to make on this document type specifically.

## Running the tests

No API key or network needed — these test the parsing/Excel/PDF-text
logic only, against hand-transcribed sample invoice data and a synthetic
test PDF (not real invoice data):

```bash
python tests/test_parser.py
python tests/test_pdf_extractor.py
python tests/test_xlsx_writer.py
```

Or with pytest, if you have it installed:

```bash
pip install pytest
pytest tests/
```

## Design decisions worth knowing

1. **One row per invoice, not one row per line item.** This version only
   extracts invoice-level totals - Company Name, Date, Ref, VAT Number,
   Total, Gross, VAT - so there's no line-item detail in the output and
   no per-invoice row grouping to manage.
2. **COMPANY NAME vs BILLED TO are different things, kept in separate
   columns on purpose.** COMPANY NAME is who issued the invoice (the
   letterhead/logo, or a handwritten company-details box). BILLED TO is
   who the invoice is addressed to (a "Bill To"/"Name"/"Invoice To"/"TO:"
   field) - very often the client's own business across this project's
   documents, since they're the one being invoiced. Real examples that
   make the distinction obvious: Caribbean Gold's invoice literally reads
   "FROM: Caribbean Gold" / "TO: Common Sense"; a handwritten repair
   invoice names the customer "Shah, Dalston Limited" in a "Bill to"
   field while the issuer's own name (scrawled in a company-details box)
   was illegible enough that the model correctly returned it as blank
   rather than guessing. Left blank on till receipts, which don't name a
   buyer at all.
3. **VAT NUMBER vs VAT AMOUNT are different things, kept in separate
   columns on purpose.** VAT NUMBER is the seller's VAT *registration*
   ID (e.g. `"GB170405145"` - often contains letters, never used in
   arithmetic). VAT AMOUNT is the VAT *charged* in currency. The prompt
   is explicit about not confusing the two, since both are commonly
   labelled "VAT" on the document itself.
4. **NET AMOUNT vs VAT AMOUNT vs GROSS AMOUNT** follow standard UK
   accounting terminology - **NET + VAT = GROSS**:
   - NET AMOUNT = the pre-VAT figure (document labels it "Net", "Net
     charges", "Goods", "Sub Total", etc.) - internally this is the
     model's `net_amount` field.
   - VAT AMOUNT = the VAT/tax charged, in currency (not a percentage).
   - GROSS AMOUNT = the final, VAT-inclusive total (document labels it
     "Total", "Invoice Total", "Total charges for this period", etc.) -
     internally this is the model's `total_amount` field. The GRAND
     TOTAL row at the bottom of the sheet sums this column.

   The spreadsheet column names and the underlying JSON field names are
   **deliberately not 1:1** here (`total_amount` -> GROSS AMOUNT column,
   `net_amount` -> NET AMOUNT column) - see the big comment at the top of
   `parser.py` if you're extending this, since it's the one spot in the
   codebase where "the column name" and "the field that fills it" don't
   match, and that's exactly what caused a real bug once already.
5. **NET/VAT are left blank (not zero) when a document doesn't print
   them separately, but GROSS still shows.** Several real samples (Baboo Wholesale Meats,
   Caribbean Gold) only show a single total with no VAT breakdown at
   all - the prompt is explicit about not guessing a 0.00 in that case,
   since a real 0% VAT line and "no VAT information printed" are
   different facts.
6. **REF fallback**: several sample receipts (Tesco, Aldi) print no
   invoice/ticket number at all. In that case REF becomes
   `"<Supplier> <date>"` so every invoice still gets a distinct
   reference; falls back to the filename if even that's missing.
7. **Malformed numeric fields never crash the run.** `parser._to_number`
   coerces things like `"£100.00"` or a stray `"n/a"` to a float or
   `None` rather than raising.
8. **GRAND TOTAL row**: `xlsx_writer.build_workbook` appends a bolded
   `GRAND TOTAL` row summing the GROSS AMOUNT column across every invoice
   in the batch. Remove the block under "Grand-total row" in
   `xlsx_writer.py` if you don't want it.

## UI

`app.py` uses `st.container(key=...)` (Streamlit 1.31+, hence the pinned
`streamlit>=1.35` in requirements.txt) to apply the gradient hero /
white-card styling in `assets/styles.css`. If you rename or remove a
`st.container(key="...")` in `app.py`, update the matching `.st-key-<name>`
selector in `assets/styles.css` to match — they're linked by that key
name, not automatically kept in sync.

## Extending it

- **Model retired?** Providers retire models from time to time (Qwen3 VL
  32B Instruct was retired on OpenRouter on 9 Oct 2026). The app then shows
  "The model ... is not available" straight away instead of retrying.
  Fix: set `QWEN_MODEL` in `.env` to a current model that accepts **image
  input** (default now `qwen/qwen3.7-plus`) and restart the app.
- **Swap models/providers**: change `QWEN_MODEL` / `QWEN_BASE_URL` in
  `.env` — nothing else needs to change as long as the endpoint is
  OpenAI-chat-completions-compatible with image input.
- **Add line-item detail back**: this version deliberately dropped
  per-line extraction (qty/description/price) to keep the output to the
  six requested columns. If you need it again later, the previous
  line-item schema is straightforward to re-add to `prompts.py`,
  `vision_client.py`, and `parser.py` - ask and it can be restored or
  added as an optional second output sheet.
- **Add/reorder a column**: extend `HEADERS` in `xlsx_writer.py` and the
  row-building in `parser.build_rows` together — they must stay the same
  length (there's a `ValueError` guard for this in
  `xlsx_writer.build_workbook`).
