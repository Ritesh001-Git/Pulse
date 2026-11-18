# Pulse — Service Monitoring & Incident Management

Pulse is a self-hosted service monitoring and incident management platform. It health-checks your
services on a schedule, tracks a healthy/degraded/down state machine per service, opens and manages
incidents automatically, fans out webhook notifications, and serves a public status page — with an
internal dashboard for your on-call engineers.

Built with **FastAPI + SQLAlchemy (async) + PostgreSQL** on the backend and **React 18 + Vite +
TanStack Query + Recharts** on the frontend.

---

## Features

### Monitoring engine
- **Per-service scheduler** (`asyncio` + `httpx`): every service is checked independently on its own
  configured interval — one slow service never blocks others.
- **Configurable global concurrency** (`PULSE_CHECK_CONCURRENCY`, default 8) and **no overlapping
  checks** per service (in-flight set).
- **Every check result persisted** to Postgres; during a DB outage results buffer in memory and
  auto-flush on recovery (the loop never crashes).
- **State machine** (pure, unit-tested logic in `app/state.py`):
  - `healthy → degraded/down` only after `failure_threshold` **consecutive** failures — a single
    failed request never raises an alarm.
  - Classification: error/timeout/non-2xx-3xx → `down`; 2xx/3xx slower than `degraded_latency_ms` →
    `degraded`; otherwise `up`.
  - `down` is never downgraded by a later `degraded` check.
  - Recovery requires `recovery_threshold` **consecutive** successes.

### Incident management
- **Streak-based detection with worst-in-streak severity**: incidents open at the failure threshold;
  any `down` in the streak ⇒ *outage*, degraded-only streaks ⇒ *degradation* (a degraded check can
  never downgrade an outage-level streak, and a `down` during an active degradation **escalates** it
  with a timeline event).
- **Auto-resolve** after sustained recovery (recovery threshold), with timeline events.
- **Reopen vs new**: a re-break within a 15-minute cooldown reopens the previous incident (up to 3
  cycles); older re-breaks create a fresh incident.
- **Complete timeline**: auto-detected, acknowledged, status changes, notes, escalations, reopens,
  resolutions. Manual incident filing, ack, notes, and resolution from the UI.
- One active incident per service enforced by a partial unique index.

### Notifications
- **Webhook fan-out** per incident lifecycle event: `incident.created / acknowledged / updated /
  resolved / reopened / escalated`.
- **Retries with backoff** (3 attempts: 0.5s/1.5s/4s, 5s timeout) — a dead endpoint never blocks
  anything and its failure is recorded.
- **Delivery history** for every event × channel (`/notifications` page, `GET /api/channels/deliveries`).
- Channel config CRUD (`/api/channels`), including service-scoped channels.

### Metrics & SLOs
- Uptime %, latency **p50/p95** (Postgres `percentile_cont`), incident counts and **MTTR** — all
  computed from real check/incident records.
- **SLO compliance + error budgets** per service (SLA target per service; budget = allowed downtime
  minutes for the window; degraded checks count at half weight).
- Visualized on the Overview page with budget-remaining bars.

### Auth
- Session login (email + password) with HMAC-signed bearer tokens.
- Protected dashboard routes, 401 → automatic sign-out and redirect. The public status page needs no
  auth and leaks no internal data.

### Public status page (`/status`)
- Live overall banner (all systems operational / degraded / partial outage), per-service status with
  response time and 30-day uptime, 90-day uptime bars, open incidents with customer messaging, and
  a guidance banner helping users tell "our side" from "your side" problems.
- Email/webhook subscription with unsubscribe tokens.

---

## Quick start

### Prerequisites
- Python 3.12+, Node 18+
- PostgreSQL (any recent version)
- Docker (only for the optional demo kit)

### 1. Database

```bash
createdb pulse          # or: psql -c "CREATE DATABASE pulse OWNER <you>;"
```

### 2. Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # or: fastapi uvicorn sqlalchemy[asyncio] asyncpg pydantic-settings httpx email-validator
cp .env.example .env                        # if absent, create .env with the vars below
```

`.env`:
```
PULSE_DATABASE_URL=postgresql+asyncpg://pulse:pulse@localhost:5432/pulse
PULSE_AUTH_ENABLED=true
PULSE_CHECK_CONCURRENCY=8
```
(Adjust the DB URL to your user/password. On startup the app creates enums/tables automatically and
seeds a default admin if the `users` table is empty.)

```bash
.venv/bin/uvicorn app.main:app --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173  (API default: http://localhost:8000)
```

### Demo credentials

| Email             | Password   | Role  |
|-------------------|------------|-------|
| `admin@pulse.dev` | `pulse123` | admin |

> The seed admin is only created when no user exists. Change the password / swap sha256 for bcrypt
> before any real deployment.

### 4. Optional: demo services

The `pulse-starter-kit/` directory ships four mock services (quotes/payments/claims/notifications on
ports 7001–7004) plus a webhook receiver on 9900:

```bash
cd pulse-starter-kit && docker compose up --build
```

Then register them in the UI (**Services → + Register service**, e.g.
`http://localhost:7001` + health path `/health`) or via `POST /api/services`. Each mock service has
fault-injection control endpoints (`POST /control/down`, `/control/slow?ms=1500`, `/control/flaky?rate=0.5`,
`/control/reset`) — perfect for demos of detection, degradation, escalation, and recovery.

---

## API overview

Internal (auth required): `/api/services` (CRUD + `POST /{id}/check` for on-demand checks),
`/api/incidents` (list/detail/ack/updates/notes/resolve/timeline),
`/api/metrics/uptime|latency|incidents|slo`, `/api/channels` (+ `/deliveries`),
`/api/auth/login|logout|me`.

Public (no auth): `/api/public/status`, `/api/public/incidents`, `/api/public/uptime`,
`/api/public/subscribe`, `/api/public/unsubscribe`.

Health: `GET /health` (liveness, no DB), `GET /health/db` (DB round-trip + table counts).
JSON uses camelCase keys and epoch-millisecond timestamps. On a transient DB outage, internal
endpoints return a clean **503** instead of hanging or crashing.

---

## Testing scripts

- `backend/scripts/detection-drill.sh` — drives real failure sequences (down/down/degraded,
  flapping, streak resets) through the API against the kit and asserts incident severity logic.
- `backend/scripts/db-resilience-drill.sh` — kills Postgres mid-run and verifies 503 responses,
  buffered checks, and recovery.

## Architecture notes

- `backend/app/state.py` — pure state-machine logic (no I/O), unit-testable.
- `backend/app/engines/checker.py` — HTTP fetch, classification, persistence, detection.
- `backend/app/engines/scheduler.py` — the monitoring loop (concurrency, overlap guard, buffering).
- `backend/app/engines/notifier.py` — webhook delivery with retries + history.
- `backend/app/resilience.py` — transient-error classification, retry helpers, 503 mapping.
- `frontend/src/api/client.js` — single API seam (token injection, 401 handling).

## Current limitations

- Passwords are **sha256-hashed** (dev-grade) — use bcrypt/argon2 before real use.
- Schema bootstrap is dev-grade (`create_all` + idempotent ALTERs); no Alembic migrations yet.
- Notifications support **webhook** channels only (email/SMS models exist but aren't wired).
- Auth tokens are stateless (no revocation/blocklist); logout is client-side.
- No WebSocket/live updates — the dashboard polls (TanStack Query, 10s stale time).
- The error-budget model counts each failed check as one interval of downtime (interval
  approximation), which slightly under-estimates downtime between checks.
- Single-process scheduler: running multiple uvicorn workers would duplicate checks (use 1 worker).
