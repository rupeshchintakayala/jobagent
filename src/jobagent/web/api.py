"""JSON API for the React front end (served from another origin, e.g. GitHub Pages).
Auth: `Authorization: Bearer <token>` (no cookies, so no CSRF and no third-party-cookie problems).
Same safety rules as the HTML UI: dry-run, human approves, nothing is submitted, every query scoped by user_id."""
from __future__ import annotations
import hmac
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Callable
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from jobagent.budget.guard import BudgetGuard
from jobagent.config import Settings
from jobagent.cvreader import CVReadError, read_cv
from jobagent.db import Repo
from jobagent.llm import InvalidKey, KeyVault, KeyVaultError, LLMClient, LLMError, mask
from jobagent.pipeline import run_daily
from jobagent.profile import Profile, ProfileParseError, ProfileService
from jobagent.safety.service import quota_for
from .security import RateLimiter, Signer, hash_password, verify_password

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_UPLOAD = 5 * 1024 * 1024


class Creds(BaseModel):
    email: str
    password: str
    invite: str = ""


class KeyIn(BaseModel):
    api_key: str
    cap_eur: float = 15.0


class PrefsIn(BaseModel):
    min_salary_eur: int = Field(80000, ge=0, le=1_000_000)
    min_score: int = Field(75, ge=0, le=100)


class PolicyIn(BaseModel):
    company: str = Field(min_length=1, max_length=120)
    max_applications: int | None = Field(None, ge=0, le=1000)
    window_days: int = Field(180, ge=1, le=3650)
    note: str = Field("", max_length=300)


class DeleteIn(BaseModel):
    confirm: str


