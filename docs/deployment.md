# RoleRadar — Production Deployment Guide

> **Status:** Locally verified and production-ready. Cloud deployment requires Render or Railway credentials.
>
> Local stack verified: 430 backend tests passing, 0 lint/type errors, 4/4 Docker services healthy, full E2E acceptance workflow passing.

---

## 1. Architecture Overview

RoleRadar runs as four independent services:

| Service | Technology | Purpose |
|---|---|---|
| `postgres` | PostgreSQL 17 | Persistent data store |
| `backend` | FastAPI + Python 3.13 | REST API, session auth, job matching |
| `worker` | Same image as backend | Continuous monitoring + notification outbox |
| `frontend` | Next.js 15 / Node 24 | Server-rendered UI + API proxy |

The frontend acts as a full proxy to the backend for all `/api/*` calls. It never exposes the backend directly to the browser's origin.

---

## 2. Local Docker Compose (Development / Self-Hosted)

### 2.1 Requirements
- Docker Engine ≥ 26, Docker Compose ≥ 2.27
- 4 GB RAM minimum (Playwright Chromium adds ~1 GB to backend image)

### 2.2 Initial Setup

```bash
# Clone or unzip repository
cd project_new_v1

# Generate environment file
cp .env.example .env

# Generate secure Postgres password
python -c "import secrets; print(secrets.token_hex(24))"
# Replace 'replace-with-random-local-password' in .env with this value
# Also update DATABASE_URL= line with same password

# Build and start all services
docker compose build
docker compose up -d

# Verify all services are healthy
docker compose ps
```

Expected healthy output:
```
NAME                        STATUS                  PORTS
project_new_v1-backend-1    Up (healthy)    127.0.0.1:8000->8000/tcp
project_new_v1-frontend-1   Up (healthy)    127.0.0.1:3000->3000/tcp
project_new_v1-postgres-1   Up (healthy)    5432/tcp
project_new_v1-worker-1     Up
```

### 2.3 Verify Migrations

```bash
docker compose exec backend alembic current
# Expected: 0010 (head)
```

### 2.4 Run Acceptance Tests

```bash
# 430 backend tests
docker compose exec backend sh -c "cd /app && python -m pytest -c /app/pyproject.toml --rootdir=/app -q"

# Full-stack smoke test (auth, session, dashboard)
python scripts/smoke_stack.py

# Real company integrations (1,787 live jobs)
docker compose exec backend python /app/scripts/validate_real_sources.py

# 15-step end-to-end acceptance (register → ingest → match → notify → save → dedup)
docker compose exec backend python /app/scripts/e2e_real_world.py
```

---

## 3. Render Deployment (Recommended PaaS)

### 3.1 Prerequisites

