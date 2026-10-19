import pytest
from jobagent.submit.runner import submit, SubmitRefused
from jobagent.budget.guard import BudgetGuard, BudgetExceeded
def test_dry_run_refuses(): 
    with pytest.raises(SubmitRefused): submit(object(), user_approved=True, company_submit_allowed=True, quota_ok=True)
def test_needs_approval():
    with pytest.raises(SubmitRefused): submit(object(), dry_run=False, company_submit_allowed=True, quota_ok=True)
def test_captcha_stops():
    with pytest.raises(SubmitRefused): submit(object(), dry_run=False, user_approved=True, company_submit_allowed=True, quota_ok=True, captcha_detected=True)
def test_budget_cap():
    g = BudgetGuard(15, 14.9)
    with pytest.raises(BudgetExceeded): g.check(0.2)
