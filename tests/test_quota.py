from datetime import datetime, timedelta
from jobagent.safety.quota import CompanyPolicy, check_quota
NOW = datetime(2026, 10, 19)
def test_blocks_at_limit():
    pol = CompanyPolicy(max_applications=5, window_days=180)
    past = [NOW - timedelta(days=d) for d in (10, 20, 30, 40, 50)]
    assert not check_quota(pol, past, NOW).allowed
def test_old_applications_expire():
    pol = CompanyPolicy(max_applications=5, window_days=180)
    past = [NOW - timedelta(days=200)] * 5
    assert check_quota(pol, past, NOW).allowed
def test_pending_approved_count():
    pol = CompanyPolicy(max_applications=5, window_days=180)
    assert not check_quota(pol, [NOW - timedelta(days=5)] * 3, NOW, pending_approved=2).allowed
def test_unknown_policy_is_conservative():
    d = check_quota(None, [NOW - timedelta(days=1)] * 3, NOW, policy_known=False)
    assert not d.allowed
