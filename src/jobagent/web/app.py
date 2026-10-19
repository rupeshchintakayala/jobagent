"""Server-rendered web UI. Same safety rules as the CLI: dry-run, human approves, nothing is submitted."""
from __future__ import annotations
import hmac
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Callable
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jobagent.budget.guard import BudgetGuard
from jobagent.config import DEFAULT_SOURCES, Settings
from jobagent.cvreader import CVReadError, read_cv
from jobagent.db import Repo, init_db, make_engine
from jobagent.llm import ClaudeProvider, InvalidKey, KeyVault, KeyVaultError, LLMClient, LLMError, mask
from jobagent.pipeline import run_daily
from jobagent.profile import Profile, ProfileParseError, ProfileService
from jobagent.safety.service import quota_for
from jobagent.sources import ADAPTERS
from .security import RateLimiter, Signer, hash_password, verify_password

COOKIE = "ja_session"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_UPLOAD = 5 * 1024 * 1024


def default_fetch_jobs(settings: Settings) -> list:
    jobs = []
    for ats, boards in (settings.sources or DEFAULT_SOURCES).items():
        for b in boards:
            try:
                jobs += ADAPTERS[ats].fetch(b)
            except Exception:  # noqa: BLE001 - one broken board must not stop the run
                continue
    return jobs


