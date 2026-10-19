import json
import re
import pytest
from fastapi.testclient import TestClient
from jobagent.config import Settings
from jobagent.llm import FakeProvider, InvalidKey, KeyVault
from jobagent.sources.models import Job
from jobagent.web import create_app

PROFILE = {"name": "Ada Lovelace", "location": "Dublin", "years_experience": 6, "skills": ["Python"],
           "experience": [{"company": "Analytical Engines Ltd", "title": "Backend Engineer", "start": "2020", "end": "present",
                           "achievements": ["Cut p95 latency by 40%"], "technologies": ["Python"]}],
           "education": [{"institution": "Trinity College Dublin", "degree": "BSc", "field": "CS", "year": "2015"}]}
DOCS = json.dumps({"cv_markdown": "Ada Lovelace. Backend Engineer at Analytical Engines Ltd. Cut p95 latency by 40%. Python.",
                   "cover_letter": "Dear hiring team, I use Python at Analytical Engines Ltd."})
JOB = Job(source="greenhouse", external_id="1", company="Acme", title="Senior Backend Engineer", location="Dublin",
          locations=["Dublin"], url="https://jobs.example.com/1", description="Python.", salary_min=90000, salary_max=120000,
          salary_currency="EUR")


def fake(system, prompt):
    s = system.lower()
    if "extract structured data" in s:
        return json.dumps(PROFILE)
    if "score how well" in s:
        return json.dumps({"score": 88, "reasons": ["Python"], "red_flags": []})
    return DOCS


class BadKeyProvider(FakeProvider):
    def verify_key(self):
        raise InvalidKey("bad")


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBAGENT_MASTER_KEY", KeyVault.generate_master_key())
    return create_app(Settings(db_url=f"sqlite:///{tmp_path/'w.db'}"), provider_factory=lambda k: FakeProvider(fake),
                      fetch_jobs=lambda s: [JOB], secret="x" * 40, run_in_background=False)


def csrf_of(client):
    html = client.get("/settings").text
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def signup(app, email="ada@example.com"):
    c = TestClient(app, follow_redirects=False)
    r = c.post("/signup", data={"email": email, "password": "correct horse battery"})
    assert r.status_code == 303, r.text
    return c


def setup_full(c):
    tok = csrf_of(c)
    assert c.post("/settings/key", data={"api_key": "sk-ant-api03-SECRETKEY1234", "cap_eur": "15", "csrf": tok}).status_code == 303
    r = c.post("/profile/upload", data={"csrf": tok}, files={"cv": ("cv.txt", b"Ada Lovelace. Python backend engineer.")})
    assert r.status_code == 303 and "err=" not in r.headers["location"]
    r = c.post("/profile/save", data={"csrf": tok, "action": "confirm", "name": "Ada Lovelace", "skills": "Python",
                                      "exp0_company": "Analytical Engines Ltd", "exp0_title": "Backend Engineer",
                                      "exp0_achievements": "Cut p95 latency by 40%", "exp0_technologies": "Python"})
    assert r.status_code == 303 and "msg=" in r.headers["location"]
    return tok


def test_requires_login(app):
    c = TestClient(app, follow_redirects=False)
    for path in ("/dashboard", "/queue", "/profile", "/settings", "/privacy"):
        r = c.get(path)
        assert r.status_code == 303 and r.headers["location"] == "/login"


def test_signup_validation_and_login(app):
    c = TestClient(app, follow_redirects=False)
    assert c.post("/signup", data={"email": "nope", "password": "correct horse battery"}).status_code == 400
    assert c.post("/signup", data={"email": "a@b.ie", "password": "short"}).status_code == 400
    signup(app)
    assert c.post("/signup", data={"email": "ada@example.com", "password": "correct horse battery"}).status_code == 400  # duplicate
    assert c.post("/login", data={"email": "ada@example.com", "password": "wrong password!!"}).status_code == 400
    r = c.post("/login", data={"email": "ada@example.com", "password": "correct horse battery"})
    assert r.status_code == 303 and "ja_session" in r.headers["set-cookie"] and "HttpOnly" in r.headers["set-cookie"]


def test_login_rate_limited(app):
    c = TestClient(app, follow_redirects=False)
    codes = [c.post("/login", data={"email": "x@y.ie", "password": "wrong password!!"}).status_code for _ in range(12)]
    assert 429 in codes


def test_forged_cookie_rejected(app):
    c = TestClient(app, follow_redirects=False, cookies={"ja_session": "someone|abc|9999999999|deadbeef"})
    assert c.get("/dashboard").status_code == 303


def test_full_flow_to_applied(app):
    c = signup(app)
    tok = setup_full(c)
    assert "Find jobs now" in c.get("/dashboard").text
    r = c.post("/run", data={"csrf": tok})
    assert r.status_code == 303
    dash = c.get("/dashboard").text
    assert "Last run finished" in dash and "queued 1 drafts" in dash
    q = c.get("/queue").text
    assert "Senior Backend Engineer" in q and "applications left at Acme" in q
    aid = re.search(r"/application/([0-9a-f-]{36})", q).group(1)
    page = c.get(f"/application/{aid}").text
    assert "Cut p95 latency by 40%" in page and "Approve" in page
    # can't mark applied before approving
    r = c.post(f"/application/{aid}/applied", data={"csrf": tok})
    assert "err=" in r.headers["location"]
    assert c.post(f"/application/{aid}/approve", data={"csrf": tok}).status_code == 303
    assert "I applied" in c.get(f"/application/{aid}").text
    assert "2 of 3 applications left" in c.get(f"/application/{aid}").text      # approved-pending counts
    c.post(f"/application/{aid}/applied", data={"csrf": tok})
    assert "Senior Backend Engineer" in c.get("/queue?status=submitted").text


