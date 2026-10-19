"""SQLAlchemy Core tables: portable across SQLite (prototype) and Postgres (production).
Every user-owned table carries user_id. Shared tables (jobs, companies) do not."""
from __future__ import annotations
import sqlalchemy as sa

metadata = sa.MetaData()
now = sa.func.current_timestamp()
JSON = sa.JSON

users = sa.Table("users", metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("email", sa.String, unique=True, nullable=False),
    sa.Column("created_at", sa.DateTime, server_default=now),
    sa.Column("deleted_at", sa.DateTime))

user_llm_keys = sa.Table("user_llm_keys", metadata,
    sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), primary_key=True),
    sa.Column("provider", sa.String, nullable=False),
    sa.Column("key_encrypted", sa.LargeBinary, nullable=False),
    sa.Column("monthly_cap_eur", sa.Float, nullable=False, server_default="15"),
    sa.Column("verified_at", sa.DateTime))

profiles = sa.Table("profiles", metadata,
    sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), primary_key=True),
    sa.Column("version", sa.Integer, primary_key=True),
    sa.Column("data", JSON, nullable=False),
    sa.Column("confirmed_at", sa.DateTime),
    sa.Column("created_at", sa.DateTime, server_default=now))

preferences = sa.Table("preferences", metadata,
    sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), primary_key=True),
    sa.Column("min_salary_eur", sa.Integer, nullable=False, server_default="80000"),
    sa.Column("locations", JSON), sa.Column("role_keywords", JSON),
    sa.Column("min_score", sa.Integer, nullable=False, server_default="75"),
    sa.Column("auto_submit_allowed", sa.Boolean, nullable=False, server_default=sa.false()))

companies = sa.Table("companies", metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("name", sa.String), sa.Column("normalized_name", sa.String, unique=True),
    sa.Column("ats", sa.String), sa.Column("careers_url", sa.String),
    sa.Column("robots_ok", sa.Boolean), sa.Column("submit_allowed", sa.Boolean, nullable=False, server_default=sa.false()))

company_policies = sa.Table("company_policies", metadata,
    sa.Column("company_id", sa.String, sa.ForeignKey("companies.id"), primary_key=True),
    sa.Column("max_applications", sa.Integer), sa.Column("window_days", sa.Integer),
    sa.Column("cooldown_days", sa.Integer), sa.Column("source_note", sa.String), sa.Column("verified_by", sa.String))

jobs = sa.Table("jobs", metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("source", sa.String), sa.Column("external_id", sa.String),
    sa.Column("url", sa.String, unique=True), sa.Column("dedupe_hash", sa.String, index=True),
    sa.Column("company_id", sa.String), sa.Column("company", sa.String), sa.Column("title", sa.String),
    sa.Column("location", sa.String), sa.Column("salary_min", sa.Integer), sa.Column("salary_max", sa.Integer),
    sa.Column("salary_currency", sa.String), sa.Column("description", sa.Text),
    sa.Column("first_seen", sa.DateTime, server_default=now), sa.Column("last_seen", sa.DateTime),
    sa.Column("closed_at", sa.DateTime))

matches = sa.Table("matches", metadata,
    sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), primary_key=True),
    sa.Column("job_id", sa.String, primary_key=True),
    sa.Column("profile_version", sa.Integer, primary_key=True),
    sa.Column("score", sa.Integer), sa.Column("reasons", JSON), sa.Column("red_flags", JSON),
    sa.Column("created_at", sa.DateTime, server_default=now))

applications = sa.Table("applications", metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
    sa.Column("job_id", sa.String, nullable=False), sa.Column("company_id", sa.String),
    sa.Column("status", sa.String, nullable=False),  # drafted|approved|submitted|rejected|withdrawn|skipped_quota
    sa.Column("cv_text", sa.Text), sa.Column("letter_text", sa.Text),
    sa.Column("applied_at", sa.DateTime), sa.Column("dry_run", sa.Boolean, nullable=False, server_default=sa.true()),
    sa.UniqueConstraint("user_id", "job_id"))

api_usage = sa.Table("api_usage", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("user_id", sa.String, nullable=False, index=True),
    sa.Column("model", sa.String), sa.Column("input_tokens", sa.Integer), sa.Column("output_tokens", sa.Integer),
    sa.Column("cost_eur", sa.Float), sa.Column("created_at", sa.DateTime, server_default=now))

llm_cache = sa.Table("llm_cache", metadata,
    sa.Column("user_id", sa.String, primary_key=True), sa.Column("cache_key", sa.String, primary_key=True),
    sa.Column("value", sa.Text), sa.Column("created_at", sa.DateTime, server_default=now))

audit_log = sa.Table("audit_log", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("user_id", sa.String), sa.Column("action", sa.String, nullable=False),
    sa.Column("detail", JSON), sa.Column("created_at", sa.DateTime, server_default=now))

user_auth = sa.Table("user_auth", metadata,
    sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), primary_key=True),
    sa.Column("password_hash", sa.String, nullable=False))

# Tables whose rows belong to one user (used by delete-my-data and isolation tests).
USER_TABLES = [user_auth, user_llm_keys, profiles, preferences, matches, applications, api_usage, llm_cache]
