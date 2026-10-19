import json
import pytest
from datetime import datetime, timedelta
from jobagent.budget.guard import BudgetGuard
from jobagent.db import make_engine, init_db, Repo
from jobagent.llm import FakeProvider, LLMClient
from jobagent.pipeline import run_daily, render_digest
from jobagent.profile import Profile, Experience, ProfileService
from jobagent.safety.service import quota_for
from jobagent.sources.models import Job
from jobagent.submit.runner import submit, SubmitRefused

PROFILE = Profile(name="Ada Lovelace", location="Dublin", years_experience=6, skills=["Python", "PostgreSQL"],
                  experience=[Experience(company="Analytical Engines Ltd", title="Backend Engineer", start="2020", end="present",
                                         achievements=["Cut p95 latency by 40%"], technologies=["Python"])])
GOOD_DOCS = json.dumps({"cv_markdown": "# Ada Lovelace\nBackend Engineer at Analytical Engines Ltd. Cut p95 latency by 40%. Python.",
                        "cover_letter": "Dear hiring team, I am applying for the role. At Analytical Engines Ltd I used Python."})


def mkjob(i, company="Acme", title="Senior Backend Engineer", loc="Dublin", lo=None, hi=None, cur=None):
    return Job(source="greenhouse", external_id=str(i), company=company, title=title, location=loc, locations=[loc],
               url=f"https://jobs.example.com/{company}/{i}", description="Python services.",
               salary_min=lo, salary_max=hi, salary_currency=cur)


def responder(score=85, docs=GOOD_DOCS):
    def f(system, prompt):
        if "score how well" in system.lower() or "You score" in system:
            return json.dumps({"score": score, "reasons": ["Python"], "red_flags": []})
        return docs
    return f


@pytest.fixture
def env():
    e = make_engine("sqlite://"); init_db(e); r = Repo(e)
    uid = r.create_user("ada@example.com")
    vd = r.add_profile_draft(uid, PROFILE.model_dump()); r.confirm_profile(uid, vd)
    return r, uid


def client(env, fn=None, cap=15.0):
    repo, uid = env
    f = FakeProvider(fn or responder())
    return LLMClient(uid, f, BudgetGuard(cap), usage_sink=repo.record_usage), f


def run(env, jobs, llm=None):
    repo, uid = env
    llm = llm or client(env)[0]
    return run_daily(repo, uid, jobs, llm, match_model="fake", tailor_model="fake")


def test_end_to_end_digest_zero_cost(env):
    jobs = [mkjob(1, lo=90000, hi=120000, cur="EUR"), mkjob(2, company="Beta"),            # known + unknown salary
            mkjob(3, title="Sales Manager"), mkjob(4, loc="Paris")]                          # filtered out
    rep = run(env, jobs)
    assert rep.fetched == 4 and rep.filtered_out == 2 and len(rep.queue) == 2
    md = render_digest(rep)
    assert "Published salary meets your minimum" in md and "Salary not published" in md
    assert "of 3 applications left" in md and "Tailored CV" in md and "dry-run" in md
    assert rep.spent_eur == 0.0                                                              # fake model = free
    repo, uid = env
    apps = repo.list_applications(uid)
    assert len(apps) == 2 and {a["status"] for a in apps} == {"drafted"}


def test_nothing_is_ever_submitted(env):
    run(env, [mkjob(1, lo=90000, hi=120000, cur="EUR")])
    repo, uid = env
    assert repo.list_applications(uid, status="submitted") == []
    with pytest.raises(SubmitRefused):
        submit(object())                                                                     # dry-run default


def test_unconfirmed_profile_blocks_pipeline():
    e = make_engine("sqlite://"); init_db(e); r = Repo(e)
    uid = r.create_user("x@y.com"); r.add_profile_draft(uid, PROFILE.model_dump())
    with pytest.raises(PermissionError):
        run((r, uid), [mkjob(1)], llm=LLMClient(uid, FakeProvider("{}"), BudgetGuard(15)))


def test_rerun_does_not_duplicate_or_respend(env):
    repo, uid = env
    llm, f = client(env)
    run(env, [mkjob(1, lo=90000, hi=120000, cur="EUR")], llm)
    calls_after_first = len(f.calls)
    rep2 = run(env, [mkjob(1, lo=90000, hi=120000, cur="EUR")], llm)
    assert len(rep2.queue) == 0 and len(f.calls) == calls_after_first                        # already applied/drafted
    assert len(repo.list_applications(uid)) == 1


