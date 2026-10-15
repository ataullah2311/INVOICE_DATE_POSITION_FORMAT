import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from invoice_converter.config import Settings
from invoice_converter.vision_client import _call_model
from invoice_converter.exceptions import VisionAPIError


class _Err(Exception):
    def __init__(self, code): super().__init__(f"Error code: {code}"); self.status_code = code


class _Client:
    def __init__(self, code): self.calls = 0; self.code = code
    @property
    def chat(self): return self
    @property
    def completions(self): return self
    def create(self, **kw):
        self.calls += 1
        raise _Err(self.code)


def test_retired_model_fails_fast_with_clear_message():
    c = _Client(404)
    s = Settings(api_key="k", base_url="u", model="qwen/old-model", max_retries=2)
    try:
        _call_model(c, s, [])
        assert False
    except VisionAPIError as e:
        assert "QWEN_MODEL" in str(e) and "qwen/old-model" in str(e)
    assert c.calls == 1  # no pointless retries


def test_default_model_is_current():
    os.environ.update(QWEN_API_KEY="k", QWEN_BASE_URL="u"); os.environ.pop("QWEN_MODEL", None)
    from invoice_converter.config import load_settings
    assert load_settings().model == "qwen/qwen3.7-plus"