def build_router(*, repo: Repo, settings: Settings, signer: Signer, limiter: RateLimiter,
                 provider_factory: Callable[[str], object], fetch_jobs: Callable[[Settings], list],
                 runs: dict, runs_lock: threading.Lock, run_in_background: bool, verify_keys: bool) -> APIRouter:
    r = APIRouter(prefix="/api")

    def user(request: Request) -> dict:
        h = request.headers.get("authorization", "")
        got = signer.read(h[7:] if h.lower().startswith("bearer ") else None)
        u = repo.get_user(got[0]) if got else None
        if not u or u["deleted_at"]:
            raise HTTPException(401, "Not signed in")
        return dict(u)

    def token_for(uid: str) -> str:
        return signer.make(uid)[0]

    def llm_for(uid: str) -> LLMClient | None:
        row = repo.get_key(uid)
        if not row:
            return None
        return LLMClient(uid, provider_factory(KeyVault().decrypt(row["key_encrypted"])),
                         BudgetGuard(row["monthly_cap_eur"], repo.month_spend_eur(uid)), usage_sink=repo.record_usage)

    # ---- auth ----
    @r.post("/signup")
    def signup(body: Creds, request: Request):
        ip = request.client.host if request.client else "?"
        if not limiter.allow("signup:" + ip):
            raise HTTPException(429, "Too many attempts. Wait a few minutes.")
        need = os.environ.get("JOBAGENT_INVITE_CODE", "")
        if need and not hmac.compare_digest(body.invite.strip().encode(), need.encode()):
            raise HTTPException(400, "Wrong invite code. Ask the person who invited you.")
        email = body.email.strip().lower()
        if not EMAIL_RE.match(email):
            raise HTTPException(400, "Enter a valid email address.")
        if len(body.password) < 10:
            raise HTTPException(400, "Password must be at least 10 characters.")
        if repo.get_user_by_email(email):
            raise HTTPException(400, "That email is already registered. Log in instead.")
        uid = repo.create_user(email)
        repo.set_password_hash(uid, hash_password(body.password))
        repo.audit(uid, "api_signup")
        return {"token": token_for(uid), "email": email}

    @r.post("/login")
    def login(body: Creds):
        email = body.email.strip().lower()
        if not limiter.allow("login:" + email):
            raise HTTPException(429, "Too many attempts. Wait a few minutes.")
        uid = repo.get_user_by_email(email)
        h = repo.get_password_hash(uid) if uid else None
        if not h or not verify_password(body.password, h):
            raise HTTPException(400, "Wrong email or password.")
        return {"token": token_for(uid), "email": email}

    @r.get("/invite-required")
    def invite_required():
        return {"required": bool(os.environ.get("JOBAGENT_INVITE_CODE"))}

    # ---- overview ----
    @r.get("/me")
    def me(u: dict = Depends(user)):
        uid = u["id"]
        key, latest, confirmed = repo.get_key(uid), repo.latest_profile(uid), repo.latest_confirmed_profile(uid)
        counts = {s: len(repo.list_applications(uid, s)) for s in ("drafted", "approved", "submitted", "rejected")}
        prefs = repo.get_preferences(uid)
        return {"email": u["email"], "has_key": bool(key), "has_profile": bool(latest), "profile_confirmed": bool(confirmed),
                "draft_pending": bool(latest and not latest["confirmed_at"]), "counts": counts,
                "cap_eur": key["monthly_cap_eur"] if key else 15.0, "spent_eur": round(repo.month_spend_eur(uid), 4),
                "run": runs.get(uid), "min_salary_eur": prefs["min_salary_eur"], "min_score": prefs["min_score"]}

    # ---- settings ----
    @r.put("/key")
    def save_key(body: KeyIn, u: dict = Depends(user)):
        key = body.api_key.strip()
        if not (1 <= body.cap_eur <= 500):
            raise HTTPException(400, "Monthly cap must be between €1 and €500.")
        if verify_keys:
            try:
                provider_factory(key).verify_key()
            except InvalidKey:
                raise HTTPException(400, "Claude rejected that key. Check it and try again.")
            except LLMError as e:
                raise HTTPException(502, f"Could not verify the key right now ({e}). Try again in a minute.")
        try:
            enc = KeyVault().encrypt(key)
        except KeyVaultError as e:
            raise HTTPException(500, f"Server setup problem: {e}")
        repo.save_key(u["id"], "claude", enc, body.cap_eur)
        repo.audit(u["id"], "api_set_key")
        return {"masked": mask(key), "cap_eur": body.cap_eur}

    @r.get("/key")
    def get_key(u: dict = Depends(user)):
        row = repo.get_key(u["id"])
        if not row:
            return {"saved": False}
        try:
            masked = mask(KeyVault().decrypt(row["key_encrypted"]))
        except KeyVaultError:
            masked = "unreadable"
        return {"saved": True, "masked": masked, "cap_eur": row["monthly_cap_eur"]}

    @r.put("/prefs")
    def prefs(body: PrefsIn, u: dict = Depends(user)):
        repo.update_preferences(u["id"], min_salary_eur=body.min_salary_eur, min_score=body.min_score)
        return {"ok": True}

    # ---- profile ----
    @r.get("/profile")
    def profile(u: dict = Depends(user)):
        row = repo.latest_profile(u["id"])
        if not row:
            return {"exists": False}
        return {"exists": True, "version": row["version"], "confirmed": row["confirmed_at"] is not None, "data": row["data"]}

    @r.post("/profile/upload")
    async def upload(cv: UploadFile = File(...), u: dict = Depends(user)):
        llm = llm_for(u["id"])
        if not llm:
            raise HTTPException(400, "Add your Claude key first.")
        data = await cv.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "File is too large (max 5 MB).")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / ("cv" + Path(cv.filename or "cv.txt").suffix.lower())
            path.write_bytes(data)
            try:
                text = read_cv(path)
            except CVReadError as e:
                raise HTTPException(400, str(e))
        try:
            v, _ = ProfileService(repo).create_draft(u["id"], text, llm)
        except ProfileParseError as e:
            raise HTTPException(422, f"Could not read your CV: {e}. Try a .txt version.")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"Claude call failed ({type(e).__name__}). Check your key and budget.")
        return {"version": v}

    @r.put("/profile")
    def save_profile(body: Profile, confirm: bool = False, u: dict = Depends(user)):
        row = repo.latest_profile(u["id"])
        if not row or row["confirmed_at"]:
            raise HTTPException(409, "No editable draft. Create a new version first.")
        ProfileService(repo).edit_draft(u["id"], row["version"], body)
        if confirm:
            ProfileService(repo).confirm(u["id"], row["version"])
            repo.audit(u["id"], "api_confirm_profile", {"version": row["version"]})
        return {"version": row["version"], "confirmed": confirm}

    @r.post("/profile/new-version")
    def new_version(u: dict = Depends(user)):
        row = repo.latest_profile(u["id"])
        if not row:
            raise HTTPException(404, "No profile yet.")
        return {"version": repo.add_profile_draft(u["id"], row["data"])}

    # ---- run ----
    def _do_run(uid: str):
        try:
            rep = run_daily(repo, uid, fetch_jobs(settings), llm_for(uid), match_model=settings.match_model,
                            tailor_model=settings.tailor_model)
            msg = f"Fetched {rep.fetched}, queued {len(rep.queue)} drafts, spent €{rep.spent_eur:.4f}."
            if rep.budget_stopped:
                msg += " Budget reached: some jobs were not scored."
            state = {"state": "done", "msg": msg}
        except PermissionError as e:
            state = {"state": "error", "msg": str(e)}
        except Exception as e:  # noqa: BLE001
            state = {"state": "error", "msg": f"Run failed ({type(e).__name__}). Check your key and budget."}
        with runs_lock:
            runs[uid] = state

    @r.post("/run")
    def run(u: dict = Depends(user)):
        uid = u["id"]
        if not repo.get_key(uid):
            raise HTTPException(400, "Add your Claude key first.")
        if not repo.latest_confirmed_profile(uid):
            raise HTTPException(400, "Confirm your profile first.")
        with runs_lock:
            if runs.get(uid, {}).get("state") == "running":
                return {"state": "running", "msg": "A run is already in progress."}
            runs[uid] = {"state": "running", "msg": "Searching and drafting… this takes a few minutes."}
        if run_in_background:
            threading.Thread(target=_do_run, args=(uid,), daemon=True).start()
        else:
            _do_run(uid)
        return runs[uid]

    # ---- queue ----
    def _item(uid: str, a, full: bool = False) -> dict:
        m = repo.get_match(uid, a["job_id"])
        q = quota_for(repo, uid, a["company_id"])
        pol = repo.get_company_policy(a["company_id"])
        d = {"id": a["id"], "title": a["title"], "company": a["company"], "url": a["url"], "status": a["status"],
             "score": m["score"] if m else None, "reasons": (m["reasons"] if m else []) or [],
             "red_flags": (m["red_flags"] if m else []) or [], "quota_remaining": q.remaining,
             "quota_max": pol["max_applications"] if pol else 3, "quota_allowed": q.allowed, "quota_reason": q.reason}
        if full:
            d.update(cv=a["cv_text"], letter=a["letter_text"], location=a.get("location", ""))
        return d

    @r.get("/applications")
    def applications(status: str = "drafted", u: dict = Depends(user)):
        if status not in ("drafted", "approved", "submitted", "rejected"):
            raise HTTPException(400, "Unknown status.")
        items = [_item(u["id"], a) for a in repo.list_applications(u["id"], status)]
        return sorted(items, key=lambda i: i["score"] or 0, reverse=True)

    @r.get("/applications/{aid}")
    def application(aid: str, u: dict = Depends(user)):
        a = repo.get_application(u["id"], aid)
        if not a:
            raise HTTPException(404, "Not found")
        return _item(u["id"], a, full=True)

    @r.post("/applications/{aid}/{action}")
    def act(aid: str, action: str, u: dict = Depends(user)):
        status = {"approve": "approved", "reject": "rejected", "applied": "submitted"}.get(action)
        if not status:
            raise HTTPException(400, "Unknown action.")
        a = repo.get_application(u["id"], aid)
        if not a:
            raise HTTPException(404, "Not found")
        allowed = {"approve": ("drafted",), "reject": ("drafted", "approved"), "applied": ("approved",)}[action]
        if a["status"] not in allowed:
            raise HTTPException(409, f"Can't {action} an application that is {a['status']}.")
        if action == "approve":
            q = quota_for(repo, u["id"], a["company_id"])
            if not q.allowed:
                raise HTTPException(409, f"Company limit reached: {q.reason}")
        repo.set_application_status(u["id"], aid, status)
        repo.audit(u["id"], f"api_{action}", {"application": aid})
        return {"status": status}

    # ---- company limits ----
    @r.get("/policies")
    def policies(u: dict = Depends(user)):
        return [dict(x) for x in repo.list_companies_with_policies()]

    @r.put("/policies")
    def set_policy(body: PolicyIn, u: dict = Depends(user)):
        cid = repo.get_or_create_company(body.company.strip())
        repo.set_company_policy(cid, body.max_applications, body.window_days, note=body.note.strip(), verified_by=u["email"])
        repo.audit(u["id"], "api_set_policy", {"company": body.company, "max": body.max_applications})
        return {"ok": True}

    # ---- privacy ----
    @r.post("/delete-account")
    def delete(body: DeleteIn, u: dict = Depends(user)):
        if body.confirm.strip().lower() != "delete":
            raise HTTPException(400, "Type DELETE to confirm.")
        repo.delete_user_data(u["id"])
        return {"ok": True}

    return r
