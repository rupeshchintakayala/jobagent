-- Postgres (SQLite-compatible subset). Every user-owned table has user_id.
CREATE TABLE users (id UUID PRIMARY KEY, email TEXT UNIQUE NOT NULL, created_at TIMESTAMPTZ DEFAULT now(), deleted_at TIMESTAMPTZ);
CREATE TABLE user_llm_keys (user_id UUID PRIMARY KEY REFERENCES users(id), provider TEXT NOT NULL, key_encrypted BYTEA NOT NULL, monthly_cap_eur NUMERIC DEFAULT 15, verified_at TIMESTAMPTZ);
CREATE TABLE profiles (user_id UUID REFERENCES users(id), version INT, data JSONB NOT NULL, confirmed_at TIMESTAMPTZ, PRIMARY KEY (user_id, version));
CREATE TABLE preferences (user_id UUID PRIMARY KEY REFERENCES users(id), min_salary_eur INT DEFAULT 80000, locations JSONB, role_keywords JSONB, min_score INT DEFAULT 75, auto_submit_allowed BOOLEAN DEFAULT false);
-- shared job pool (no user_id)
CREATE TABLE jobs (id UUID PRIMARY KEY, source TEXT, url TEXT UNIQUE, dedupe_hash TEXT, company_id UUID, title TEXT, location TEXT, salary_min INT, salary_max INT, description TEXT, first_seen TIMESTAMPTZ DEFAULT now(), last_seen TIMESTAMPTZ, closed_at TIMESTAMPTZ);
CREATE INDEX jobs_hash ON jobs(dedupe_hash);
CREATE TABLE companies (id UUID PRIMARY KEY, name TEXT, normalized_name TEXT UNIQUE, ats TEXT, careers_url TEXT, robots_ok BOOLEAN, submit_allowed BOOLEAN DEFAULT false);
-- per-company application limits (see QUOTAS)
CREATE TABLE company_policies (company_id UUID PRIMARY KEY REFERENCES companies(id), max_applications INT, window_days INT, scope TEXT DEFAULT 'per_company', cooldown_days INT, source_note TEXT, verified_by TEXT);
CREATE TABLE matches (user_id UUID, job_id UUID, score INT, reasons JSONB, red_flags JSONB, profile_version INT, created_at TIMESTAMPTZ DEFAULT now(), PRIMARY KEY (user_id, job_id));
CREATE TABLE applications (id UUID PRIMARY KEY, user_id UUID, job_id UUID, company_id UUID, status TEXT, -- drafted|approved|submitted|rejected|withdrawn|skipped_quota
  cv_artifact TEXT, letter_artifact TEXT, applied_at TIMESTAMPTZ, dry_run BOOLEAN DEFAULT true, UNIQUE (user_id, job_id));
CREATE INDEX app_user_company ON applications(user_id, company_id, applied_at);
CREATE TABLE api_usage (id BIGSERIAL PRIMARY KEY, user_id UUID, model TEXT, input_tokens INT, output_tokens INT, cost_eur NUMERIC, created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE audit_log (id BIGSERIAL PRIMARY KEY, user_id UUID, action TEXT, detail JSONB, created_at TIMESTAMPTZ DEFAULT now());
