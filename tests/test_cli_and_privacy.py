import json
import logging
import pytest
from typer.testing import CliRunner
import jobagent.cli as cli
from jobagent.db import make_engine, init_db, Repo, tables as t
from jobagent.llm import FakeProvider, KeyVault, ClaudeProvider, LLMClient
from jobagent.budget.guard import BudgetGuard
import sqlalchemy as sa

runner = CliRunner()
PROFILE = {"name": "Ada Lovelace", "location": "Dublin", "years_experience": 6, "skills": ["Python"],
           "experience": [{"company": "Analytical Engines Ltd", "title": "Backend Engineer", "start": "2020", "end": "present",
                           "achievements": ["Cut p95 latency by 40%"], "technologies": ["Python"]}]}
DOCS = json.dumps({"cv_markdown": "Ada Lovelace. Backend Engineer at Analytical Engines Ltd. Cut p95 latency by 40%. Python.",
                   "cover_letter": "Dear hiring team, I use Python at Analytical Engines Ltd."})
JOBS = [{"source": "greenhouse", "external_id": "1", "company": "Acme", "title": "Senior Backend Engineer",
         "location": "Dublin", "locations": ["Dublin"], "url": "https://jobs.example.com/1", "description": "Python.",
         "salary_min": 90000, "salary_max": 120000, "salary_currency": "EUR"}]


def fake(system, prompt):
    if "parse" in system.lower() or "extract structured data" in system.lower():
        return json.dumps(PROFILE)
    if "score how well" in system.lower():
        return json.dumps({"score": 88, "reasons": ["Python"], "red_flags": []})
    return DOCS


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = f"sqlite:///{tmp_path/'t.db'}"
    monkeypatch.setenv("JOBAGENT_DB", db)
    monkeypatch.setenv("JOBAGENT_MASTER_KEY", KeyVault.generate_master_key())
    monkeypatch.setattr(cli, "ClaudeProvider", lambda key: FakeProvider(fake))     # no network, no cost
    return tmp_path, db


def invoke(*args, **kw):
    r = runner.invoke(cli.app, list(args), catch_exceptions=False, **kw)
    return r


def test_full_cli_flow_end_to_end(env):
    tmp, db = env
    cv = tmp / "cv.txt"; cv.write_text("Ada Lovelace, Backend Engineer at Analytical Engines Ltd. Python.")
    jobs = tmp / "jobs.json"; jobs.write_text(json.dumps(JOBS))
    assert invoke("signup", "ada@example.com").exit_code == 0
    r = invoke("set-key", "ada@example.com", "--api-key", "sk-ant-api03-SECRETKEY1234", "--cap-eur", "15", "--skip-verify")
    assert r.exit_code == 0 and "SECRETKEY" not in r.output and "****1234" in r.output
    r = invoke("upload-cv", "ada@example.com", str(cv))
    assert r.exit_code == 0 and "confirm-profile" in r.output
    # unconfirmed profile must block the pipeline
    r = invoke("run-daily", "ada@example.com", "--fixtures", str(jobs), "--out", str(tmp / "d.md"))
    assert r.exit_code == 1 and "confirm" in r.output.lower()
    assert invoke("confirm-profile", "ada@example.com", "1").exit_code == 0
    r = invoke("run-daily", "ada@example.com", "--dry-run", "--fixtures", str(jobs), "--out", str(tmp / "d.md"))
    assert r.exit_code == 0 and "1 drafts queued" in r.output
    md = (tmp / "d.md").read_text()
    assert "Senior Backend Engineer" in md and "score **88**" in md and "of 3 applications left" in md
    assert "Tailored CV" in md and "dry-run" in md
    r = invoke("digest", "ada@example.com")
    assert "Acme" in r.output
    app_id = r.output.split()[0]
    assert invoke("approve", "ada@example.com", app_id).exit_code == 0
    assert invoke("mark-applied", "ada@example.com", app_id).exit_code == 0


def test_set_key_rejects_without_master_key(env, monkeypatch):
    monkeypatch.delenv("JOBAGENT_MASTER_KEY")
    invoke("signup", "a@x.com")
    r = invoke("set-key", "a@x.com", "--api-key", "sk-ant-x", "--skip-verify")
    assert r.exit_code == 1 and "init-master-key" in r.output


def test_unknown_user_gets_helpful_error(env):
    r = invoke("digest", "nobody@x.com")
    assert r.exit_code == 1 and "signup" in r.output


def test_stored_key_is_encrypted_at_rest(env):
    tmp, db = env
    invoke("signup", "a@x.com")
    invoke("set-key", "a@x.com", "--api-key", "sk-ant-api03-PLAINTEXT9999", "--skip-verify")
    repo = Repo(make_engine(db))
    blob = repo.get_key(repo.get_user_by_email("a@x.com"))["key_encrypted"]
    assert b"PLAINTEXT" not in blob
    raw = open(db.replace("sqlite:///", ""), "rb").read()
    assert b"PLAINTEXT9999" not in raw