def test_run_blocked_without_confirmed_profile(app):
    c = signup(app)
    tok = csrf_of(c)
    r = c.post("/run", data={"csrf": tok})
    assert "err=" in r.headers["location"] and r.headers["location"].startswith("/settings")


def test_bad_key_is_rejected_and_not_stored(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBAGENT_MASTER_KEY", KeyVault.generate_master_key())
    a = create_app(Settings(db_url=f"sqlite:///{tmp_path/'b.db'}"), provider_factory=lambda k: BadKeyProvider(fake),
                   fetch_jobs=lambda s: [], secret="x" * 40, run_in_background=False)
    c = signup(a)
    r = c.post("/settings/key", data={"api_key": "sk-bad", "cap_eur": "15", "csrf": csrf_of(c)})
    assert "err=" in r.headers["location"]
    assert "Saved" not in c.get("/settings").text


def test_csrf_required_on_every_post(app):
    c = signup(app)
    setup_full(c)
    for path, data in [("/run", {}), ("/settings/key", {"api_key": "sk-x", "cap_eur": "15"}), ("/settings/prefs", {}),
                       ("/profile/new-version", {}), ("/privacy/delete", {"confirm": "DELETE"})]:
        r = c.post(path, data=data)
        assert r.status_code == 303 and "err=" in r.headers["location"], path
    # nothing deleted
    assert c.get("/dashboard").status_code == 200


def test_users_cannot_see_each_others_applications(app):
    a = signup(app, "a@example.com"); ta = setup_full(a)
    a.post("/run", data={"csrf": ta})
    aid = re.search(r"/application/([0-9a-f-]{36})", a.get("/queue").text).group(1)
    b = signup(app, "b@example.com"); tb = csrf_of(b)
    assert b.get(f"/application/{aid}").status_code == 404
    r = b.post(f"/application/{aid}/approve", data={"csrf": tb})
    assert "err=" in r.headers["location"]
    assert "Senior Backend Engineer" not in b.get("/queue").text
    assert a.get(f"/application/{aid}").status_code == 200       # still drafted, untouched
    assert "Approve" in a.get(f"/application/{aid}").text


def test_api_key_never_rendered(app):
    c = signup(app); setup_full(c)
    for path in ("/settings", "/dashboard", "/profile"):
        assert "SECRETKEY1234"[:6] not in c.get(path).text
    assert "****1234" in c.get("/settings").text


def test_confirmed_profile_is_read_only_until_new_version(app):
    c = signup(app); tok = setup_full(c)
    r = c.post("/profile/save", data={"csrf": tok, "name": "Mallory", "action": "save"})
    assert "err=" in r.headers["location"]
    c.post("/profile/new-version", data={"csrf": tok})
    assert "draft: needs your check" in c.get("/profile").text
    assert c.post("/run", data={"csrf": tok}).status_code == 303          # old confirmed profile still usable


def test_delete_account(app):
    c = signup(app); tok = setup_full(c)
    r = c.post("/privacy/delete", data={"csrf": tok, "confirm": "nope"})
    assert "err=" in r.headers["location"]
    r = c.post("/privacy/delete", data={"csrf": tok, "confirm": "DELETE"})
    assert r.status_code == 303
    assert c.get("/dashboard").status_code == 303
    assert c.post("/login", data={"email": "ada@example.com", "password": "correct horse battery"}).status_code == 400


def test_prefs_validation(app):
    c = signup(app); tok = csrf_of(c)
    assert "err=" in c.post("/settings/prefs", data={"csrf": tok, "min_salary_eur": "-5", "min_score": "70"}).headers["location"]
    assert "msg=" in c.post("/settings/prefs", data={"csrf": tok, "min_salary_eur": "90000", "min_score": "70"}).headers["location"]


def test_missing_session_secret_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBAGENT_SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        create_app(Settings(db_url=f"sqlite:///{tmp_path/'x.db'}"))


def test_policy_page_sets_limit_used_by_quota(app):
    c = signup(app); tok = setup_full(c)
    assert "err=" in c.post("/policies", data={"csrf": tok, "company": "Acme", "max_applications": "abc"}).headers["location"]
    assert "err=" in c.post("/policies", data={"csrf": "bad", "company": "Acme", "max_applications": "5"}).headers["location"]
    assert "msg=" in c.post("/policies", data={"csrf": tok, "company": "Acme", "max_applications": "5", "note": "careers"}).headers["location"]
    c.post("/run", data={"csrf": tok})
    q = c.get("/queue").text
    assert "5 of 5 applications left at Acme" in q
    assert "5 per 180d" in c.get("/policies").text


def test_policies_require_login(app):
    c = TestClient(app, follow_redirects=False)
    assert c.get("/policies").status_code == 303


def test_invite_code_gates_signup(app, monkeypatch):
    monkeypatch.setenv("JOBAGENT_INVITE_CODE", "friends-2026")
    c = TestClient(app, follow_redirects=False)
    assert "Invite code" in c.get("/signup").text
    assert c.post("/signup", data={"email": "a@b.ie", "password": "correct horse battery", "invite": "wrong"}).status_code == 400
    assert c.post("/signup", data={"email": "a@b.ie", "password": "correct horse battery"}).status_code == 400
    assert c.post("/signup", data={"email": "a@b.ie", "password": "correct horse battery", "invite": "friends-2026"}).status_code == 303
