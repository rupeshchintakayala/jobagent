"""Submission is disabled by default. Never submits unless ALL gates pass."""
class SubmitRefused(Exception): ...

def submit(application, *, dry_run: bool = True, user_approved: bool = False,
           company_submit_allowed: bool = False, quota_ok: bool = False, captcha_detected: bool = False):
    if dry_run: raise SubmitRefused("dry-run")
    if not user_approved: raise SubmitRefused("no explicit user approval")
    if not company_submit_allowed: raise SubmitRefused("company not on submit allow-list")
    if not quota_ok: raise SubmitRefused("company quota")
    if captcha_detected: raise SubmitRefused("CAPTCHA: hand to user")
    raise NotImplementedError("live submission not implemented until tests pass")