1. Create a [Render](https://render.com) account.
2. Push the repository to GitHub or GitLab (Render requires a Git source).
3. Connect your Git account in Render Settings.

### 3.2 Blueprint Deployment

The repository contains [`render.yaml`](../render.yaml) which provisions all 4 services automatically.

1. In the Render dashboard, click **New +** → **Blueprint**.
2. Select your repository. Render reads `render.yaml` and shows:
   - `roledar-postgres` — Managed PostgreSQL 17
   - `roledar-backend` — FastAPI web service (auto-runs `alembic upgrade head`)
   - `roledar-worker` — Background worker (`python -m app.worker`)
   - `roledar-frontend` — Next.js web service
3. Click **Apply**.
4. Set the following **secret** environment variables in the Render dashboard before first deploy:

**Required for backend (`roledar-backend`):**

| Variable | Value | Notes |
|---|---|---|
| `APP_ORIGIN` | `https://roledar-frontend.onrender.com` | Your frontend's public URL |

**Optional — Email (backend + worker):**

| Variable | Value | Notes |
|---|---|---|
| `EMAIL_PROVIDER` | `resend` | Change from `disabled` once Resend is configured |
| `RESEND_API_KEY` | `re_...` | From [resend.com](https://resend.com) dashboard |
| `EMAIL_FROM` | `RoleRadar <alerts@yourdomain.com>` | Must be a verified sender domain |

> **Important:** `EMAIL_PROVIDER` defaults to `disabled` in `render.yaml`. Notifications are queued and silently suppressed (not permanently failed) until you set it to `resend` with valid credentials. This is intentional safe behavior.

### 3.3 Environment Variable Wire-Up (Auto-Configured by Blueprint)

| Service | Variable | Auto-wired from |
|---|---|---|
| `roledar-backend` | `DATABASE_URL` | `roledar-postgres` connection string |
| `roledar-backend` | `COOKIE_SECURE` | `true` (hardcoded in blueprint) |
| `roledar-backend` | `TRUST_FORWARDED_FOR` | `true` (hardcoded in blueprint) |
| `roledar-worker` | `DATABASE_URL` | `roledar-postgres` connection string |
| `roledar-frontend` | `BACKEND_URL` | `roledar-backend` service URL (full `https://`) |
| `roledar-frontend` | `TRUST_FORWARDED_FOR` | `true` (hardcoded in blueprint) |

### 3.4 After Deployment: Verify

```bash
# Backend health (replace URL with your actual Render URL)
curl https://roledar-backend.onrender.com/api/health
# Expected: {"status":"ok"}

# Frontend
curl -I https://roledar-frontend.onrender.com/
# Expected: HTTP/2 200

# Run smoke test against production
APP_ORIGIN=https://roledar-frontend.onrender.com python scripts/smoke_stack.py
```

### 3.5 Production APP_ORIGIN Configuration

CSRF protection requires `APP_ORIGIN` to match the actual frontend URL exactly.

After Render deploys the frontend, copy its URL (e.g. `https://roledar-frontend.onrender.com`) and set it in the backend service environment:
```
APP_ORIGIN = https://roledar-frontend.onrender.com
```

Then redeploy the backend service (or it will auto-redeploy).

---

## 4. Railway Deployment

### 4.1 Services to Create

In [Railway](https://railway.app), create a new project with:

1. **PostgreSQL** plugin (Railway managed)
2. **Backend** service from GitHub, Dockerfile: `docker/backend.Dockerfile`  
   Start command: `sh -c 'alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT'`
3. **Worker** service, same Dockerfile, start command: `python -m app.worker`
4. **Frontend** service, Dockerfile: `docker/frontend.Dockerfile`

### 4.2 Environment Variables

**Backend + Worker:**
```
DATABASE_URL = ${{Postgres.DATABASE_URL}}
APP_ORIGIN   = https://<your-frontend-domain>.up.railway.app
COOKIE_SECURE = true
TRUST_FORWARDED_FOR = true
EMAIL_PROVIDER = disabled    # or resend once configured
```

**Frontend:**
```
BACKEND_URL = https://<your-backend-domain>.up.railway.app
TRUST_FORWARDED_FOR = true
```

---

## 5. Self-Hosted Linux VM

### 5.1 System Requirements

- Ubuntu 22.04 LTS or 24.04 LTS
- Minimum: 2 vCPU, 4 GB RAM, 40 GB SSD
- Recommended: 4 vCPU, 8 GB RAM (for Playwright Chromium in worker)
- Open ports: 22, 80, 443

### 5.2 Server Setup

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git ufw jq

# Firewall
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
newgrp docker
```

### 5.3 Application Setup

```bash
cd /opt
sudo git clone https://github.com/your-org/roleradar.git
sudo chown -R $USER:$USER /opt/roleradar
cd /opt/roleradar

cp .env.example .env
# Edit .env with production values:
#   APP_ORIGIN=https://roleradar.yourdomain.com
#   COOKIE_SECURE=true
#   TRUST_FORWARDED_FOR=true
#   POSTGRES_PASSWORD=<strong random password>
#   DATABASE_URL=postgresql+psycopg://jobpulse:<password>@postgres:5432/jobpulse

docker compose build
docker compose up -d
docker compose ps  # verify all healthy
```

### 5.4 Caddy Reverse Proxy (Automatic HTTPS)

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy -y
```

Create `/etc/caddy/Caddyfile`:
```caddy
roleradar.yourdomain.com {
    reverse_proxy 127.0.0.1:3000
}
```

```bash
sudo systemctl restart caddy
```

### 5.5 Systemd Auto-Restart

Create `/etc/systemd/system/roleradar.service`:
```ini
[Unit]
Description=RoleRadar Docker Compose Application
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/roleradar
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable roleradar
sudo systemctl start roleradar
```

---

## 6. Email Notifications (Resend)

> Email notifications are **disabled by default** in all deployment targets. No emails are sent and no false `sent` statuses are recorded until you configure Resend.

### 6.1 Setup

1. Create account at [resend.com](https://resend.com).
2. Verify your sending domain under **Domains**.
3. Create an API key under **API Keys**.
4. Set environment variables on your backend **and** worker services:

```env
EMAIL_PROVIDER=resend
RESEND_API_KEY=re_your_api_key_here
EMAIL_FROM=RoleRadar <notifications@yourdomain.com>
```

### 6.2 Verify Live Delivery

```bash
docker compose exec backend python /app/scripts/verify_resend.py --to your-email@example.com
```

### 6.3 Delivery Status Semantics

| Outbox Status | Meaning |
|---|---|
| `pending` | Queued, awaiting worker claim |
| `processing` | Worker has claimed and is attempting delivery |
| `sent` | Resend accepted; real `re_*` provider ID recorded |
| `cancelled` | Email provider is `disabled`; suppressed silently |
| `failed` | Transient error; will retry with exponential backoff |
| `permanently_failed` | Max attempts exceeded or permanent error (invalid email, auth failure) |

---

## 7. Database Migrations

Migrations run automatically on backend startup via `alembic upgrade head`.

Manual commands:
```bash
docker compose exec backend alembic current   # check revision
docker compose exec backend alembic history   # list all revisions
docker compose exec backend alembic upgrade head  # run pending migrations
docker compose exec backend alembic downgrade -1  # roll back one revision
```

Current schema: **10 migrations** (`0001_auth` → `0010_repair_notification_error_type`).

---

## 8. Database Backup & Restore

### 8.1 Backup

```bash
#!/bin/bash
BACKUP_DIR="/opt/backups/roleradar"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
mkdir -p "${BACKUP_DIR}"
docker compose exec -T postgres pg_dump -U jobpulse -d jobpulse -F c > "${BACKUP_DIR}/roleradar_${TIMESTAMP}.dump"
gzip -9 "${BACKUP_DIR}/roleradar_${TIMESTAMP}.dump"
find "${BACKUP_DIR}" -name "*.dump.gz" -mtime +14 -delete
echo "Backup: ${BACKUP_DIR}/roleradar_${TIMESTAMP}.dump.gz"
```

### 8.2 Restore

```bash
docker compose stop backend worker
gunzip -c /opt/backups/roleradar/roleradar_YYYYMMDD_HHMMSS.dump.gz | \
  docker compose exec -T postgres pg_restore -U jobpulse -d jobpulse --clean --if-exists
docker compose up -d
```

---

## 9. Operational Monitoring

```bash
# Live aggregated logs
docker compose logs -f --tail=100

# Worker monitoring cycles
docker compose logs -f worker | grep -E "ingestion|Monitoring source"

# Worker notification delivery
docker compose logs -f worker | grep -E "notification|delivered email"

# Backend errors
docker compose logs -f backend | grep -i error

# Health check
curl http://localhost:8000/api/health
```

---

## 10. Redeploy Procedure

### On Render
Push to your connected Git branch. Render auto-rebuilds and redeploys on each push to the default branch.

To trigger a manual redeploy: Render Dashboard → Service → **Manual Deploy** → **Deploy latest commit**.

### On Docker Compose (Local / VM)
```bash
git pull
docker compose build
docker compose up -d
docker compose exec backend alembic upgrade head
```

---

## 11. Known Limitations

| Item | Status | Notes |
|---|---|---|
| **Email delivery** | NOT VERIFIED live | Requires Resend API key + verified domain |
| **Public cloud deployment** | NOT DEPLOYED | Infrastructure blueprints exist; credentials required |
| **Browser-based job scraping** | Infrastructure only | Playwright installed; company-specific adapters not implemented |
| **Browserbase cloud browsers** | Optional | Set `BROWSER_PROVIDER=browserbase` with credentials |
| **Lever + Ashby adapters** | Fully implemented | Verified against 6 real companies (1,787 live jobs) |
| **Greenhouse adapter** | Fully implemented | Verified against Cloudflare (468) and Figma (145) |
