# Deployment guide (Render backend + Vercel frontend)

Order matters: backend first (you need its URL), then frontend, then tell the backend the frontend's URL.

## 0. Before you start (on your Mac)
1. Docker memory check (decides if Render FREE is viable; its RAM is 512 MB):
   `make up`, send one chat in the UI, then `docker stats --no-stream`.
   Look at MEM USAGE for the backend. Under ~350 MiB: free tier is OK. Over ~400 MiB: use Starter.
2. Push to GitHub (public repo): `git remote add origin <url>`, `git push -u origin main`.
   Check `git ls-files | grep -E '\.env$'` prints nothing.

## 1. Backend on Render
1. render.com > sign in with GitHub > New + > Blueprint > pick the repo > it reads `render.yaml`.
   (Or New + > Web Service > Docker, Root Directory blank, Dockerfile Path `./backend/Dockerfile`, Docker Context `./backend`.)
2. When asked for secrets: `LLM_API_KEYS` = `key1,key2` (no quotes/spaces). `ALLOWED_ORIGINS` = `http://localhost:3000` for now.
3. Apply. Wait for "Live". Copy the URL (https://lyftr-backend-xxxx.onrender.com).
4. Verify: `curl https://<backend>/health` -> `keys_configured: 2`.
5. `python3 scripts/smoke_test.py https://<backend>` (first request may take ~60 s on free: cold start).

## 2. Frontend on Vercel
1. vercel.com > Add New > Project > import the repo.
2. Root Directory: `frontend`. Framework preset: Vite (auto). Build command `npm run build`, output `dist`.
3. Environment Variable: `VITE_API_BASE_URL` = `https://<backend>.onrender.com` (https, no trailing slash).
4. Deploy. Copy the production URL (https://<project>.vercel.app).

## 3. Connect them (CORS)
1. Render > backend > Environment: `ALLOWED_ORIGINS` = `https://<project>.vercel.app` (add `,http://localhost:3000` if you still want local use). Save (it redeploys).
2. `python3 scripts/smoke_test.py https://<backend> --origin https://<project>.vercel.app` (must be all PASS).
3. Open the Vercel URL in an INCOGNITO window (proves no login needed). Send a message; open DevTools > Console: there must be no CORS errors.

## 4. Persistence (history surviving restarts)
- FREE: filesystem is ephemeral; history is lost on restart/redeploy/15-min sleep. The app still works; say so honestly in the README.
- STARTER (~$7/mo + $0.25/GB): Render > backend > Settings > Instance Type: Starter; Disks > Add Disk: name `lyftr-data`, mount path `/data`, 1 GB.
  Test: send a chat in session `persist-demo`; Render > Manual Deploy > Restart; `curl https://<backend>/sessions/persist-demo/messages` must still return it.
  (The entrypoint chowns /data so the non-root app user can write to the mounted disk.)

## 5. Keep-alive (free tier only)
Free services sleep after 15 min. Evaluators hitting a sleeping backend wait ~1 min. Optional: a free monitor (e.g. UptimeRobot) pinging `https://<backend>/health` every 5 min keeps it warm (one always-on service fits in the 750 h/month allowance).

## Troubleshooting
| Symptom | Cause / fix |
|---|---|
| Browser: "Cannot reach the backend" + CORS error in console | `ALLOWED_ORIGINS` doesn't exactly match the Vercel origin (scheme + host, no path). |
| Frontend calls localhost:8000 | `VITE_API_BASE_URL` missing at Vercel build time: set it, then Redeploy (it's baked in at build). |
| Render deploy "port scan timeout" | Service must listen on $PORT; the image does this by default. Check logs. |
| 502 "provider error" on chat | Wrong model name or bad key; see Render logs. |
| Backend killed / restarting loop, log shows OOM | 512 MB too small: upgrade to Starter or larger. |
