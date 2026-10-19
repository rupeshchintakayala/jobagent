# Deploy (one small server)

You need: a cheap Linux server (about EUR 5/month, e.g. Hetzner or DigitalOcean), a domain name pointing to its IP, and Docker installed.

1. Copy this folder to the server (`scp` or `git clone`).
2. Create the settings file:
   ```bash
   cp .env.example .env
   python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"   # paste as JOBAGENT_MASTER_KEY
   python3 -c "import secrets;print(secrets.token_urlsafe(48))"                                  # paste as JOBAGENT_SESSION_SECRET
   ```
   (Or run `docker compose run --rm app jobagent init-master-key` for the first one.) Set DOMAIN and a long POSTGRES_PASSWORD.
3. Start everything:
   ```bash
   docker compose up -d --build
   ```
   Caddy gets the HTTPS certificate automatically. Open https://your-domain.
4. Daily search: the app runs it itself every 24 hours (`JOBAGENT_SCHEDULE_HOURS`). To run it by hand:
   `docker compose exec app jobagent run-all`.
5. Company limits: `docker compose exec app jobagent set-policy "Stripe" --max-applications 5 --note "careers page"` (or the Company limits page).

## Safety checklist
- Back up `.env` somewhere safe (password manager). Losing the master key = every saved Claude key is unreadable (users just re-paste).
- Back up Postgres: `docker compose exec db pg_dump -U jobagent jobagent > backup.sql` (weekly).
- Update: `git pull && docker compose up -d --build`.
- Logs: `docker compose logs -f app`.
- Set `JOBAGENT_INVITE_CODE` in `.env` and share the code only with your ~10 users; without it anyone who finds the URL can sign up.