def create_app(settings: Settings | None = None, *, provider_factory: Callable[[str], object] | None = None,
               fetch_jobs: Callable[[Settings], list] | None = None, secret: str | None = None,
               run_in_background: bool = True, verify_keys: bool = True) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.db_url)
    init_db(engine)
    repo = Repo(engine)
    secret = secret or os.environ.get("JOBAGENT_SESSION_SECRET")
    if not secret:
        raise RuntimeError("JOBAGENT_SESSION_SECRET is not set. Use any long random string (see RUN_LOCALLY.md).")
    signer = Signer(secret)
    limiter = RateLimiter()
    provider_factory = provider_factory or (lambda key: ClaudeProvider(key))
    fetch_jobs = fetch_jobs or default_fetch_jobs
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(_app):
        _maybe_start_scheduler()
        yield

    app = FastAPI(title="Job agent", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    runs: dict[str, dict] = {}          # user_id -> {"state": running|done|error, "msg": str}
    runs_lock = threading.Lock()

    # ---------- helpers ----------
    def render(request: Request, name: str, ctx: dict | None = None, status: int = 200, user=None):
        c = {"request": request, "user": user, "csrf": getattr(request.state, "csrf", ""), "flash": request.query_params.get("msg", ""),
             "err": request.query_params.get("err", "")}
        c.update(ctx or {})
        return templates.TemplateResponse(request, name, c, status_code=status)

    def current(request: Request):
        got = signer.read(request.cookies.get(COOKIE))
        if not got:
            return None
        uid, csrf = got
        u = repo.get_user(uid)
        if not u or u["deleted_at"]:
            return None
        request.state.csrf = csrf
        return u

    def go(path: str, msg: str = "", err: str = ""):
        from urllib.parse import quote
        q = "&".join(x for x in (f"msg={quote(msg)}" if msg else "", f"err={quote(err)}" if err else "") if x)
        return RedirectResponse(path + ("?" + q if q else ""), status_code=303)

    def start_session(uid: str, resp):
        cookie, _ = signer.make(uid)
        resp.set_cookie(COOKIE, cookie, httponly=True, samesite="lax", max_age=14 * 86400,
                        secure=os.environ.get("JOBAGENT_COOKIE_SECURE", "") == "1")
        return resp

    def csrf_ok(request: Request, token: str) -> bool:
        return bool(token) and token == getattr(request.state, "csrf", None)

    def llm_for(uid: str) -> LLMClient | None:
        row = repo.get_key(uid)
        if not row:
            return None
        provider = provider_factory(KeyVault().decrypt(row["key_encrypted"]))
        return LLMClient(uid, provider, BudgetGuard(row["monthly_cap_eur"], repo.month_spend_eur(uid)), usage_sink=repo.record_usage)

    def setup_state(uid: str) -> dict:
        key = repo.get_key(uid)
        latest = repo.latest_profile(uid)
        confirmed = repo.latest_confirmed_profile(uid)
        return {"has_key": bool(key), "has_draft": bool(latest), "confirmed": bool(confirmed),
                "draft_pending": bool(latest and not latest["confirmed_at"]), "latest": latest,
                "cap": key["monthly_cap_eur"] if key else 15.0, "spent": repo.month_spend_eur(uid)}

    # ---------- public pages ----------
    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        u = current(request)
        if u:
            return RedirectResponse("/dashboard", status_code=303)
        return render(request, "home.html")

    @app.get("/signup", response_class=HTMLResponse)
    def signup_form(request: Request):
        return render(request, "signup.html", {"needs_invite": bool(os.environ.get("JOBAGENT_INVITE_CODE"))})

    @app.post("/signup")
    def signup(request: Request, email: str = Form(...), password: str = Form(...), invite: str = Form("")):
        email = email.strip().lower()
        need = os.environ.get("JOBAGENT_INVITE_CODE", "")
        if need and not hmac.compare_digest(invite.strip().encode(), need.encode()):
            return render(request, "signup.html", {"error": "Wrong invite code. Ask the person who invited you.", "email": email, "needs_invite": True}, 400)
        if not limiter.allow("signup:" + (request.client.host if request.client else "?")):
            return render(request, "signup.html", {"error": "Too many attempts. Wait a few minutes."}, 429)
        if not EMAIL_RE.match(email):
            return render(request, "signup.html", {"error": "Enter a valid email address.", "email": email}, 400)
        if len(password) < 10:
            return render(request, "signup.html", {"error": "Password must be at least 10 characters.", "email": email}, 400)
        if repo.get_user_by_email(email):
            return render(request, "signup.html", {"error": "That email is already registered. Log in instead.", "email": email}, 400)
        uid = repo.create_user(email)
        repo.set_password_hash(uid, hash_password(password))
        repo.audit(uid, "web_signup")
        return start_session(uid, go("/dashboard", msg="Welcome! Three quick steps to get set up."))

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        return render(request, "login.html")

    @app.post("/login")
    def login(request: Request, email: str = Form(...), password: str = Form(...)):
        email = email.strip().lower()
        if not limiter.allow("login:" + email):
            return render(request, "login.html", {"error": "Too many attempts. Wait a few minutes.", "email": email}, 429)
        uid = repo.get_user_by_email(email)
        h = repo.get_password_hash(uid) if uid else None
        if not h or not verify_password(password, h):
            return render(request, "login.html", {"error": "Wrong email or password.", "email": email}, 400)
        return start_session(uid, go("/dashboard"))

    @app.post("/logout")
    def logout(request: Request, csrf: str = Form("")):
        current(request)
        resp = go("/")
        resp.delete_cookie(COOKIE)
        return resp

    # ---------- authenticated pages ----------
    def guard(request: Request):
        u = current(request)
        return u, (None if u else go("/login"))

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request):
        u, redirect = guard(request)
        if redirect:
            return redirect
        s = setup_state(u["id"])
        counts = {st: len(repo.list_applications(u["id"], st)) for st in ("drafted", "approved", "submitted", "rejected")}
        return render(request, "dashboard.html", {"s": s, "counts": counts, "run": runs.get(u["id"]),
                                                  "pct": min(100, int(100 * s["spent"] / s["cap"])) if s["cap"] else 0}, user=u)

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request):
        u, redirect = guard(request)
        if redirect:
            return redirect
        key = repo.get_key(u["id"])
        masked = None
        if key:
            try:
                masked = mask(KeyVault().decrypt(key["key_encrypted"]))
            except KeyVaultError:
                masked = "unreadable"
        return render(request, "settings.html", {"key": key, "masked": masked, "prefs": repo.get_preferences(u["id"])}, user=u)

    @app.post("/settings/key")
    def save_key(request: Request, api_key: str = Form(...), cap_eur: float = Form(15.0), csrf: str = Form("")):
        u, redirect = guard(request)
        if redirect:
            return redirect
        if not csrf_ok(request, csrf):
            return go("/settings", err="Session expired. Try again.")
        api_key = api_key.strip()
        if not (1 <= cap_eur <= 500):
            return go("/settings", err="Monthly cap must be between €1 and €500.")
        if verify_keys:
            try:
                provider_factory(api_key).verify_key()
            except InvalidKey:
                return go("/settings", err="Claude rejected that key. Check it and try again.")
            except LLMError as e:
                return go("/settings", err=f"Could not verify the key right now ({e}). Try again in a minute.")
        try:
            enc = KeyVault().encrypt(api_key)
        except KeyVaultError as e:
            return go("/settings", err=f"Server setup problem: {e}")
        repo.save_key(u["id"], "claude", enc, cap_eur)
        repo.audit(u["id"], "web_set_key")
        return go("/dashboard", msg=f"Key saved ({mask(api_key)}). Monthly cap €{cap_eur:.2f}.")

    @app.post("/settings/prefs")
    def save_prefs(request: Request, min_salary_eur: int = Form(80000), min_score: int = Form(75), csrf: str = Form("")):
        u, redirect = guard(request)
        if redirect:
            return redirect
        if not csrf_ok(request, csrf):
            return go("/settings", err="Session expired. Try again.")
        if not (0 <= min_salary_eur <= 1_000_000 and 0 <= min_score <= 100):
            return go("/settings", err="Salary or score out of range.")
        repo.update_preferences(u["id"], min_salary_eur=min_salary_eur, min_score=min_score)
        return go("/settings", msg="Preferences saved.")

    @app.get("/profile", response_class=HTMLResponse)
    def profile_page(request: Request):
        u, redirect = guard(request)
        if redirect:
            return redirect
        row = repo.latest_profile(u["id"])
        p = Profile.model_validate(row["data"]) if row else None
        return render(request, "profile.html", {"row": row, "p": p, "has_key": bool(repo.get_key(u["id"]))}, user=u)

    @app.post("/profile/upload")
    async def upload(request: Request, cv: UploadFile = File(...), csrf: str = Form("")):
        u, redirect = guard(request)
        if redirect:
            return redirect
        if not csrf_ok(request, csrf):
            return go("/profile", err="Session expired. Try again.")
        llm = llm_for(u["id"])
        if not llm:
            return go("/settings", err="Add your Claude key first.")
        data = await cv.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            return go("/profile", err="File is too large (max 5 MB).")
        suffix = Path(cv.filename or "cv.txt").suffix.lower()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / f"cv{suffix}"
            path.write_bytes(data)
            try:
                text = read_cv(path)
            except CVReadError as e:
                return go("/profile", err=str(e))
        try:
            ProfileService(repo).create_draft(u["id"], text, llm)
        except ProfileParseError as e:
            return go("/profile", err=f"Could not read your CV: {e}. Try a .txt version.")
        except Exception as e:  # noqa: BLE001
            return go("/profile", err=f"Claude call failed ({type(e).__name__}). Check your key and budget.")
        return go("/profile", msg="Draft created. Check every fact, fix anything wrong, then confirm.")

    def _lines(v: str) -> list[str]:
        return [x.strip() for x in v.splitlines() if x.strip()]

    @app.post("/profile/save")
    async def save_profile(request: Request):
        u, redirect = guard(request)
        if redirect:
            return redirect
        f = await request.form()
        if not csrf_ok(request, str(f.get("csrf", ""))):
            return go("/profile", err="Session expired. Try again.")
        row = repo.latest_profile(u["id"])
        if not row or row["confirmed_at"]:
            return go("/profile", err="No editable draft.")
        p = Profile.model_validate(row["data"])
        for k in ("name", "email", "phone", "location", "headline", "summary", "work_authorization"):
            setattr(p, k, str(f.get(k, "")).strip())
        for k in ("skills", "certifications", "languages", "links", "target_roles"):
            setattr(p, k, _lines(str(f.get(k, ""))))
        yrs = str(f.get("years_experience", "")).strip()
        try:
            p.years_experience = float(yrs) if yrs else None
        except ValueError:
            return go("/profile", err="Years of experience must be a number.")
        for i, e in enumerate(p.experience):
            e.company = str(f.get(f"exp{i}_company", e.company)).strip()
            e.title = str(f.get(f"exp{i}_title", e.title)).strip()
            e.start = str(f.get(f"exp{i}_start", e.start)).strip()
            e.end = str(f.get(f"exp{i}_end", e.end)).strip()
            e.summary = str(f.get(f"exp{i}_summary", e.summary)).strip()
            e.achievements = _lines(str(f.get(f"exp{i}_achievements", "")))
            e.technologies = _lines(str(f.get(f"exp{i}_technologies", "")))
        for i, ed in enumerate(p.education):
            ed.institution = str(f.get(f"edu{i}_institution", ed.institution)).strip()
            ed.degree = str(f.get(f"edu{i}_degree", ed.degree)).strip()
            ed.field = str(f.get(f"edu{i}_field", ed.field)).strip()
            ed.year = str(f.get(f"edu{i}_year", ed.year)).strip()
        ProfileService(repo).edit_draft(u["id"], row["version"], p)
        if f.get("action") == "confirm":
            ProfileService(repo).confirm(u["id"], row["version"])
            repo.audit(u["id"], "web_confirm_profile", {"version": row["version"]})
            return go("/dashboard", msg="Profile confirmed. Only these facts will ever be used in your applications.")
        return go("/profile", msg="Draft saved.")

    @app.post("/profile/new-version")
    def new_version(request: Request, csrf: str = Form("")):
        """Editing a confirmed profile creates a new unconfirmed draft (the confirmed one stays in use until you confirm)."""
        u, redirect = guard(request)
        if redirect:
            return redirect
        if not csrf_ok(request, csrf):
            return go("/profile", err="Session expired. Try again.")
        row = repo.latest_profile(u["id"])
        if row:
            repo.add_profile_draft(u["id"], row["data"])
        return go("/profile", msg="New draft created from your confirmed profile.")

    # ---------- run ----------
    def _do_run(uid: str):
        try:
            llm = llm_for(uid)
            jobs = fetch_jobs(settings)
            rep = run_daily(repo, uid, jobs, llm, match_model=settings.match_model, tailor_model=settings.tailor_model)
            msg = f"Fetched {rep.fetched}, queued {len(rep.queue)} drafts, spent €{rep.spent_eur:.4f}."
            if rep.budget_stopped:
                msg += " Budget reached: some jobs were not scored."
            with runs_lock:
                runs[uid] = {"state": "done", "msg": msg}
        except PermissionError as e:
            with runs_lock:
                runs[uid] = {"state": "error", "msg": str(e)}
        except Exception as e:  # noqa: BLE001
            with runs_lock:
                runs[uid] = {"state": "error", "msg": f"Run failed ({type(e).__name__}). Check your key and budget."}

    @app.post("/run")
    def run_now(request: Request, csrf: str = Form("")):
        u, redirect = guard(request)
        if redirect:
            return redirect
        if not csrf_ok(request, csrf):
            return go("/dashboard", err="Session expired. Try again.")
        s = setup_state(u["id"])
        if not s["has_key"]:
            return go("/settings", err="Add your Claude key first.")
        if not s["confirmed"]:
            return go("/profile", err="Confirm your profile first.")
        with runs_lock:
            if runs.get(u["id"], {}).get("state") == "running":
                return go("/dashboard", msg="A run is already in progress.")
            runs[u["id"]] = {"state": "running", "msg": "Searching and drafting… this takes a few minutes."}
        if run_in_background:
            threading.Thread(target=_do_run, args=(u["id"],), daemon=True).start()
        else:
            _do_run(u["id"])
        return go("/dashboard")

    # ---------- review queue ----------
    @app.get("/queue", response_class=HTMLResponse)
    def queue(request: Request, status: str = "drafted"):
        u, redirect = guard(request)
        if redirect:
            return redirect
        if status not in ("drafted", "approved", "submitted", "rejected"):
            status = "drafted"
        items = []
        for r in repo.list_applications(u["id"], status):
            m = repo.get_match(u["id"], r["job_id"])
            q = quota_for(repo, u["id"], r["company_id"])
            pol = repo.get_company_policy(r["company_id"])
            items.append({"a": r, "score": m["score"] if m else None, "reasons": (m["reasons"] if m else []) or [],
                          "flags": (m["red_flags"] if m else []) or [], "remaining": q.remaining,
                          "max": pol["max_applications"] if pol else 3})
        items.sort(key=lambda i: i["score"] or 0, reverse=True)
        return render(request, "queue.html", {"items": items, "status": status}, user=u)

    @app.get("/application/{aid}", response_class=HTMLResponse)
    def application(request: Request, aid: str):
        u, redirect = guard(request)
        if redirect:
            return redirect
        a = repo.get_application(u["id"], aid)          # scoped by user_id: other users' ids return nothing
        if not a:
            return render(request, "message.html", {"title": "Not found", "body": "That application doesn't exist."}, 404, user=u)
        m = repo.get_match(u["id"], a["job_id"])
        q = quota_for(repo, u["id"], a["company_id"])
        pol = repo.get_company_policy(a["company_id"])
        return render(request, "application.html", {"a": a, "m": m, "q": q, "max": pol["max_applications"] if pol else 3}, user=u)

    @app.post("/application/{aid}/{action}")
    def application_action(request: Request, aid: str, action: str, csrf: str = Form("")):
        u, redirect = guard(request)
        if redirect:
            return redirect
        if not csrf_ok(request, csrf):
            return go("/queue", err="Session expired. Try again.")
        status = {"approve": "approved", "reject": "rejected", "applied": "submitted"}.get(action)
        if not status:
            return go("/queue", err="Unknown action.")
        a = repo.get_application(u["id"], aid)
        if not a:
            return go("/queue", err="Application not found.")
        allowed = {"approve": ("drafted",), "reject": ("drafted", "approved"), "applied": ("approved",)}[action]
        if a["status"] not in allowed:
            return go(f"/application/{aid}", err=f"Can't {action} an application that is {a['status']}.")
        repo.set_application_status(u["id"], aid, status)
        repo.audit(u["id"], f"web_{action}", {"application": aid})
        nxt = {"approve": "Approved. Apply on the company's site, then click “I applied”.",
               "reject": "Rejected.", "applied": "Recorded as applied."}[action]
        return go("/queue", msg=nxt)

    # ---------- company limits ----------
    @app.get("/policies", response_class=HTMLResponse)
    def policies(request: Request):
        u, redirect = guard(request)
        if redirect:
            return redirect
        return render(request, "policies.html", {"rows": repo.list_companies_with_policies()}, user=u)

    @app.post("/policies")
    def set_policy(request: Request, company: str = Form(...), max_applications: str = Form(""), window_days: int = Form(180),
                   note: str = Form(""), csrf: str = Form("")):
        u, redirect = guard(request)
        if redirect:
            return redirect
        if not csrf_ok(request, csrf):
            return go("/policies", err="Session expired. Try again.")
        company = company.strip()
        if not company or len(company) > 120 or not (1 <= window_days <= 3650):
            return go("/policies", err="Enter a company name and a window between 1 and 3650 days.")
        try:
            mx = int(max_applications) if max_applications.strip() else None
        except ValueError:
            return go("/policies", err="Max applications must be a whole number (or empty for no limit).")
        if mx is not None and not (0 <= mx <= 1000):
            return go("/policies", err="Max applications must be between 0 and 1000.")
        cid = repo.get_or_create_company(company)
        repo.set_company_policy(cid, mx, window_days, note=note.strip()[:300], verified_by=u["email"])
        repo.audit(u["id"], "web_set_policy", {"company": company, "max": mx})
        return go("/policies", msg=f"Saved limit for {company}.")

    # ---------- privacy ----------
    @app.get("/privacy", response_class=HTMLResponse)
    def privacy(request: Request):
        u, redirect = guard(request)
        if redirect:
            return redirect
        return render(request, "privacy.html", user=u)

    @app.post("/privacy/delete")
    def delete_me(request: Request, confirm: str = Form(""), csrf: str = Form("")):
        u, redirect = guard(request)
        if redirect:
            return redirect
        if not csrf_ok(request, csrf) or confirm.strip().lower() != "delete":
            return go("/privacy", err="Type DELETE to confirm.")
        repo.delete_user_data(u["id"])
        resp = go("/")
        resp.delete_cookie(COOKIE)
        return resp

    def _maybe_start_scheduler():
        hours = float(os.environ.get("JOBAGENT_SCHEDULE_HOURS", "0") or 0)
        if hours <= 0:
            return
        import logging, time
        from jobagent.scheduler import run_all

        def loop():
            while True:
                try:
                    run_all(repo, settings, provider_factory=provider_factory, fetch=fetch_jobs)
                except Exception as e:  # noqa: BLE001
                    logging.getLogger("jobagent.scheduler").error("scheduler pass failed: %s", type(e).__name__)
                time.sleep(hours * 3600)
        threading.Thread(target=loop, daemon=True, name="scheduler").start()

    # ---------- JSON API + CORS for the React front end ----------
    from fastapi.middleware.cors import CORSMiddleware
    from .api import build_router
    origins = [o.strip().rstrip("/") for o in os.environ.get("JOBAGENT_CORS_ORIGINS", "").split(",") if o.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "PUT"],
                           allow_headers=["Authorization", "Content-Type"], allow_credentials=False, max_age=600)
    app.include_router(build_router(repo=repo, settings=settings, signer=signer, limiter=limiter, provider_factory=provider_factory,
                                    fetch_jobs=fetch_jobs, runs=runs, runs_lock=runs_lock, run_in_background=run_in_background,
                                    verify_keys=verify_keys))

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app
