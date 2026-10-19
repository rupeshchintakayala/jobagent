import json
from datetime import datetime, timedelta
import pytest
from typer.testing import CliRunner
import jobagent.cli as cli
from jobagent.config import Settings
from jobagent.db import Repo, init_db, make_engine
from jobagent.db.engine import normalize_url
from jobagent.llm import FakeProvider, KeyVault
from jobagent.profile import Profile
from jobagent.scheduler import run_all
from jobagent.sources.models import Job

PROFILE = {"name": "Ada", "location": "Dublin", "years_experience": 6, "skills": ["Python"],
           "experience": [{"company": "Analytical Engines Ltd", "title": "Backend Engineer", "start": "2020", "end": "present",
                           "achievements": ["Cut p95 latency by 40%"], "technologies": ["Python"]}]}
DOCS = json.dumps({"cv_markdown": "Ada. Backend Engineer at Analytical Engines Ltd. Cut p95 latency by 40%. Python.",
                   "cover_letter": "Dear team, I use Python at Analytical Engines Ltd."})
JOB = Job(source="greenhouse", external_id="1", company="Acme", title="Senior Backend Engineer", location="Dublin",
          locations=["Dublin"], url="https://jobs.example.com/1", description="Python.", salary_min=90000,
          salary_max=120000, salary_currency="EUR")


def fake(system, prompt):
    if "score how well" in system.lower():
        return json.dumps({"score": 88, "reasons": ["Python"], "red_flags": []})
    return DOCS


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBAGENT_MASTER_KEY", KeyVault.generate_master_key())
    e = make_engine(f"sqlite:///{tmp_path/'s.db'}"); init_db(e)
    return Repo(e)


def make_user(repo, email, confirmed=True, key=True):
    uid = repo.create_user(email)
    if key:
        repo.save_key(uid, "claude", KeyVault().encrypt("sk-ant-x1234"), 15.0)
    v = repo.add_profile_draft(uid, Profile.model_validate(PROFILE).model_dump())
    if confirmed:
        repo.confirm_profile(uid, v)
    return uid


def test_runs_only_eligible_users_and_isolates_failures(repo):
    ok = make_user(repo, "ok@x.ie")
    make_user(repo, "nokey@x.ie", key=False)
    make_user(repo, "unconfirmed@x.ie", confirmed=False)
    bad = make_user(repo, "bad@x.ie")
    calls = []

    def factory(key):
        calls.append(key)
        if len(calls) == 1:
            raise RuntimeError("boom")        # first eligible user blows up
        return FakeProvider(fake)
    r = run_all(repo, Settings(), fetch=lambda s: [JOB], provider_factory=factory)
    assert len(r.ran) == 1 and len(r.failed) == 1
    assert {r.ran[0], r.failed[0][0]} == {"ok@x.ie", "bad@x.ie"}
    assert r.queued == 1


def test_users_get_only_their_own_drafts(repo):
    a = make_user(repo, "a@x.ie"); b = make_user(repo, "b@x.ie")
    r = run_all(repo, Settings(), fetch=lambda s: [JOB], provider_factory=lambda k: FakeProvider(fake))
    assert len(r.ran) == 2 and r.queued == 2
    assert len(repo.list_applications(a)) == 1 and len(repo.list_applications(b)) == 1
    assert repo.list_applications(a)[0]["id"] != repo.list_applications(b)[0]["id"]


def test_does_not_rerun_within_window(repo):
    make_user(repo, "a@x.ie")
    fetched = []
    f = lambda s: fetched.append(1) or [JOB]
    run_all(repo, Settings(), fetch=f, provider_factory=lambda k: FakeProvider(fake))
    r2 = run_all(repo, Settings(), fetch=f, provider_factory=lambda k: FakeProvider(fake))
    assert r2.ran == [] and r2.skipped and len(fetched) == 1          # no fetch when nobody is due
    later = datetime.utcnow() + timedelta(hours=25)
    r3 = run_all(repo, Settings(), fetch=f, provider_factory=lambda k: FakeProvider(fake), now=later)
    assert r3.ran == ["a@x.ie"]


def test_budget_cap_respected_per_user(repo):
    uid = make_user(repo, "cheap@x.ie")
    repo.save_key(uid, "claude", KeyVault().encrypt("sk-ant-x1234"), 0.000001)
    r = run_all(repo, Settings(), fetch=lambda s: [JOB], provider_factory=lambda k: FakeProvider(fake))
    assert r.queued == 0 and repo.list_applications(uid) == []


def test_url_normalisation():
    assert normalize_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_url("postgresql+psycopg://u:p@h/db").startswith("postgresql+psycopg://")
    assert normalize_url("sqlite:///x.db") == "sqlite:///x.db"


def test_policy_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBAGENT_DB", f"sqlite:///{tmp_path/'p.db'}")
    r = CliRunner()
    assert r.invoke(cli.app, ["set-policy", "Stripe", "--max-applications", "5", "--note", "careers page"]).exit_code == 0
    out = r.invoke(cli.app, ["list-policies"]).output
    assert "Stripe: 5 per 180d" in out


def test_run_all_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBAGENT_DB", f"sqlite:///{tmp_path/'c.db'}")
    monkeypatch.setenv("JOBAGENT_MASTER_KEY", KeyVault.generate_master_key())
    res = CliRunner().invoke(cli.app, ["run-all"])
    assert res.exit_code == 0 and "ran 0" in res.output
