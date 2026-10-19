# NOTES
Done: backend steps 1-10; step 11 server-rendered UI (still served by `jobagent serve` at /); step 12 scheduler, policy editor, Docker/Postgres/Caddy deploy files;
step 13 React front end in web/ (Vite+TS+Tailwind+Framer Motion, HashRouter, bearer-token JSON API at /api/*, CORS allow-list JOBAGENT_CORS_ORIGINS),
GitHub Actions: pages.yml (test+build+deploy to Pages), tests.yml (pytest + vitest); start-local.sh (backend on user's computer + cloudflared tunnel); FRONTEND.md.
Tests: 191 pytest + 11 vitest. Verified: full HTTP flow across origins (CORS preflight, signup, key, upload, confirm, run, approve) against a live server.
Next: user publishes to GitHub and tries it with a real Claude key; fix whatever breaks. Then: always-on server (DEPLOY.md), Postgres test.
Known limits: Postgres/Docker/GitHub Actions never run in sandbox; real Claude untested; run status in-memory; login limiter per-process; bearer token in localStorage (14-day expiry, no server-side revoke).