def test_bad_cv_file_is_reported(env):
    tmp, _ = env
    invoke("signup", "a@x.com"); invoke("set-key", "a@x.com", "--api-key", "k", "--skip-verify")
    r = invoke("upload-cv", "a@x.com", str(tmp / "missing.pdf"))
    assert r.exit_code == 1 and "not found" in r.output


def test_live_submission_flag_is_ignored(env):
    tmp, _ = env
    cv = tmp / "cv.txt"; cv.write_text("cv"); jobs = tmp / "j.json"; jobs.write_text(json.dumps(JOBS))
    invoke("signup", "a@x.com"); invoke("set-key", "a@x.com", "--api-key", "k", "--skip-verify")
    invoke("upload-cv", "a@x.com", str(cv)); invoke("confirm-profile", "a@x.com", "1")
    r = invoke("run-daily", "a@x.com", "--no-dry-run", "--fixtures", str(jobs), "--out", str(tmp / "d.md"))
    assert "not implemented" in r.output and r.exit_code == 0


# ---------- isolation + GDPR ----------
@pytest.fixture
def two_users():
    e = make_engine("sqlite://"); init_db(e); r = Repo(e)
    a, b = r.create_user("a@x.com"), r.create_user("b@x.com")
    for u in (a, b):
        r.save_key(u, "claude", KeyVault(KeyVault.generate_master_key()).encrypt(f"sk-{u}"), 15)
        v = r.add_profile_draft(u, PROFILE); r.confirm_profile(u, v)
        cid = r.get_or_create_company("Acme")
        from jobagent.sources.models import Job
        jid = r.upsert_job(Job.model_validate(JOBS[0]), cid)
        r.create_application(u, jid, cid, "drafted", "cv", "letter")
        r.save_match(u, jid, v, 80, ["x"], [])
        r.cache_set(u, "k", "v"); r.record_usage({"user_id": u, "model": "m", "input_tokens": 1, "output_tokens": 1, "cost_eur": 0.1})
        r.audit(u, "x")
    return r, a, b


def test_every_user_table_has_user_id():
    for table in t.USER_TABLES:
        assert "user_id" in table.c, table.name


def test_users_cannot_read_each_others_data(two_users):
    r, a, b = two_users
    assert r.get_key(a)["user_id"] == a and r.get_key(b)["user_id"] == b
    assert len(r.list_applications(a)) == 1 and r.list_applications(a)[0]["user_id"] == a
    assert r.cache_get(a, "k") == "v" and r.cache_get(a, "other") is None
    assert r.latest_confirmed_profile(a)["user_id"] == a
    assert r.month_spend_eur(a) == pytest.approx(0.1)


def test_cannot_modify_another_users_application(two_users):
    r, a, b = two_users
    with pytest.raises(ValueError):
        r.set_application_status(b, r.list_applications(a)[0]["id"], "approved")
    assert r.list_applications(a)[0]["status"] == "drafted"


def test_delete_my_data_removes_everything_for_that_user_only(two_users):
    r, a, b = two_users
    r.delete_user_data(a)
    with r.engine.connect() as c:
        for table in t.USER_TABLES:
            assert c.execute(sa.select(sa.func.count()).select_from(table).where(table.c.user_id == a)).scalar() == 0, table.name
        assert c.execute(sa.select(sa.func.count()).select_from(t.users).where(t.users.c.id == a)).scalar() == 0
        assert c.execute(sa.select(sa.func.count()).select_from(t.audit_log).where(t.audit_log.c.user_id == a)).scalar() == 0
    assert r.get_user_by_email("a@x.com") is None
    assert r.get_key(b) is not None and len(r.list_applications(b)) == 1 and r.latest_confirmed_profile(b)


def test_delete_my_data_cli(env):
    tmp, db = env
    invoke("signup", "gone@x.com")
    assert invoke("delete-my-data", "gone@x.com", "--yes").exit_code == 0
    assert Repo(make_engine(db)).get_user_by_email("gone@x.com") is None


def test_api_key_never_in_logs_or_audit(env, caplog):
    tmp, db = env
    caplog.set_level(logging.DEBUG)
    invoke("signup", "a@x.com"); invoke("set-key", "a@x.com", "--api-key", "sk-ant-api03-NEVERLOG777", "--skip-verify")
    assert "NEVERLOG777" not in caplog.text
    repo = Repo(make_engine(db))
    with repo.engine.connect() as c:
        assert "NEVERLOG777" not in str(c.execute(sa.select(t.audit_log)).all())
