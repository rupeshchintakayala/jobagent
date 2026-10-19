"""Repository: every user-owned query takes user_id explicitly."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
import sqlalchemy as sa
from . import tables as t


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Repo:
    def __init__(self, engine: sa.Engine):
        self.engine = engine

    # users
    def create_user(self, email: str) -> str:
        uid = str(uuid.uuid4())
        with self.engine.begin() as c:
            c.execute(sa.insert(t.users).values(id=uid, email=email.lower().strip()))
            c.execute(sa.insert(t.preferences).values(user_id=uid))
        return uid

    def get_user_by_email(self, email: str) -> str | None:
        with self.engine.connect() as c:
            return c.execute(sa.select(t.users.c.id).where(t.users.c.email == email.lower().strip())).scalar()

    # web auth
    def set_password_hash(self, user_id: str, pw_hash: str) -> None:
        with self.engine.begin() as c:
            c.execute(sa.delete(t.user_auth).where(t.user_auth.c.user_id == user_id))
            c.execute(sa.insert(t.user_auth).values(user_id=user_id, password_hash=pw_hash))

    def get_password_hash(self, user_id: str) -> str | None:
        with self.engine.connect() as c:
            return c.execute(sa.select(t.user_auth.c.password_hash).where(t.user_auth.c.user_id == user_id)).scalar()

    def get_user(self, user_id: str):
        with self.engine.connect() as c:
            return c.execute(sa.select(t.users).where(t.users.c.id == user_id)).mappings().first()

    def get_application(self, user_id: str, application_id: str):
        q = sa.select(t.applications, t.jobs.c.title, t.jobs.c.company, t.jobs.c.url, t.jobs.c.location).join(
            t.jobs, t.jobs.c.id == t.applications.c.job_id).where(
            t.applications.c.user_id == user_id, t.applications.c.id == application_id)
        with self.engine.connect() as c:
            return c.execute(q).mappings().first()

    def get_match(self, user_id: str, job_id: str):
        with self.engine.connect() as c:
            return c.execute(sa.select(t.matches).where(t.matches.c.user_id == user_id, t.matches.c.job_id == job_id)
                             .order_by(t.matches.c.profile_version.desc()).limit(1)).mappings().first()

    def latest_profile(self, user_id: str):
        with self.engine.connect() as c:
            return c.execute(sa.select(t.profiles).where(t.profiles.c.user_id == user_id)
                             .order_by(t.profiles.c.version.desc()).limit(1)).mappings().first()

    def update_preferences(self, user_id: str, **vals) -> None:
        with self.engine.begin() as c:
            c.execute(sa.update(t.preferences).where(t.preferences.c.user_id == user_id).values(**vals))

    # api usage
    def record_usage(self, row: dict) -> None:
        with self.engine.begin() as c:
            c.execute(sa.insert(t.api_usage).values(**row))

    def month_spend_eur(self, user_id: str, now: datetime | None = None) -> float:
        now = now or _now()
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        with self.engine.connect() as c:
            v = c.execute(sa.select(sa.func.coalesce(sa.func.sum(t.api_usage.c.cost_eur), 0.0))
                          .where(t.api_usage.c.user_id == user_id, t.api_usage.c.created_at >= start)).scalar()
        return float(v)

    # keys
    def save_key(self, user_id: str, provider: str, key_encrypted: bytes, monthly_cap_eur: float = 15.0) -> None:
        with self.engine.begin() as c:
            c.execute(sa.delete(t.user_llm_keys).where(t.user_llm_keys.c.user_id == user_id))
            c.execute(sa.insert(t.user_llm_keys).values(user_id=user_id, provider=provider,
                                                        key_encrypted=key_encrypted, monthly_cap_eur=monthly_cap_eur))

    def get_key(self, user_id: str):
        with self.engine.connect() as c:
            return c.execute(sa.select(t.user_llm_keys).where(t.user_llm_keys.c.user_id == user_id)).mappings().first()

    # profiles (versioned; only confirmed ones are usable downstream)
    def add_profile_draft(self, user_id: str, data: dict) -> int:
        with self.engine.begin() as c:
            cur = c.execute(sa.select(sa.func.coalesce(sa.func.max(t.profiles.c.version), 0))
                            .where(t.profiles.c.user_id == user_id)).scalar()
            v = int(cur) + 1
            c.execute(sa.insert(t.profiles).values(user_id=user_id, version=v, data=data))
        return v

    def update_profile_draft(self, user_id: str, version: int, data: dict) -> None:
        with self.engine.begin() as c:
            r = c.execute(sa.update(t.profiles).where(t.profiles.c.user_id == user_id, t.profiles.c.version == version,
                                                      t.profiles.c.confirmed_at.is_(None)).values(data=data))
            if r.rowcount != 1:
                raise ValueError("only unconfirmed drafts can be edited; create a new version instead")

    def confirm_profile(self, user_id: str, version: int) -> None:
        with self.engine.begin() as c:
            r = c.execute(sa.update(t.profiles).where(t.profiles.c.user_id == user_id, t.profiles.c.version == version)
                          .values(confirmed_at=_now()))
            if r.rowcount != 1:
                raise ValueError("profile version not found")

    def get_profile(self, user_id: str, version: int):
        with self.engine.connect() as c:
            return c.execute(sa.select(t.profiles).where(t.profiles.c.user_id == user_id,
                                                         t.profiles.c.version == version)).mappings().first()

    def latest_confirmed_profile(self, user_id: str):
        with self.engine.connect() as c:
            return c.execute(sa.select(t.profiles).where(t.profiles.c.user_id == user_id,
                                                         t.profiles.c.confirmed_at.is_not(None))
                             .order_by(t.profiles.c.version.desc()).limit(1)).mappings().first()

    # llm cache
    def cache_get(self, user_id: str, key: str) -> str | None:
        with self.engine.connect() as c:
            return c.execute(sa.select(t.llm_cache.c.value).where(t.llm_cache.c.user_id == user_id,
                                                                  t.llm_cache.c.cache_key == key)).scalar()

    def cache_set(self, user_id: str, key: str, value: str) -> None:
        with self.engine.begin() as c:
            c.execute(sa.delete(t.llm_cache).where(t.llm_cache.c.user_id == user_id, t.llm_cache.c.cache_key == key))
            c.execute(sa.insert(t.llm_cache).values(user_id=user_id, cache_key=key, value=value))

    # ---- companies / policies ----
    @staticmethod
    def normalize_company(name: str) -> str:
        import re
        n = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
        n = re.sub(r"\b(ltd|limited|inc|llc|gmbh|plc|corp|corporation|ireland|the)\b", " ", n)
        return re.sub(r"\s+", " ", n).strip()

    def get_or_create_company(self, name: str, ats: str | None = None) -> str:
        norm = self.normalize_company(name)
        def find(c):
            return c.execute(sa.select(t.companies.c.id).where(t.companies.c.normalized_name == norm)).scalar()
        with self.engine.begin() as c:
            row = find(c)
            if row:
                return row
        cid = str(uuid.uuid4())
        try:
            with self.engine.begin() as c:
                c.execute(sa.insert(t.companies).values(id=cid, name=name, normalized_name=norm, ats=ats))
            return cid
        except sa.exc.IntegrityError:      # another worker created it first
            with self.engine.begin() as c:
                return find(c)

    def set_company_policy(self, company_id: str, max_applications: int | None, window_days: int = 180,
                           cooldown_days: int | None = None, note: str = "", verified_by: str = "") -> None:
        with self.engine.begin() as c:
            c.execute(sa.delete(t.company_policies).where(t.company_policies.c.company_id == company_id))
            c.execute(sa.insert(t.company_policies).values(company_id=company_id, max_applications=max_applications,
                      window_days=window_days, cooldown_days=cooldown_days, source_note=note, verified_by=verified_by))

    def get_company_policy(self, company_id: str):
        with self.engine.connect() as c:
            return c.execute(sa.select(t.company_policies).where(t.company_policies.c.company_id == company_id)).mappings().first()

    def list_companies_with_policies(self):
        q = sa.select(t.companies.c.id, t.companies.c.name, t.company_policies.c.max_applications,
                      t.company_policies.c.window_days, t.company_policies.c.source_note).select_from(
            t.companies.outerjoin(t.company_policies, t.company_policies.c.company_id == t.companies.c.id)
        ).order_by(t.companies.c.name)
        with self.engine.connect() as c:
            return c.execute(q).mappings().all()

    def list_runnable_users(self) -> list[dict]:
        """Users with a saved key AND a confirmed profile (the only ones the scheduler may run)."""
        q = sa.select(t.users.c.id, t.users.c.email).join(t.user_llm_keys, t.user_llm_keys.c.user_id == t.users.c.id).where(
            t.users.c.deleted_at.is_(None),
            sa.exists().where(t.profiles.c.user_id == t.users.c.id, t.profiles.c.confirmed_at.is_not(None)))
        with self.engine.connect() as c:
            return [dict(r) for r in c.execute(q).mappings().all()]

    def last_run_at(self, user_id: str):
        with self.engine.connect() as c:
            return c.execute(sa.select(sa.func.max(t.audit_log.c.created_at)).where(
                t.audit_log.c.user_id == user_id, t.audit_log.c.action == "run_daily")).scalar()

    # ---- jobs (shared pool) ----
    def upsert_job(self, job, company_id: str) -> str:
        with self.engine.begin() as c:
            row = c.execute(sa.select(t.jobs.c.id).where(t.jobs.c.url == job.url)).scalar()
            if row:
                c.execute(sa.update(t.jobs).where(t.jobs.c.id == row).values(last_seen=_now()))
                return row
            jid = str(uuid.uuid4())
            c.execute(sa.insert(t.jobs).values(
                id=jid, source=job.source, external_id=job.external_id, url=job.url, dedupe_hash=job.dedupe_hash,
                company_id=company_id, company=job.company, title=job.title, location=job.location,
                salary_min=job.salary_min, salary_max=job.salary_max, salary_currency=job.salary_currency,
                description=job.description, last_seen=_now()))
            return jid

    def applied_urls_and_hashes(self, user_id: str) -> tuple[set[str], set[str]]:
        with self.engine.connect() as c:
            rows = c.execute(sa.select(t.jobs.c.url, t.jobs.c.dedupe_hash).join(
                t.applications, t.applications.c.job_id == t.jobs.c.id).where(t.applications.c.user_id == user_id)).all()
        return {r[0] for r in rows}, {r[1] for r in rows}

    # ---- applications ----
    def create_application(self, user_id: str, job_id: str, company_id: str, status: str = "drafted",
                           cv_text: str = "", letter_text: str = "") -> str | None:
        """Returns None if this user already has an application row for the job."""
        aid = str(uuid.uuid4())
        try:
            with self.engine.begin() as c:
                c.execute(sa.insert(t.applications).values(id=aid, user_id=user_id, job_id=job_id, company_id=company_id,
                          status=status, cv_text=cv_text, letter_text=letter_text, dry_run=True))
        except sa.exc.IntegrityError:
            return None
        return aid

    def set_application_status(self, user_id: str, application_id: str, status: str) -> None:
        vals = {"status": status}
        if status == "submitted":
            vals["applied_at"] = _now()
        with self.engine.begin() as c:
            r = c.execute(sa.update(t.applications).where(t.applications.c.id == application_id,
                          t.applications.c.user_id == user_id).values(**vals))
            if r.rowcount != 1:
                raise ValueError("application not found for this user")

    def list_applications(self, user_id: str, status: str | None = None):
        q = sa.select(t.applications, t.jobs.c.title, t.jobs.c.company, t.jobs.c.url).join(
            t.jobs, t.jobs.c.id == t.applications.c.job_id).where(t.applications.c.user_id == user_id)
        if status:
            q = q.where(t.applications.c.status == status)
        with self.engine.connect() as c:
            return c.execute(q).mappings().all()

    def company_application_stats(self, user_id: str, company_id: str) -> tuple[list[datetime], int]:
        """(dates of submitted applications, count of approved-but-not-yet-submitted)."""
        with self.engine.connect() as c:
            sub = [r[0] for r in c.execute(sa.select(t.applications.c.applied_at).where(
                t.applications.c.user_id == user_id, t.applications.c.company_id == company_id,
                t.applications.c.status == "submitted", t.applications.c.applied_at.is_not(None))).all()]
            pend = c.execute(sa.select(sa.func.count()).select_from(t.applications).where(
                t.applications.c.user_id == user_id, t.applications.c.company_id == company_id,
                t.applications.c.status == "approved")).scalar()
        return sub, int(pend or 0)

    # ---- matches ----
    def save_match(self, user_id: str, job_id: str, profile_version: int, score: int, reasons: list, red_flags: list) -> None:
        with self.engine.begin() as c:
            c.execute(sa.delete(t.matches).where(t.matches.c.user_id == user_id, t.matches.c.job_id == job_id,
                                                 t.matches.c.profile_version == profile_version))
            c.execute(sa.insert(t.matches).values(user_id=user_id, job_id=job_id, profile_version=profile_version,
                                                  score=score, reasons=reasons, red_flags=red_flags))

    # ---- audit / preferences ----
    def audit(self, user_id: str | None, action: str, detail: dict | None = None) -> None:
        with self.engine.begin() as c:
            c.execute(sa.insert(t.audit_log).values(user_id=user_id, action=action, detail=detail or {}))

    def get_preferences(self, user_id: str):
        with self.engine.connect() as c:
            return c.execute(sa.select(t.preferences).where(t.preferences.c.user_id == user_id)).mappings().first()

    # ---- GDPR ----
    def delete_user_data(self, user_id: str) -> None:
        """Remove every row belonging to the user. Shared tables (jobs, companies) hold no personal data."""
        with self.engine.begin() as c:
            for table in t.USER_TABLES:
                c.execute(sa.delete(table).where(table.c.user_id == user_id))
            c.execute(sa.delete(t.audit_log).where(t.audit_log.c.user_id == user_id))
            c.execute(sa.delete(t.users).where(t.users.c.id == user_id))
