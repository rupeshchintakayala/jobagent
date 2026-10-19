import logging
import pytest
from jobagent.budget.guard import BudgetGuard, BudgetExceeded
from jobagent.llm import (LLMClient, FakeProvider, ClaudeProvider, KeyVault, KeyVaultError, InvalidKey, LLMError,
                          mask, cost_eur, estimate_call_eur)
from jobagent.llm.pricing import estimate_tokens


def test_cost_known_models():
    # 1M in + 1M out on haiku = (1+5) USD * 0.92
    assert cost_eur("claude-haiku-4-5", 1_000_000, 1_000_000) == pytest.approx(6 * 0.92)
    assert cost_eur("claude-sonnet-4-5", 1_000_000, 0) == pytest.approx(3 * 0.92)
    assert cost_eur("fake", 10**6, 10**6) == 0


def test_unknown_model_priced_at_most_expensive():
    assert cost_eur("mystery-model", 1_000_000, 0) == pytest.approx(15 * 0.92)


def test_estimate_is_worst_case():
    est = estimate_call_eur("claude-haiku-4-5", "sys", "prompt", 1000)
    assert est >= cost_eur("claude-haiku-4-5", 5, 1000) * 0.99


def test_client_blocks_before_calling_provider_when_over_budget():
    fake = FakeProvider("hello")
    c = LLMClient("u1", fake, BudgetGuard(cap_eur=0.0001))
    with pytest.raises(BudgetExceeded):
        c.complete("s", "p" * 10000, model="claude-sonnet-4-5", max_tokens=4000)
    assert fake.calls == []  # provider never called, nothing spent


def test_client_records_usage_and_spend():
    sink = []
    g = BudgetGuard(cap_eur=15)
    c = LLMClient("u1", FakeProvider("hi there"), g, usage_sink=sink.append)
    r = c.complete("s", "p", model="claude-haiku-4-5")
    assert r.text == "hi there" and len(sink) == 1 and sink[0]["user_id"] == "u1"
    assert g.spent == pytest.approx(sink[0]["cost_eur"]) and g.spent >= 0


def test_budget_accumulates_across_calls_then_blocks():
    g = BudgetGuard(cap_eur=0.002)
    c = LLMClient("u1", FakeProvider("x" * 400), g)
    blocked = False
    for _ in range(50):
        try:
            c.complete("s", "p", model="claude-haiku-4-5", max_tokens=300)
        except BudgetExceeded:
            blocked = True
            break
    assert blocked and g.spent <= 0.002


def test_fake_provider_scripted_responses():
    f = FakeProvider(["a", "b"])
    assert [f.complete("s", "p").text for _ in range(3)] == ["a", "b", "b"]
    f2 = FakeProvider(lambda s, p: p.upper())
    assert f2.complete("s", "abc").text == "ABC"


class _Msg:
    def __init__(self):
        class B: type = "text"; text = "OK"
        class U: input_tokens = 7; output_tokens = 2
        self.content, self.usage = [B()], U()


class _Boom(Exception):
    def __init__(self, status): self.status_code = status; super().__init__("secret-sk-ant-1234 leaked?")


class _SDK:
    def __init__(self, err=None): self.err = err; self.messages = self
    def create(self, **kw):
        if self.err: raise self.err
        self.kw = kw
        return _Msg()


def test_claude_provider_parses_response_without_network():
    sdk = _SDK()
    p = ClaudeProvider("sk-ant-test-1234", client=sdk)
    r = p.complete("sys", "hi", model="claude-haiku-4-5", max_tokens=10)
    assert (r.text, r.input_tokens, r.output_tokens) == ("OK", 7, 2)
    assert sdk.kw["system"] == "sys" and sdk.kw["max_tokens"] == 10


def test_claude_invalid_key_maps_and_never_leaks_key():
    p = ClaudeProvider("sk-ant-test-1234", client=_SDK(_Boom(401)))
    with pytest.raises(InvalidKey) as e:
        p.complete("s", "p")
    assert "sk-ant" not in str(e.value)
    p2 = ClaudeProvider("sk-ant-test-1234", client=_SDK(_Boom(500)))
    with pytest.raises(LLMError) as e2:
        p2.complete("s", "p")
    assert "sk-ant" not in str(e2.value) and "1234" not in str(e2.value)


def test_vault_roundtrip_and_ciphertext_hides_key():
    v = KeyVault(KeyVault.generate_master_key())
    tok = v.encrypt("sk-ant-secret-9999")
    assert b"secret" not in tok and v.decrypt(tok) == "sk-ant-secret-9999"


def test_vault_wrong_master_key_fails_cleanly():
    tok = KeyVault(KeyVault.generate_master_key()).encrypt("sk-ant-x")
    with pytest.raises(KeyVaultError):
        KeyVault(KeyVault.generate_master_key()).decrypt(tok)


def test_vault_requires_master_key(monkeypatch):
    monkeypatch.delenv("JOBAGENT_MASTER_KEY", raising=False)
    with pytest.raises(KeyVaultError):
        KeyVault()
    with pytest.raises(KeyVaultError):
        KeyVault("not-a-valid-key")


def test_mask():
    assert mask("sk-ant-api03-abcdWXYZ") == "****WXYZ" and mask("short") == "****"


def test_key_not_logged(caplog):
    caplog.set_level(logging.DEBUG)
    key = "sk-ant-api03-SUPERSECRET"
    p = ClaudeProvider(key, client=_SDK())
    LLMClient("u1", p, BudgetGuard(15)).complete("s", "p", model="claude-haiku-4-5")
    assert "SUPERSECRET" not in caplog.text
