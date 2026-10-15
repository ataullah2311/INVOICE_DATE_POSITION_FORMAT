"""
Prompt(s) sent to the model. Kept separate from the API-calling code so
prompts can be tuned/versioned without touching request logic.

The extraction rules (JSON shape, what each field means) are shared between
the image path and the PDF-text path via _FIELD_RULES, so the two prompts
can't silently drift out of sync with each other - only the framing at the
top differs, since one describes a photo and the other describes raw
extracted PDF text.

MULTIPLE INVOICES PER PAGE: a single photo or scanned page very often holds
several separate receipts/invoices laid side by side (e.g. 3-4 fuel
receipts scanned onto one A4 sheet). The model must return EVERY one of
them as its own entry in the "invoices" list, plus an "invoice_count" it
states up-front. vision_client checks the two agree, and the app flags the
page for a manual check if they don't.
"""

_FIELD_RULES = """Return ONLY a single JSON object, no markdown fences, no commentary, in
exactly this shape:

{
  "invoice_count": number,
  "invoices": [
    {
      "position": string,
      "ref": string,
      "date": string,
      "supplier": string,
      "billed_to": string,
      "vat_number": string,
      "net_amount": number or null,
      "vat_amount": number or null,
      "total_amount": number or null
    }
  ]
}

HOW MANY INVOICES - read this first:
- The input may contain ONE invoice/receipt or SEVERAL separate ones (for
  example 2-4 till or fuel receipts placed side by side on one scanned
  page or in one photo). Before extracting anything, count every separate
  invoice/receipt that is present, and put that number in
  "invoice_count".
- Return ONE entry in "invoices" for EACH of them - "invoices" must have
  exactly "invoice_count" entries. Never stop after the first one, and
  never merge two different receipts into one entry.
- Include a receipt even if it is faded, creased, partly cut off, or is
  missing some of its figures - fill in whatever IS legible (supplier,
  date, VAT number, ref) and use null for anything that is not printed or
  not readable. A receipt with no VAT breakdown, or whose totals are cut
  off, still gets its own entry.
- Only skip a piece of paper if NOTHING on it can be read at all.
- Count these as ONE invoice, not several:
  * the card-payment slip / "Customer Copy" printed at the bottom of the
    same receipt (same transaction, same amount)
  * torn or crumpled fragments of the same invoice (same supplier and
    the figures belong together)
  * an invoice that continues across several pages of the same document
- Order the entries top-to-bottom, then left-to-right, as they appear.
- "position": where this invoice sits in the image, in plain words, e.g.
  "top left", "top right", "bottom left", "bottom right", "middle", or
  "full page" when there is only one.

Field rules (apply to EACH entry):
- "ref": the invoice/ticket/receipt/order/transaction number if the
  document shows one (e.g. "Invoice No", "Order No", "Receipt", "Trans",
  "Transaction No", "No."). If there is truly no reference number
  present, use null and it will be generated from supplier + date.
- "date": the transaction or invoice date as printed, reformatted to
  DD/MM/YYYY. Prefer a clearly labelled "Date issued"/"Invoice date"
  over other dates on the document (e.g. a billing period's start/end
  dates are NOT the invoice date). If a time is also present, ignore it.
  If part of the date (e.g. the year) is not printed or not legible, copy
  exactly what IS legible rather than guessing the missing part.
- "supplier": the business ISSUING the invoice/receipt - i.e. who was
  paid. Usually the name at the top of the receipt/letterhead (e.g.
  "Toolstation Ltd", "Park Garage Group Plc", "Eastham Service Station",
  "Majors Builders Merchants"). If a fuel station prints both a site name
  and a different operating company, use the site name at the top.
- "billed_to": the business or person the invoice is ADDRESSED TO - a
  distinct "Bill To", "Name", "Customer", "Client", "Invoice To", "To"
  field. Do not reuse the supplier's name here. Till and fuel receipts
  normally don't name a buyer - use null.
- "vat_number": the seller's VAT REGISTRATION number if printed (labels
  vary: "VAT No", "VAT Reg No", "VAT Number"). This is a registration ID,
  NOT a currency amount. Copy it exactly as printed, including spaces.
  If the label is there but no number is printed next to it, or there
  is no VAT number at all, use null - never guess or invent one.
- "net_amount": the amount BEFORE VAT - the value the document labels
  "Net", "Nett", "Ex.VAT", "Excl", "Subtotal (ex. VAT)", "Goods", or
  similar. If it is not printed, use null - do not calculate it.
- "vat_amount": the VAT/tax amount in currency (not a percentage). If a
  document lists several VAT rates, sum them into one figure. If no VAT
  amount is printed, use null - do not assume 0 and do not calculate it.
- "total_amount": the final, VAT-INCLUSIVE total for THIS invoice - the
  value labelled "Total", "Order Total", "Inc.VAT", "Incl", "Invoice
  Total", "Total Paid", or similar. Not a "Current balance", and not the
  cash tendered or change given. If no total is printed (for example a
  handwritten invoice where only the line items were filled in), use
  null - do NOT add up the line items yourself.
- net_amount + vat_amount should equal total_amount when all three are
  printed - if they don't, re-check which figure is which.
- All numeric fields are plain numbers (no currency symbols, no commas).
  A negative amount (credit/refund) keeps its negative sign.
- If the input contains no invoice or receipt at all, return
  {"invoice_count": 0, "invoices": []}.
"""

EXTRACTION_PROMPT = """You are extracting summary data from a photo or scanned
page that contains ONE OR MORE invoices, till receipts, fuel receipts, or
handwritten supplier invoices. These come from small UK businesses
(supermarket and fuel-station receipts, trade counters, wholesale
suppliers, handwritten invoice pads). Receipts may be creased, faded,
torn, overlapping or at an angle.

You only need the INVOICE-LEVEL summary figures for each invoice - not
individual line items.

""" + _FIELD_RULES

TEXT_EXTRACTION_PROMPT = """You are extracting summary data from the text
content of a PDF, already extracted from the PDF's text layer (not an
image). It usually holds a single invoice or bill (supplier invoice,
utility bill, etc.), possibly spread over several pages, but it may hold
several separate invoices. Because it was extracted from a PDF,
formatting like table columns, line breaks, and spacing may be irregular
or flattened - read past that rather than treating odd spacing as
meaningful.

The document text will often contain a lot of boilerplate that is NOT
part of the invoice figures themselves - payment methods, complaints
procedures, terms and conditions, contact details, etc. Ignore it.

You only need the INVOICE-LEVEL summary figures - not individual line
items or meter-reading detail. For a single invoice spread over several
pages, return ONE entry with "position": "full document".

""" + _FIELD_RULES
