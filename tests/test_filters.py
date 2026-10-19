import pytest
from jobagent.sources.models import Job
from jobagent.filters import (apply_filters, location_ok, salary_status, parse_salary_text, SalaryStatus,
                              role_ok, Deduper, canonical_url)


def J(title="Senior Backend Engineer", location="Dublin", locations=None, remote=None, desc="", lo=None, hi=None,
      cur=None, url="https://x.com/jobs/1", company="Acme"):
    return Job(source="t", external_id=url, company=company, title=title, location=location,
               locations=locations or [location], remote=remote, url=url, description=desc,
               salary_min=lo, salary_max=hi, salary_currency=cur)


@pytest.mark.parametrize("loc,locs,remote,expected", [
    ("Dublin", None, None, True),
    ("Dublin, Ireland", None, None, True),
    ("Ireland", None, None, True),
    ("Cork", None, None, True),
    ("London", None, None, False),
    ("Remote - European Union", None, True, True),
    ("Remote - EMEA", None, True, True),
    ("Remote - US", None, True, False),
    ("Remote (US only)", None, True, False),
    ("Remote", None, True, True),
    ("Berlin", ["Berlin", "Ireland"], None, True),
    ("San Francisco", None, None, False),
    ("Remote - Canada", None, True, False),
    ("Remote - Germany", None, True, False),
])
def test_location(loc, locs, remote, expected):
    assert location_ok(J(location=loc, locations=locs, remote=remote))[0] is expected


@pytest.mark.parametrize("text,expected", [
    ("Salary: €80,000 - €100,000", (80000, 100000, "EUR")),
    ("€110K – €185K", (110000, 185000, "EUR")),
    ("€90k", (90000, 90000, "EUR")),
    ("80k-100k EUR", (80000, 100000, "EUR")),
    ("£70,000 to £90,000", (70000, 90000, "GBP")),
    ("$150,000 - $200,000", (150000, 200000, "USD")),
    ("€45 per hour", (None, None, None)),
    ("2 - 3 years experience", (None, None, None)),
    ("competitive salary", (None, None, None)),
    ("€100.000 - €120.000", (100000, 120000, "EUR")),
])
def test_parse_salary_text(text, expected):
    assert parse_salary_text(text) == expected


@pytest.mark.parametrize("kwargs,status", [
    (dict(lo=90000, hi=120000, cur="EUR"), SalaryStatus.PASS),
    (dict(lo=60000, hi=75000, cur="EUR"), SalaryStatus.FAIL),
    (dict(lo=70000, hi=85000, cur="EUR"), SalaryStatus.PASS),   # max meets threshold
    (dict(lo=90000, hi=100000, cur="USD"), SalaryStatus.PASS),  # ~92k EUR
    (dict(lo=80000, hi=85000, cur="USD"), SalaryStatus.FAIL),   # ~78k EUR
    (dict(), SalaryStatus.UNKNOWN),
    (dict(lo=100000, hi=100000, cur="JPY"), SalaryStatus.UNKNOWN),
    (dict(desc="The salary range is €95,000 - €120,000 plus equity"), SalaryStatus.PASS),
    (dict(desc="We offer 25 days leave and 3 - 5 years experience"), SalaryStatus.UNKNOWN),
])
def test_salary_status(kwargs, status):
    assert salary_status(J(**kwargs))[0] is status


@pytest.mark.parametrize("title,expected", [
    ("Senior Backend Engineer", True),
    ("Software Engineer, Payments", True),
    ("Platform Engineer", True),
    ("Staff Distributed Systems Engineer", True),
    ("AI Engineer", True),
    ("Machine Learning Engineer", True),
    ("Site Reliability Engineer", True),
    ("Software Engineering Intern", False),
    ("Software Engineer, New Grad", False),
    ("Early Career Software Engineer", False),
    ("Account Executive", False),
    ("Abuse Investigator", False),
    ("Marketing Manager", False),
    ("Product Designer", False),
    ("Customer Support Engineer", False),
])
def test_role(title, expected):
    assert role_ok(J(title=title))[0] is expected


def test_canonical_url_strips_query_and_trailing_slash():
    assert canonical_url("https://X.com/jobs/1/?gh_jid=1#a") == "https://x.com/jobs/1"


def test_deduper_by_url_and_hash():
    d = Deduper()
    a = J(url="https://x.com/jobs/1")
    b = J(url="https://x.com/jobs/1/?utm=1")             # same url
    c = J(url="https://agency.com/9", title="Senior  Backend Engineer!")  # same hash
    e = J(url="https://x.com/jobs/2", title="Platform Engineer")
    assert d.filter_new([a, b, c, e]) == [a, e]


def test_deduper_remembers_previous_applications():
    d = Deduper(seen_urls={"https://x.com/jobs/1"})
    assert d.is_duplicate(J(url="https://x.com/jobs/1"))


def test_pipeline_buckets():
    jobs = [
        J(url="u1", lo=90000, hi=120000, cur="EUR"),                       # pass
        J(url="u2", title="Platform Engineer"),                            # unknown salary
        J(url="u3", title="AI Engineer", lo=50000, hi=60000, cur="EUR"),   # salary fail
        J(url="u4", title="Sales Manager"),                                # role fail
        J(url="u5", title="Backend Engineer", location="Paris"),           # location fail
        J(url="u1", lo=90000, hi=120000, cur="EUR"),                       # duplicate
    ]
    res = apply_filters(jobs)
    assert [j.url for j in res.passed] == ["u1"]
    assert [j.url for j in res.unknown_salary] == ["u2"]
    reasons = {j.url: r for j, r in res.rejected}
    assert reasons["u3"].startswith("salary") and reasons["u4"].startswith("role")
    assert reasons["u5"].startswith("location") and "duplicate" in reasons.values()


def test_pipeline_on_real_fixtures():
    import json
    from pathlib import Path
    from jobagent.sources import ashby
    payload = json.loads((Path(__file__).parent / "fixtures/ashby_ashby.json").read_text())
    res = apply_filters(ashby.parse(payload, "ashby"))
    assert len(res.passed) + len(res.unknown_salary) + len(res.rejected) == len(ashby.parse(payload, "ashby"))
