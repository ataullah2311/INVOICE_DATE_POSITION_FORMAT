"""
Wraps calls to the model (default: qwen/qwen3.7-plus via an
OpenAI-compatible endpoint) behind two functions:

  - extract_invoices(file_bytes, mime, settings)  - image path (vision)
  - extract_invoices_from_text(text, settings)    - PDF-text path (no
                                                      vision needed, since
                                                      the text is already
                                                      digital)

Both return EVERY invoice found in the input (a photo or scanned page often
holds several receipts side by side), as a dict:

    {
        "invoices": [ {ref, date, supplier, ..., position}, ... ],
        "reported_count": int | None,   # how many the model said it saw
        "count_mismatch": bool,         # True if that != len(invoices)
    }

Both retry on transient API failures and validate the JSON shape before
handing it back, sharing the same parsing/validation helpers so the two
paths can never silently drift into producing differently-shaped output.

Any failure raises a specific exception (VisionAPIError / ParseError)
rather than letting a raw requests/openai exception bubble up.
"""
import base64
import json
import time
from typing import Optional

from .config import Settings
from .exceptions import VisionAPIError, ParseError
from .prompts import EXTRACTION_PROMPT, TEXT_EXTRACTION_PROMPT

INVOICE_KEYS = {"ref", "date", "supplier", "billed_to", "vat_number", "net_amount", "vat_amount", "total_amount"}
# kept for backwards compatibility with anything importing the old name
REQUIRED_KEYS = INVOICE_KEYS

def _encode_image(file_bytes: bytes, mime: str) -> str:
    b64 = base64.b64encode(file_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def _get_client(settings: Settings):
    # Imported lazily so importing this module doesn't require `openai`
    # to be installed unless you actually call one of the extract_* functions.
    try:
        from openai import OpenAI
    except ImportError as e:
        raise VisionAPIError(
            "The 'openai' package is required to call the model. "
            "Install it with: pip install openai"
        ) from e
    return OpenAI(api_key=settings.api_key, base_url=settings.base_url)


def _call_model(client, settings: Settings, messages: list) -> str:
    last_error: Optional[Exception] = None
    for attempt in range(settings.max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=settings.model,
                messages=messages,
                temperature=0,
                timeout=settings.request_timeout,
            )
            content = response.choices[0].message.content
            if not content or not content.strip():
                raise VisionAPIError("Model returned an empty response.")
            return content.strip()
        except Exception as e:  # noqa: BLE001 - deliberately broad, wrapped below
            last_error = e
            status = getattr(e, "status_code", None)
            if status in (400, 401, 402, 403, 404):
                # Retrying can't fix these - fail straight away with a clear hint.
                hint = {
                    401: "The API key was rejected - check QWEN_API_KEY in .env.",
                    402: "The API account is out of credit - top up at the provider.",
                    403: "The API key isn't allowed to use this model - check the provider account.",
                    404: (f"The model '{settings.model}' is not available (it may have been "
                          f"retired by the provider). Change QWEN_MODEL in .env to a current "
                          f"vision model, then restart the app."),
                }.get(status, "The request was rejected by the API.")
                raise VisionAPIError(f"{hint} Details: {e}") from e
            if attempt < settings.max_retries:
                time.sleep(1.5 * (attempt + 1))
                continue
    raise VisionAPIError(f"API call failed after {settings.max_retries + 1} attempt(s): {last_error}") from last_error


def _strip_markdown_fence(raw: str) -> str:
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _extract_json_object(raw: str):
    raw = _strip_markdown_fence(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        if raw.lstrip().startswith("["):
            lstart, lend = raw.find("["), raw.rfind("]")
            if lstart != -1 and lend > lstart:
                try:
                    return json.loads(raw[lstart : lend + 1])
                except json.JSONDecodeError:
                    pass
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ParseError(f"Model response was not valid JSON and no JSON object could be located: {raw[:300]!r}")
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError as e:
            raise ParseError(f"Model response could not be parsed as JSON: {e}. Raw (truncated): {raw[:300]!r}") from e


def _validate_invoice(inv, index: int) -> dict:
    if not isinstance(inv, dict):
        raise ParseError(f"Invoice #{index + 1} in the model's list is not a JSON object.")
    missing = INVOICE_KEYS - inv.keys()
    if missing:
        raise ParseError(f"Invoice #{index + 1} is missing required key(s): {sorted(missing)}")
    inv.setdefault("position", None)
    return inv


def _validate_shape(parsed) -> dict:
    """Validate the model's JSON and normalise it to
    {"invoices": [...], "reported_count": int|None, "count_mismatch": bool}.

    Accepts the multi-invoice shape {"invoice_count": N, "invoices": [...]},
    a bare list of invoices, or the old single-invoice object (wrapped into
    a one-item list) so an older-style answer is never lost."""
    reported = None
    if isinstance(parsed, list):
        invoices = parsed
    elif isinstance(parsed, dict) and "invoices" in parsed:
        invoices = parsed["invoices"]
        reported = parsed.get("invoice_count")
    elif isinstance(parsed, dict) and INVOICE_KEYS & parsed.keys():
        invoices = [parsed]  # old single-invoice shape
    else:
        raise ParseError(f"Unexpected JSON shape from the model: {str(parsed)[:300]!r}")

    if not isinstance(invoices, list):
        raise ParseError('"invoices" must be a list.')
    invoices = [_validate_invoice(inv, i) for i, inv in enumerate(invoices)]

    try:
        reported = int(reported) if reported is not None else None
    except (TypeError, ValueError):
        reported = None

    return {
        "invoices": invoices,
        "reported_count": reported,
        "count_mismatch": reported is not None and reported != len(invoices),
    }


def extract_invoices(file_bytes: bytes, mime: str, settings: Settings) -> dict:
    """Send one IMAGE (a photo, or one rendered page of a scanned PDF) to
    the vision model and return every invoice/receipt found on it - see
    the module docstring for the returned shape.

    Raises:
        VisionAPIError - the API call itself failed after retries.
        ParseError     - the model responded but the content wasn't
                         valid/complete JSON in the expected shape.
    """
    client = _get_client(settings)
    data_url = _encode_image(file_bytes, mime)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": EXTRACTION_PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]
    raw = _call_model(client, settings, messages)
    parsed = _extract_json_object(raw)
    return _validate_shape(parsed)


def extract_invoices_from_text(text: str, settings: Settings) -> dict:
    """Send TEXT already extracted from a digital PDF to the model as plain
    text and return every invoice found in it - same shape as
    extract_invoices().

    Raises:
        VisionAPIError - the API call itself failed after retries.
        ParseError     - the model responded but the content wasn't
                         valid/complete JSON in the expected shape.
    """
    client = _get_client(settings)
    messages = [
        {
            "role": "user",
            "content": TEXT_EXTRACTION_PROMPT + "\n\n---\n\nDocument text:\n\n" + text,
        }
    ]
    raw = _call_model(client, settings, messages)
    parsed = _extract_json_object(raw)
    return _validate_shape(parsed)
