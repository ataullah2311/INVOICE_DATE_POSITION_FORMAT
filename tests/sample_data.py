"""
Hand-transcribed data from the real sample invoices reviewed for this
project. Used by tests to validate parsing and xlsx output without calling
the vision API.

supplier    = who ISSUED the invoice (letterhead/logo, or a company-details
              box on a blank invoice pad).
billed_to   = who the invoice is ADDRESSED TO ("Bill To" / "Name" /
              "Invoice To" / "TO:" field) - a different name from supplier
              whenever the document names one. Several real samples make
              this obvious: Caribbean Gold's invoice literally has
              "FROM: Caribbean Gold" / "TO: Common Sense"; Major Foods'
              invoice has "Invoice To: Foods Van Ltd T/A Shah's Halal";
              Yaseen Fruit & Veg addresses "Bedford freash fish" (their own
              typo, preserved as printed). Left None on till receipts,
              which don't name a buyer at all.

net_amount / vat_amount reflect what each document actually prints
separately from its total - left as None when the document doesn't break
the total down that way (many handwritten trade invoices don't).
Note: net_amount + vat_amount = total_amount, and total_amount is what
lands in the spreadsheet's GROSS AMOUNT column (see parser.py's
module docstring for why the column name and JSON field name differ).

vat_number is the seller's VAT REGISTRATION number (not an amount) -
copied exactly as printed on each document; left None where the document
shows none.
"""

SAMPLES = [
    {  # Tesco Petrol - Barking PFS: "VAT RECEIPT SUMMARY Net £43.34 VAT £8.67", Total £52.01
        "ref": None, "date": "14/09/2025", "supplier": "Tesco Petrol Filling Station",
        "billed_to": None, "vat_number": "220430231",
        "net_amount": 43.34, "vat_amount": 8.67, "total_amount": 52.01,
    },
    {  # Holland Bazaar Cash & Carry: "GOODS 119.55, V.A.T. 8.10, TOTAL E.&O.E 127.65" - no named customer on this ticket
        "ref": "6297406", "date": "04/07/2025", "supplier": "Holland Bazaar Cash & Carry",
        "billed_to": None, "vat_number": "802 6418 53",
        "net_amount": 119.55, "vat_amount": 8.10, "total_amount": 127.65,
    },
    {  # Tesco Rainham Extra - red cabbage; no separate VAT breakdown printed on this receipt
        "ref": None, "date": "11/07/2025", "supplier": "Tesco Rainham Extra",
        "billed_to": None, "vat_number": "GB 220 4302 31",
        "net_amount": None, "vat_amount": None, "total_amount": 4.74,
    },
    {  # Aldi Dalston: "A 00.0% Net 8.70 Vat 0.00", Total £8.70 - VAT number not legible in photo
        "ref": None, "date": "11/11/2025", "supplier": "Aldi Stores Kingsland Shopping Centre",
        "billed_to": None, "vat_number": None,
        "net_amount": 8.70, "vat_amount": 0.00, "total_amount": 8.70,
    },
    {  # Baboo Wholesale Meats - "Name: Bedford Fish & Meat" field is the billed_to
        "ref": "217501", "date": "22/10/2025", "supplier": "Baboo Wholesale Meats Ltd",
        "billed_to": "Bedford Fish & Meat", "vat_number": "849022818",
        "net_amount": None, "vat_amount": None, "total_amount": 634.62,
    },
    {  # Yaseen Fruit & Veg: "Bill to: Bedford freash fish" (their own typo, kept as printed)
        "ref": "243685", "date": "05/11/2025", "supplier": "Yaseen Fruits & Veg Ltd",
        "billed_to": "Bedford freash fish", "vat_number": "368599818",
        "net_amount": 487.60, "vat_amount": 0.00, "total_amount": 487.60,
    },
    {  # Major Foods Limited: "Invoice To: Foods Van Ltd T/A Shah's Halal"
        "ref": "SI-000017", "date": "01/09/2025", "supplier": "Major Foods Limited",
        "billed_to": "Foods Van Ltd T/A Shah's Halal", "vat_number": "GB 170405145",
        "net_amount": 268.82, "vat_amount": 14.80, "total_amount": 283.62,
    },
    {  # Caribbean Gold handwritten - literally "FROM: Caribbean Gold" / "TO: Common Sense"
        "ref": None, "date": None, "supplier": "Caribbean Gold",
        "billed_to": "Common Sense", "vat_number": None,
        "net_amount": None, "vat_amount": None, "total_amount": 402.00,
    },
    {  # Handwritten repair invoice No. 11 - "Bill to Shah,Dalston Limited"
        # Supplier's own name is handwritten in a details box and not
        # confidently legible - left as None rather than guessed.
        "ref": "11", "date": "13/11/2025", "supplier": None,
        "billed_to": "Shah, Dalston Limited", "vat_number": None,
        "net_amount": 450.00, "vat_amount": None, "total_amount": 450.00,
    },
]
