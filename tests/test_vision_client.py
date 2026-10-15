"""Tests for the model-response parsing in vision_client - no API calls."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from invoice_converter.vision_client import _validate_shape, _extract_json_object
from invoice_converter.exceptions import ParseError


def _inv(**kw):
    base = {"ref": None, "date": None, "supplier": None, "billed_to": None, "vat_number": None,
            "net_amount": None, "vat_amount": None, "total_amount": None}
    base.update(kw)
    return base


def test_multiple_invoices_all_returned():
    raw = {"invoice_count": 3, "invoices": [
        _inv(supplier="Park Garage Group Plc", total_amount=40.01, position="top left"),
        _inv(supplier="BP Express Shopping Limited", total_amount=40.03, position="top right"),
        _inv(supplier="Muhammads Pharmacy", total_amount=8.99, position="bottom right"),
    ]}
    r = _validate_shape(raw)
    assert len(r["invoices"]) == 3
    assert r["reported_count"] == 3 and r["count_mismatch"] is False


def test_count_mismatch_detected():
    r = _validate_shape({"invoice_count": 4, "invoices": [_inv(supplier="A"), _inv(supplier="B")]})
    assert r["count_mismatch"] is True and r["reported_count"] == 4


def test_old_single_invoice_shape_still_accepted():
    r = _validate_shape(_inv(supplier="Tesco", total_amount=5.0))
    assert len(r["invoices"]) == 1 and r["invoices"][0]["supplier"] == "Tesco"
    assert r["count_mismatch"] is False


def test_bare_list_accepted():
    r = _validate_shape([_inv(supplier="A"), _inv(supplier="B")])
    assert [i["supplier"] for i in r["invoices"]] == ["A", "B"]


def test_empty_page():
    r = _validate_shape({"invoice_count": 0, "invoices": []})
    assert r["invoices"] == [] and r["count_mismatch"] is False


def test_invoice_missing_key_raises():
    bad = _inv(supplier="A"); del bad["vat_number"]
    try:
        _validate_shape({"invoice_count": 1, "invoices": [bad]})
        assert False, "expected ParseError"
    except ParseError:
        pass


def test_json_wrapped_in_text_or_fences():
    assert _extract_json_object('```json\n{"invoice_count": 0, "invoices": []}\n```')["invoice_count"] == 0
    assert _extract_json_object('Here you go: {"invoice_count": 0, "invoices": []} done')["invoices"] == []
    assert len(_extract_json_object('[{"a": 1}, {"a": 2}] trailing')) == 2


if __name__ == "__main__":
    import traceback
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except Exception:
            failed += 1; print(f"FAIL {t.__name__}"); traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
