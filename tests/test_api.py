import json
import pytest
from fastapi.testclient import TestClient
from jobagent.config import Settings
from jobagent.llm import FakeProvider, InvalidKey, KeyVault
from jobagent.web import create_app
from test_web import PROFILE, JOB, fake, BadKeyProvider

PW = "correct horse battery"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBAGENT_MASTER_KEY", KeyVault.generate_master_key())
    monkeypatch.setenv("JOBAGENT_CORS_ORIGINS", "https://rupesh.github.io")
    return create_app(Settings(db_url=f"sqlite:///{tmp_path/'a.db'}"), provider_factory=lambda k: FakeProvider(fake),
                      fetch_jobs=lambda s: [JOB], secret="y" * 40, run_in_background=False)


def new_user(app, email="ada@example.com"):
    c = TestClient(app)
    r = c.post("/api/signup", json={"email": email, "password": PW})
    assert r.status_code == 200, r.text
    c.headers["Authorization"] = "Bearer " + r.json()["token"]
    return c


def ready_user(app, email="ada@example.com"):
    c = new_user(app, email)
    assert c.put("/api/key", json={"api_key": "sk-ant-api03-SECRETKEY1234", "cap_eur": 15}).status_code == 200
    assert c.post("/api/profile/upload", files={"cv": ("cv.txt", b"Ada. Python engineer.")}).status_code == 200
    p = c.get("/api/profile").json()["data"]
    assert c.put("/api/profile?confirm=true", json=p).status_code == 200
    return c


def test_auth_required(app):
    c = TestClient(app)
    for m, p in [("get", "/api/me"), ("get", "/api/profile"), ("get", "/api/applications"), ("post", "/api/run"),
                 ("get", "/api/policies"), ("put", "/api/key")]:
        assert getattr(c, m)(p).status_code in (401, 422), p
    c.headers["Authorization"] = "Bearer forged|abc|9999999999|deadbeef"
    assert c.get("/api/me").status_code == 401


def test_signup_login_validation(app):
    c = TestClient(app)
    assert c.post("/api/signup", json={"email": "bad", "password": PW}).status_code == 400
    assert c.post("/api/signup", json={"email": "a@b.ie", "password": "short"}).status_code == 400
    new_user(app)
    assert c.post("/api/signup", json={"email": "ada@example.com", "password": PW}).status_code == 400
    assert c.post("/api/login", json={"email": "ada@example.com", "password": "nope nope nope"}).status_code == 400
    r = c.post("/api/login", json={"email": "ada@example.com", "password": PW})
    assert r.status_code == 200 and r.json()["token"]


def test_invite_code(app, monkeypatch):
    monkeypatch.setenv("JOBAGENT_INVITE_CODE", "friends")
    c = TestClient(app)
    assert c.get("/api/invite-required").json() == {"required": True}
    assert c.post("/api/signup", json={"email": "a@b.ie", "password": PW}).status_code == 400
    assert c.post("/api/signup", json={"email": "a@b.ie", "password": PW, "invite": "friends"}).status_code == 200


def test_full_flow(app):
    c = ready_user(app)
    me = c.get("/api/me").json()
    assert me["has_key"] and me["profile_confirmed"] and me["counts"]["drafted"] == 0
    assert c.post("/api/run").json()["state"] == "done"
    items = c.get("/api/applications").json()
    assert len(items) == 1 and items[0]["score"] == 88 and items[0]["quota_remaining"] == 3
    aid = items[0]["id"]
    full = c.get(f"/api/applications/{aid}").json()
    assert "Cut p95 latency by 40%" in full["cv"]
    assert c.post(f"/api/applications/{aid}/applied").status_code == 409        # must approve first
    assert c.post(f"/api/applications/{aid}/approve").json() == {"status": "approved"}
    assert c.get(f"/api/applications/{aid}").json()["quota_remaining"] == 2      # approved-pending counts
    assert c.post(f"/api/applications/{aid}/approve").status_code == 409        # no double approve
    assert c.post(f"/api/applications/{aid}/applied").json() == {"status": "submitted"}
    assert len(c.get("/api/applications?status=submitted").json()) == 1


def test_key_never_returned_and_bad_key_rejected(app, tmp_path, monkeypatch):
    c = ready_user(app)
    body = c.get("/api/key").text + c.get("/api/me").text
    assert "SECRETKEY" not in body and "****1234" in body
    a2 = create_app(Settings(db_url=f"sqlite:///{tmp_path/'b.db'}"), provider_factory=lambda k: BadKeyProvider(fake),
                    fetch_jobs=lambda s: [], secret="y" * 40, run_in_background=False)
    c2 = new_user(a2)
    assert c2.put("/api/key", json={"api_key": "sk-bad", "cap_eur": 15}).status_code == 400
    assert c2.get("/api/key").json() == {"saved": False}


def test_run_requires_key_and_confirmed_profile(app):
    c = new_user(app)
    assert c.post("/api/run").status_code == 400
    c.put("/api/key", json={"api_key": "sk-ant-x1234", "cap_eur": 15})
    assert c.post("/api/run").status_code == 400


def test_users_isolated(app):
    a = ready_user(app, "a@x.ie"); a.post("/api/run")
    aid = a.get("/api/applications").json()[0]["id"]
    b = new_user(app, "b@x.ie")
    assert b.get(f"/api/applications/{aid}").status_code == 404
    assert b.post(f"/api/applications/{aid}/approve").status_code == 404
    assert b.get("/api/applications").json() == []
    assert a.get(f"/api/applications/{aid}").json()["status"] == "drafted"


def test_confirmed_profile_locked_until_new_version(app):
    c = ready_user(app)
    p = c.get("/api/profile").json()["data"]
    assert c.put("/api/profile", json=p).status_code == 409
    assert c.post("/api/profile/new-version").json()["version"] == 2
    assert c.put("/api/profile", json={**p, "name": "Ada L."}).status_code == 200
    assert c.get("/api/profile").json()["confirmed"] is False


def test_policy_changes_quota(app):
    c = ready_user(app)
    assert c.put("/api/policies", json={"company": "Acme", "max_applications": 5, "window_days": 180}).status_code == 200
    c.post("/api/run")
    assert c.get("/api/applications").json()[0]["quota_max"] == 5
    assert c.put("/api/policies", json={"company": "Acme", "max_applications": -1}).status_code == 422


def test_approve_blocked_when_quota_reached(app):
    c = ready_user(app)
    c.post("/api/run")
    aid = c.get("/api/applications").json()[0]["id"]
    c.put("/api/policies", json={"company": "Acme", "max_applications": 0, "window_days": 180})
    assert c.post(f"/api/applications/{aid}/approve").status_code == 409


def test_delete_account(app):
    c = ready_user(app)
    assert c.post("/api/delete-account", json={"confirm": "nope"}).status_code == 400
    assert c.post("/api/delete-account", json={"confirm": "DELETE"}).status_code == 200
    assert c.get("/api/me").status_code == 401


def test_cors_only_for_allowed_origin(app):
    c = TestClient(app)
    ok = c.options("/api/me", headers={"Origin": "https://rupesh.github.io", "Access-Control-Request-Method": "GET",
                                       "Access-Control-Request-Headers": "authorization"})
    assert ok.headers.get("access-control-allow-origin") == "https://rupesh.github.io"
    bad = c.options("/api/me", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers
