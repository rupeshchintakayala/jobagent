# Front end on GitHub Pages + backend on your computer

## One-time: publish the UI
1. Create a GitHub repository (private is fine; Pages on private repos needs a paid plan, so a **public** repo is simplest. It holds no secrets).
2. Push this whole folder to the `main` branch.
3. In the repo: **Settings -> Pages -> Source: GitHub Actions**.
4. The "Deploy web UI to GitHub Pages" workflow runs on every push and publishes to `https://<your-username>.github.io/<repo-name>/`.
   Check progress under the **Actions** tab. First deploy takes about 2 minutes.

## Every time you want people to use it
1. On your computer, in the project folder (virtualenv active, `pip install -e .` done):
   ```bash
   ./start-local.sh https://<your-username>.github.io
   ```
   - Use only the origin (no `/repo-name`). It is the allow-list for browser requests.
   - It prints an **invite code** and a **https://....trycloudflare.com** address (needs the free `cloudflared` tool).
2. Give users three things: the Pages link, the **server address**, and the **invite code**.
3. They open the Pages link, paste the server address, sign up with the invite code, and follow the 3 setup steps.

Notes
- The quick-tunnel address changes each time you restart it. Users just paste the new one on the login screen.
- The UI only works while your computer is on and the script is running. When you want it always-on, move the backend to a server using DEPLOY.md; the UI stays on Pages (set a repository variable `BACKEND_URL` to pre-fill the address).
- Nothing sensitive lives on GitHub: API keys, passwords and CVs stay in the database on your computer.

## Developing the UI
```bash
cd web && npm install
VITE_API_URL=http://127.0.0.1:8000 npm run dev      # then run: JOBAGENT_CORS_ORIGINS=http://localhost:5173 jobagent serve
npm test
```