def test_low_scores_not_tailored(env):
    llm, f = client(env, responder(score=40))
    rep = run(env, [mkjob(1, lo=90000, hi=120000, cur="EUR")], llm)
    assert rep.queue == [] and len(rep.below_threshold) == 1 and len(f.calls) == 1           # only the scoring call


def test_quota_blocks_company_at_limit(env):
    repo, uid = env
    cid = repo.get_or_create_company("Acme")
    repo.set_company_policy(cid, max_applications=5, window_days=180)
    for i in range(5):                                                                       # 5 submitted applications recently
        jid = repo.upsert_job(mkjob(100 + i, title=f"Platform Engineer {i}"), cid)
        aid = repo.create_application(uid, jid, cid, "drafted")
        repo.set_application_status(uid, aid, "submitted")
    assert quota_for(repo, uid, cid).allowed is False
    rep = run(env, [mkjob(1, lo=90000, hi=120000, cur="EUR")])
    assert rep.queue == [] and len(rep.quota_blocked) == 1 and "quota reached" in rep.quota_blocked[0][1]


def test_scarce_quota_raises_the_bar(env):
    repo, uid = env
    cid = repo.get_or_create_company("Acme")
    repo.set_company_policy(cid, max_applications=5, window_days=180)
    for i in range(3):                                                                       # 2 left -> needs 85
        jid = repo.upsert_job(mkjob(200 + i, title=f"Platform Engineer {i}"), cid)
        aid = repo.create_application(uid, jid, cid, "drafted"); repo.set_application_status(uid, aid, "submitted")
    rep = run(env, [mkjob(1, lo=90000, hi=120000, cur="EUR")], client(env, responder(score=80))[0])
    assert rep.queue == [] and rep.below_threshold[0][1] == 80                               # 80 >= 75 but < 85
    rep2 = run(env, [mkjob(2, title="Staff Backend Engineer", lo=90000, hi=120000, cur="EUR")], client(env, responder(score=90))[0])
    assert len(rep2.queue) == 1 and rep2.queue[0].quota_remaining == 2
    assert "2 of 5 applications left" in render_digest(rep2)


def test_approved_pending_counts_toward_quota(env):
    repo, uid = env
    cid = repo.get_or_create_company("Acme")
    repo.set_company_policy(cid, max_applications=2, window_days=180)
    for i in range(2):
        jid = repo.upsert_job(mkjob(300 + i, title=f"Platform Engineer {i}"), cid)
        aid = repo.create_application(uid, jid, cid, "drafted"); repo.set_application_status(uid, aid, "approved")
    assert quota_for(repo, uid, cid).allowed is False


def test_invented_claims_never_reach_the_queue(env):
    bad = json.dumps({"cv_markdown": "Ex-Google engineer with a PhD from MIT.", "cover_letter": "Hello."})
    rep = run(env, [mkjob(1, lo=90000, hi=120000, cur="EUR")], client(env, responder(docs=bad))[0])
    assert rep.queue == [] and len(rep.tailoring_rejected) == 1
    md = render_digest(rep)
    assert "Google" not in md.split("fact-check")[0] and "failed the fact-check" in md
    repo, uid = env
    assert repo.list_applications(uid) == []


def test_budget_exhaustion_stops_cleanly(env):
    repo, uid = env
    f = FakeProvider(responder())
    llm = LLMClient(uid, f, BudgetGuard(0.0), usage_sink=repo.record_usage, prices={"fake": (1e6, 1e6)})
    rep = run(env, [mkjob(1, lo=90000, hi=120000, cur="EUR")], llm)
    assert rep.budget_stopped and rep.queue == [] and f.calls == []
    assert "budget" in render_digest(rep).lower()


def test_two_users_are_isolated(env):
    repo, uid = env
    run(env, [mkjob(1, lo=90000, hi=120000, cur="EUR")])
    bob = repo.create_user("bob@example.com")
    vb = repo.add_profile_draft(bob, PROFILE.model_dump()); repo.confirm_profile(bob, vb)
    assert repo.list_applications(bob) == []                                                 # Ada's drafts invisible to Bob
    rep = run_daily(repo, bob, [mkjob(1, lo=90000, hi=120000, cur="EUR")], client((repo, bob))[0],
                    match_model="fake", tailor_model="fake")
    assert len(rep.queue) == 1                                                               # Bob still gets the job
    with pytest.raises(ValueError):
        repo.set_application_status(bob, repo.list_applications(uid)[0]["id"], "approved")   # cannot touch Ada's
