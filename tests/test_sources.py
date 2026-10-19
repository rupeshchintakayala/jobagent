import json
from pathlib import Path
import httpx
import respx
from jobagent.sources import greenhouse, lever, ashby, Job
from jobagent.sources.text import html_to_text

FX = Path(__file__).parent / "fixtures"
load = lambda n: json.loads((FX / n).read_text())


def test_html_to_text_handles_double_escaped():
    s = "&lt;p&gt;Hello &amp;amp; welcome&lt;/p&gt;&lt;ul&gt;&lt;li&gt;One&lt;/li&gt;&lt;/ul&gt;"
    out = html_to_text(s)
    assert "<" not in out and "Hello & welcome" in out and "One" in out


def test_greenhouse_parse():
    jobs = greenhouse.parse(load("greenhouse_stripe.json"), "stripe")
    assert jobs and all(isinstance(j, Job) for j in jobs)
    j = jobs[0]
    assert j.source == "greenhouse" and j.company == "Stripe"
    assert "Dublin" in j.location and j.url.startswith("http")
    assert "<" not in j.description and len(j.description) > 100
    assert j.posted_at is not None


def test_lever_parse():
    jobs = lever.parse(load("lever_spotify.json"), "spotify")
    assert len(jobs) == 3
    j = jobs[0]
    assert j.source == "lever" and j.company == "spotify" and j.url.startswith("https://jobs.lever.co")
    assert j.posted_at is not None and j.title


def test_ashby_parse_salary_and_remote():
    jobs = ashby.parse(load("ashby_ashby.json"), "ashby")
    with_pay = [j for j in jobs if j.salary_min]
    assert with_pay, "fixture should contain a job with compensation"
    j = with_pay[0]
    assert j.salary_currency == "EUR" and j.salary_min <= j.salary_max
    assert j.remote is True
    assert "Ireland" in j.locations or j.locations


def test_dedupe_hash_is_stable_and_normalised():
    a = Job(source="x", external_id="1", company="Stripe", title="Backend Engineer", location="Dublin", url="u")
    b = Job(source="y", external_id="2", company=" stripe ", title="Backend  Engineer!", location="DUBLIN", url="v")
    c = Job(source="x", external_id="3", company="Stripe", title="Backend Engineer", location="London", url="w")
    assert a.dedupe_hash == b.dedupe_hash != c.dedupe_hash


@respx.mock
def test_fetch_greenhouse_uses_public_api():
    route = respx.get("https://boards-api.greenhouse.io/v1/boards/stripe/jobs").mock(
        return_value=httpx.Response(200, json=load("greenhouse_stripe.json")))
    jobs = greenhouse.fetch("stripe")
    assert route.called and jobs


@respx.mock
def test_fetch_lever_and_ashby():
    respx.get("https://api.lever.co/v0/postings/spotify").mock(return_value=httpx.Response(200, json=load("lever_spotify.json")))
    respx.get("https://api.ashbyhq.com/posting-api/job-board/ashby").mock(return_value=httpx.Response(200, json=load("ashby_ashby.json")))
    assert lever.fetch("spotify") and ashby.fetch("ashby")
