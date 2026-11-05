# RoleRadar — Production Deployment Guide (Vercel + Render)

This guide documents the production deployment architecture for **RoleRadar** using a split-hosting strategy:
- **Frontend:** [Vercel](https://vercel.com) (Next.js 15 App Router)
- **Backend, Database & Background Worker:** [Render](https://render.com) (FastAPI, Managed PostgreSQL 17, and Worker)

---

## 1. Target Architecture

```
                                      +---------------------------------------------+
                                      |                   VERCEL                    |
                                      |                                             |
[ User Browser ] -------------------> |  Next.js 15 Frontend (App Router, SSR/RSC) |
 (First-party cookies, HTTPS)         |  Root Directory: frontend/                  |
                                      +---------------------------------------------+
                                                             |
                                                             | Server-to-Server
                                                             | (Secure HTTPS via BACKEND_URL)
                                                             v
                                      +---------------------------------------------+
                                      |                   RENDER                    |
                                      |                                             |
                                      |  +---------------------------------------+  |
                                      |  | roleradar-backend (FastAPI / Uvicorn) |  |
                                      |  | - Port: ${PORT:-8000}                 |  |
                                      |  | - Auto Alembic migrations on startup  |  |
                                      |  | - CORS: allow_origins=[APP_ORIGIN]    |  |
                                      |  | - CSRF: check_origin on mutations     |  |
                                      |  | - /api/health endpoint                |  |
                                      |  +---------------------------------------+  |
                                      |                      ^                      |
                                      |                      | Internal ConnString  |
                                      |  +---------------------------------------+  |
                                      |  | roleradar-postgres (PostgreSQL 17)    |  |
                                      |  +---------------------------------------+  |
                                      |                      ^                      |
                                      |                      | Internal ConnString  |
                                      |  +---------------------------------------+  |
                                      |  | roleradar-worker                      |  |
                                      |  | - Command: python -m app.worker       |  |
                                      |  | - Independent monitoring cycles       |  |
                                      |  | - Transactional notification outbox   |  |
                                      |  +---------------------------------------+  |
                                      +---------------------------------------------+
```

### Architecture Highlights
1. **First-Party Authentication (BFF Pattern):**  
   The user's browser interacts exclusively with the Vercel domain (`https://roleradar.vercel.app`). The Next.js Route Handlers (`app/api/*`) act as a Backend-for-Frontend (BFF), forwarding sessions, cookies, and payloads server-to-server to the Render backend. The session cookie (`__Host-jobpulse_session`) is set as a **first-party cookie** on the Vercel domain, avoiding all third-party cookie blocking issues (Safari ITP, Firefox ETP, Chrome Privacy Sandbox).
2. **Dedicated Background Worker:**  
   The worker runs as an independent persistent service (`roleradar-worker`), completely isolated from the FastAPI HTTP web process. It supervises career board polling and outbox email dispatches without degrading HTTP request latency.
3. **Single Migration Runner:**  
   Alembic migrations execute automatically during backend startup (`alembic upgrade head`) before Uvicorn binds to the port. The worker does not run migrations, avoiding migration race conditions.

---

## 2. Summary of Repository Changes

1. **`render.yaml` Updated:**
   - Provisioning strictly limited to the 3 required Render services: `roleradar-postgres`, `roleradar-backend`, and `roleradar-worker`.
   - Removed frontend from Render blueprint (frontend is hosted on Vercel).
   - Configured `healthCheckPath: /api/health` for the backend.
   - Pinned safe `EMAIL_PROVIDER=disabled` default so notifications enter `cancelled` without failing before Resend credentials are supplied.
2. **`docker/backend.Dockerfile` Updated:**
   - Modified entrypoint CMD from hardcoded `--port 8000` to `--port ${PORT:-8000}` to dynamically support Render's `$PORT` environment variable while retaining local Docker Compose compatibility.
3. **`backend/app/core/config.py` Updated:**
   - Added `field_validator` on `database_url` to automatically normalize legacy `postgres://` URLs (commonly injected by Render/Heroku) into `postgresql+psycopg://`.
4. **`backend/app/db/session.py` Updated:**
   - Added `pool_recycle=1800` alongside `pool_pre_ping=True` to gracefully recycle idle connections across Render cloud load balancers.

---

## 3. Render Setup & Deployment

### 3.1 Step 1: Create a Render Account
1. Sign up or log in at [dashboard.render.com](https://dashboard.render.com).
2. Connect your GitHub account under **Account Settings** → **Connected Accounts**.

### 3.2 Step 2: Deploy Blueprint
1. In the Render Dashboard, click **New +** → **Blueprint**.
2. Select your repository: `codebynikhil-cpp/JobPulse`.
3. Render automatically parses [`render.yaml`](../render.yaml) and provisions:
   - **`roleradar-postgres`**: PostgreSQL 17 database.
   - **`roleradar-backend`**: Docker Web Service running FastAPI.
   - **`roleradar-worker`**: Docker Worker Service running `python -m app.worker`.
4. Click **Apply**.

### 3.3 Step 3: Configure Render Environment Variables
In the Render dashboard, configure the following variables for `roleradar-backend`:

| Service | Environment Variable | Value | Description |
|---|---|---|---|
| `roleradar-backend` | `DATABASE_URL` | Auto-wired from database | Render managed connection string |
| `roleradar-backend` | `COOKIE_SECURE` | `true` | Enforces `__Host-` cookie prefix on HTTPS |
| `roleradar-backend` | `TRUST_FORWARDED_FOR` | `true` | Trusts Render proxy headers |
| `roleradar-backend` | `APP_ORIGIN` | `https://your-app.vercel.app` | **Your Vercel frontend domain** (see Section 4) |
| `roleradar-backend` | `EMAIL_PROVIDER` | `disabled` (or `resend`) | Set to `resend` once API key is ready |
| `roleradar-backend` | `RESEND_API_KEY` | *(Optional)* `re_...` | Resend API key |
| `roleradar-backend` | `EMAIL_FROM` | *(Optional)* `RoleRadar <alerts@domain.com>` | Verified sender address |

For `roleradar-worker`:
| Service | Environment Variable | Value | Description |
|---|---|---|---|
| `roleradar-worker` | `DATABASE_URL` | Auto-wired from database | Render managed connection string |
| `roleradar-worker` | `EMAIL_PROVIDER` | `disabled` (or `resend`) | Match backend setting |
| `roleradar-worker` | `RESEND_API_KEY` | *(Optional)* `re_...` | Resend API key |
| `roleradar-worker` | `EMAIL_FROM` | *(Optional)* `RoleRadar <alerts@domain.com>` | Verified sender address |

---

## 4. Vercel Setup & Deployment

### 4.1 Step 1: Import Project into Vercel
1. Log in to [vercel.com](https://vercel.com).
2. Click **Add New...** → **Project**.
3. Select your `JobPulse` repository from GitHub.

### 4.2 Step 2: Configure Project Settings
In the Vercel configuration screen:
- **Framework Preset:** `Next.js`
- **Root Directory:** Click **Edit** and select `frontend`.
- **Build Command:** `npm run build` (default)
- **Output Directory:** `.next` (default)
- **Install Command:** `npm install` (default)

### 4.3 Step 3: Configure Vercel Environment Variables
Add the following environment variable in the Vercel project settings:

| Environment Variable | Value | Scope | Notes |
|---|---|---|---|
| `BACKEND_URL` | `https://roleradar-backend.onrender.com` | Production, Preview | **No trailing slash**. The public HTTPS URL of your Render backend service. |
| `TRUST_FORWARDED_FOR` | `true` | Production, Preview | Enables client IP forwarding for rate limiting |

> **Security Note:** Do NOT add `NEXT_PUBLIC_` prefixes to `BACKEND_URL`. Next.js keeps `BACKEND_URL` strictly server-side, protecting your backend network topology from the client browser.

### 4.4 Step 4: Deploy & Sync Domains
1. Click **Deploy**. Vercel will build and assign a production URL (e.g., `https://roleradar.vercel.app`).
2. Copy this URL.
3. Return to **Render** → `roleradar-backend` → **Environment**, and set:
   ```
   APP_ORIGIN = https://roleradar.vercel.app
   ```
4. Save changes on Render. Render will automatically redeploy the backend with the new allowed origin.

---

## 5. Cross-Origin Authentication & Security

### 5.1 Cookie Security & Cross-Site Behavior
- **SameSite Policy:** `SameSite=Lax`.
- **HttpOnly:** `true`. JavaScript cannot inspect or exfiltrate session tokens.
- **Secure Flag:** `COOKIE_SECURE=true` ensures the browser sends the cookie only over HTTPS.
- **`__Host-` Prefix:** Enforces that the cookie can only be sent to the exact Vercel host that set it, not subdomains, and cannot be overwritten by insecure HTTP connections.
- **No Third-Party Cookies:** Because all browser requests target `https://roleradar.vercel.app/api/*`, the session cookie is first-party. Cross-site tracking blocks do not interfere with authentication.

### 5.2 CSRF Defense
All state-modifying requests (`POST`, `PATCH`, `DELETE`) enforce origin verification via `check_origin` dependency in FastAPI:
```python
def check_origin(request: Request) -> None:
    if request.headers.get("origin") != settings.app_origin:
        raise HTTPException(403, "Invalid request origin")
```
The Next.js route handlers explicitly forward the browser's `Origin` header (`https://roleradar.vercel.app`), guaranteeing end-to-end CSRF defense.

### 5.3 Client IP Rate Limiting
- Login attempt limiting (`AUTH_FAILURE_LIMIT=5` per 15-minute window) uses the client IP.
- With `TRUST_FORWARDED_FOR=true`, Next.js extracts `x-forwarded-for` and passes it to FastAPI, which safely inspects the first client IP.

---

## 6. Email Notification Configuration (Resend)

To activate live email notifications:
1. Create an account at [resend.com](https://resend.com) and add a domain under **Domains**.
2. Add the required DNS records (SPF, DKIM) to your DNS provider.
3. Generate an API Key under **API Keys**.
4. In Render, set the following environment variables on **both** `roleradar-backend` and `roleradar-worker`:
   ```ini
   EMAIL_PROVIDER=resend
   RESEND_API_KEY=re_your_api_key_here
   EMAIL_FROM=RoleRadar <notifications@yourverifieddomain.com>
   ```
5. Deploy latest commit on both services.

---

## 7. Deployment Verification Checklist

After deploying to Render and Vercel, verify each step:

- [ ] **Backend Health:** Open `https://roleradar-backend.onrender.com/api/health` in browser. Expect `{"status": "ok"}`.
- [ ] **Frontend Landing Page:** Open `https://roleradar.vercel.app`. Verify landing page renders cleanly (HTTP 200).
- [ ] **Database Connectivity:** Check Render backend deployment logs for: `alembic upgrade head` completing with `Running upgrade ... -> 0010`.
- [ ] **User Registration:** Navigate to `/signup`, register a new user account. Verify redirect to `/dashboard`.
- [ ] **Session Persistence:** Refresh `/dashboard`. Verify account email appears in header and user remains logged in.
- [ ] **Job Search Profile:** Navigate to `/profiles/new`, create a profile with target titles (`Backend Engineer`), skills (`Python`, `FastAPI`), and location (`Remote`).
- [ ] **Company Monitoring:** Navigate to `/companies`, subscribe to a supported company (e.g. `Linear`).
- [ ] **Worker Verification:** Check `roleradar-worker` logs in Render. Confirm hourly execution entries: `Source ingestion succeeded` and `Monitoring source completed`.
- [ ] **Feed & Matches:** Return to `/dashboard` and `/jobs`. Verify matches are populated with match scores.
- [ ] **Job Actions:** Click **Save** on a job posting. Verify it appears under `/saved`. Mark as **Applied**, verify under `/applied`.

---

## 8. Troubleshooting & Rollback

### 8.1 Common Issues & Solutions

| Symptom | Cause | Solution |
|---|---|---|
| Frontend returns 502 Bad Gateway on `/api/*` | `BACKEND_URL` misconfigured on Vercel | Ensure `BACKEND_URL` on Vercel is set to `https://roleradar-backend.onrender.com` without trailing slash. |
| Login / Signup returns 403 Forbidden | `APP_ORIGIN` mismatch on Render | Set `APP_ORIGIN=https://roleradar.vercel.app` on `roleradar-backend` in Render dashboard. |
| Database connection error on startup | Unsupported `postgres://` scheme | Handled automatically by RoleRadar's `normalize_database_url` validator. Verify `DATABASE_URL` is linked to `roleradar-postgres`. |
| Session cookie not set on login | `COOKIE_SECURE=true` over HTTP | Ensure you are testing over HTTPS. Browsers reject `__Host-` cookies over non-HTTPS connections. |
| Worker not processing jobs | Worker container stopped | In Render, check `roleradar-worker` status. Note: Render free tier does not support persistent background workers. |

### 8.2 Rollback Procedure
1. **Frontend (Vercel):**
   - In the Vercel Dashboard, go to **Deployments**.
   - Find the previous stable deployment, click the `...` menu, and select **Promote to Production**. Instant rollback occurs with zero build delay.
2. **Backend (Render):**
   - In the Render Dashboard, select `roleradar-backend`.
   - Go to **Deploys**, find the last successful deploy, and click **Rollback to this deploy**.
   - If an Alembic migration rollback is needed:
     ```bash
     alembic downgrade -1
     ```

---

## 9. Database Backup & Restore Procedures

### 9.1 Render Automated Backups
Render Managed PostgreSQL automatically performs daily logical backups on paid plans with point-in-time recovery (PITR).
To download a manual snapshot:
1. Go to `roleradar-postgres` in the Render dashboard.
2. Navigate to **Backups** → **Create Manual Backup**.
3. Download the `.dump` file when complete.

### 9.2 CLI Backup & Restore
To perform an on-demand backup using standard PostgreSQL client tools:

```bash
# Export from Render PostgreSQL
pg_dump "postgresql://roleradar:PASSWORD@HOST.oregon-postgres.render.com/roleradar" -F c -b -v -f roleradar_backup.dump

# Restore into Render PostgreSQL
pg_restore -d "postgresql://roleradar:PASSWORD@HOST.oregon-postgres.render.com/roleradar" --clean --if-exists roleradar_backup.dump
```

---

## 10. Estimated Monthly Hosting Costs

| Component | Platform | Free Tier Feasibility | Recommended Paid Production Tier | Monthly Cost (USD) |
|---|---|---|---|---|
| **Next.js Frontend** | Vercel | ✅ **Free (Hobby)**: 100 GB bandwidth, unlimited serverless invocations. | Vercel Pro (optional, for custom team domains/SLAs) | **$0** (or $20/seat) |
| **FastAPI Backend** | Render | ⚠️ **Free Web Service**: Spins down after 15 min inactivity, 50-second cold starts. | Starter Web Service (512 MB RAM, 0.5 CPU, 100% uptime) | **$7.00** |
| **PostgreSQL 17** | Render | ⚠️ **Free Postgres**: Database expires after 30 days. No automated backups. | Starter PostgreSQL (1 GB RAM, 1 CPU, 256 GB storage) | **$7.00** |
| **Background Worker** | Render | ❌ **No Free Tier**: Background workers are paid-only on Render. | Starter Worker Service (512 MB RAM, 0.5 CPU, continuous loop) | **$7.00** |
| **Total Estimated Cost** | — | **Not recommended** (worker requires paid tier; DB expires) | **Production Deployment** | **~$21.00 / month** |

> **DevOps Recommendation:** For an always-on, resume-worthy production deployment, the **$21/month** Render Starter plan (1 Web + 1 Worker + 1 Database) combined with the **Free Vercel Hobby** plan provides zero cold starts, continuous background job monitoring, and persistent PostgreSQL storage.

