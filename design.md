# Pulse — Design Document

Pulse is a self-hosted **service monitoring and incident management platform**: it periodically
health-checks registered services, maintains a per-service health state machine, opens and manages
incidents automatically, notifies on-call engineers via webhooks, computes reliability metrics and
error budgets, and exposes a customer-facing public status page — plus an internal dashboard for
engineers.

---

## 1. Architecture overview

```
┌───────────────────────────────┐        ┌──────────────────────────────────────┐
│ Frontend (React 18 + Vite)    │  HTTP  │ Backend (FastAPI, async)             │
│  :5173                        │ ─────► │  :8000                               │
│                               │        │                                      │
│  TanStack Query (cache/poll)  │        │  routers/ ──► services, incidents,   │
│  AuthProvider (token)         │        │              metrics, public, auth,  │
│  client.js (single API seam)  │        │              channels, ops           │
└───────────────────────────────┘        │                                      │
                                         │  engines/                            │
         ┌─────────────────────────────┐ │    scheduler ──► checker             │
         │ PostgreSQL (pulse db)       │ │    notifier  (webhook fan-out)       │
         │  services (state machine)   │◄┤    checker   (fetch+classify+detect) │
         │  check_results              │ │                                      │
         │  incidents + timeline       │ │  state.py  (PURE state machine)      │
         │  notifications + channels   │ │  resilience.py (503/retry/buffer)    │
         │  users, subscribers, …      │ │                                      │
         └─────────────────────────────┘ │  deps (HMAC bearer auth)             │
                                         └──────────────┬───────────────────────┘
                                                        │ POST webhooks (retries)
                                                        ▼
                                          Webhook receivers (e.g. kit :9900)
```

Key principles:
- **One API seam** on the frontend (`client.js`): token injection, 401 handling, error normalization.
- **Pure logic separated from I/O**: `state.py` has zero I/O and is unit-testable; engines own I/O.
- **Resilience by default**: DB outages return clean 503s, checks buffer and flush, notification
  failures are recorded but never block the request path.
- **camelCase JSON + epoch-ms timestamps** across the whole wire contract.

---

## 2. Backend design

### 2.1 Stack
- FastAPI + SQLAlchemy 2.0 async + asyncpg + PostgreSQL 18.
- Pydantic v2 settings (`PULSE_DATABASE_URL`, `PULSE_AUTH_ENABLED`, `PULSE_CHECK_CONCURRENCY`).
- httpx for both health checks and webhook delivery.

### 2.2 Data model

| Table | Purpose / notable fields |
|---|---|
| `users` | email, name, role (admin/engineer/support), sha256 password_hash |
| `services` | name (unique), url, health_path, check_interval_sec, timeout_ms, degraded_latency_ms, failure_threshold, recovery_threshold, sla_target, is_active, **state** (pending/healthy/degraded/down), **consecutive_failures / consecutive_successes** (persisted so streaks survive restarts) |
| `check_results` | service_id, status (up/degraded/down), latency_ms, status_code, error, checked_at — every check persisted |
| `incidents` | service_id, title, severity (outage/degradation), state (investigating/identified/monitoring/resolved), acknowledged(+by/at), opened_at, resolved_at, reopened_count; **partial unique index**: one row per service where `resolved_at IS NULL` |
| `timeline_events` | incident_id, actor (system/user), actor_user_id, kind (opened/auto_detected/acked/status_changed/note/resolved), message |
| `notifications` | incident_id, channel, audience, event, status (pending/sent/failed), detail — the delivery history |
| `notification_channels` | webhook configs: name, url, optional service_id scope, is_active |
| `subscribers` | public status page email/webhook subscribers with unsubscribe tokens |
| `maintenance_windows` | reserved for scheduled-maintenance suppression |

Eight PG-native enums back the status/state columns.

### 2.3 State machine (`app/state.py`) — pure functions

**Classification** (`classify_response`):
| HTTP outcome | status |
|---|---|
| timeout / connection error / no response | down |
| non-2xx/3xx status code | down |
| 2xx/3xx with latency > `degraded_latency_ms` | degraded |
| 2xx/3xx fast | up |

**Transitions** (`next_service_state`) with F = failure_threshold, R = recovery_threshold:
- `up`: pending→healthy (first evidence of life); degraded/down→healthy only after **R consecutive** ups (an intervening failure resets the count)
- `degraded`: down state stays down (no downgrade); otherwise after F consecutive failures → degraded
- `down`: after F consecutive failures → down (degraded failures count toward the same streak, so `dg,dg,down → down`)

Flapping (failures interleaved with ups) never accumulates a streak — F exists to suppress that noise.

### 2.4 Monitoring scheduler (`app/engines/scheduler.py`)
- 1-second scheduling tick; each **active** service is an independent asyncio task.
- **Concurrency limit**: global `asyncio.Semaphore(PULSE_CHECK_CONCURRENCY=8)`.
- **No-overlap guard**: in-flight set — a due service whose previous check is still running is
  skipped this tick (tracked by counter).
- Next run scheduled at completion-time + that service's own interval.
- Service list re-read every tick → newly registered services are picked up automatically;
  deleted/paused ones stop.
- **DB-outage behavior**: results buffer in a bounded deque (5,000) and auto-flush on recovery;
  the loop never crashes (transient exceptions → 5s backoff).
- Per-service httpx timeout = `timeout_ms`.

### 2.5 Detection (`app/engines/checker.py`)
- **Streak** = all checks since the last `up` (queried via "latest up; everything after it") —
  streaks never bleed across a recovery boundary.
- **Trigger**: streak length ≥ failure_threshold.
- **Severity = worst-in-streak**: any `down` in the streak ⇒ outage; degraded-only ⇒ degradation.
  Guarantees:
  - a later degraded check can never downgrade an outage-level streak (`down,down,degraded → outage`)
  - an active **degradation** incident hit by a `down` check **escalates** to outage + timeline event
  - an active outage incident is never touched by later degraded checks
- Persisted counters mean streaks survive process restarts.

### 2.6 Incident lifecycle
- **Open**: at threshold, with `auto_detected` timeline event + queued notification.
- **Escalate**: degradation + down check (see above).
- **Ack / status updates / notes**: by authenticated users; every action appended to the timeline.
- **Auto-resolve**: once the state machine confirms HEALTHY (R consecutive ups), the active incident
  resolves with a "Sustained recovery observed" timeline event.
- **Reopen vs new**: a re-break within a **15-minute cooldown** (and < 3 reopen cycles) reopens the
  previous incident (resolved_at cleared, reopened_count++, REOPENED timeline event); later
  re-breaks create a fresh incident. Prevents both duplicate incidents for one ongoing outage and
  endlessly-reused incident records.

### 2.7 Notifications (`app/engines/notifier.py`)
- Events: `incident.created / acknowledged / updated / resolved / reopened / escalated`.
- One history row per event × channel (pending → sent/failed with HTTP status or error text).
- Delivery: fire-and-forget background task, **3 attempts with backoff (0.5s/1.5s/4s)**, 5s timeout.
- Channel matching: service-scoped channels only receive their service's events.
- Failures are recorded, never propagated — notifications can't break the API or the scheduler.

### 2.8 Resilience (`app/resilience.py`, `database.py`)
- Engine: 5s connect / 10s command timeouts, `pool_pre_ping`.
- Transient-error classification (includes raw `ConnectionRefusedError` from uvloop).
- `get_db` / `resilient_session` raise `DatabaseUnavailable` → global handler returns **503** with a
  clean JSON body (never a hang, never a 500).
- Startup bootstrap retries 5× with backoff; idempotent enum + column migrations for dev.

### 2.9 Auth
- HMAC-signed bearer tokens (`id:expires:hmac`), `PULSE_AUTH_ENABLED` toggle.
- `get_current_user` dependency on internal routers; `/api/public/*` and `/status` are open.
- Login: `POST /api/auth/login` → `{ token, user }`; wrong credentials → 401.
- Dev seeding: default admin created only if `users` is empty (`admin@pulse.dev / pulse123`).

---

## 3. API contract (camelCase, epoch-ms)

Internal (auth):
- `GET/POST /api/services`, `GET/PATCH/DELETE /api/services/{id}`
- `POST /api/services/{id}/check` (on-demand: classify, persist, advance state, detect)
- `GET /api/services/{id}/checks` (history)
- `GET /api/incidents?active=true|false`, `POST /api/incidents` (manual file, 409 if active exists)
- `GET /api/incidents/{id}` (detail + timeline + notes), `GET .../timeline`
- `POST /api/incidents/{id}/ack | updates | notes | resolve`
- `GET /api/metrics/uptime | latency | incidents | slo?window=24h|7d|30d`
- `GET/POST /api/channels`, `DELETE /api/channels/{id}`, `GET /api/channels/deliveries`
- `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`

Public (no auth): `GET /api/public/status`, `/api/public/incidents`, `/api/public/uptime`,
`POST /api/public/subscribe`, `GET /api/public/unsubscribe?token=…`

Ops: `GET /health` (liveness, no DB), `GET /health/db` (DB round-trip + table counts).

Error semantics: 401 unauthenticated, 404 unknown id, 409 conflicts (duplicate name, duplicate
active incident), 422 validation, **503 transient DB outage**, 500 unexpected (logged).

---

## 4. Frontend design

- **Stack**: React 18 + Vite, react-router v6, TanStack Query (staleTime 10s, retry 1), Recharts.
- **Structure**:
  - `api/client.js` — the only place that touches `fetch`; injects `Authorization`, normalizes
    errors, 401 → clear session + redirect to `/login`.
  - `api/hooks.js` — query hooks + mutation hooks with cache invalidation (mutation responses are
    summary-shaped, so the detail query is **invalidated**, never overwritten).
  - `auth/AuthContext.jsx` — login/logout, localStorage-persisted user + token.
  - `components/` — PageHeader, PageState (loading/error/retry), StatCard, Table, badges,
    LatencyChart, UptimeBars, Timeline, NotesSection, Modal, and the three flow modals
    (Register/Edit service, File incident).
- **Routes**: `/login`, `/` (Overview), `/services`, `/services/:id`, `/incidents`,
  `/incidents/:id`, `/notifications` — all protected; `/status` standalone and public.
- **Overview**: stat cards (total/operational/degraded/down/active incidents), service health list,
  active-incidents card, **SLO/error-budget table** with budget-remaining bars.
- **ServiceDetail**: state-machine status (stable, not the flickering latest check), "Run check now"
  with result feedback, edit/delete flow, latency chart, 90-day uptime bars, recent incidents.
- **IncidentDetail**: severity/state badges, ack/note/resolve actions, complete timeline,
  customer-communication message.
- **Public status**: overall banner, per-service rows (status, response time, 30-day uptime),
  90-day uptime bars, open incidents with customer messaging, and a guidance banner explaining
  "all green → likely your side; anything degraded/down → our side".
- **Notifications**: webhook delivery history with colored status badges and error detail.

---

## 5. Reliability guarantees (summary)

| Concern | Guarantee |
|---|---|
| Slow/hanging service | Never blocks other checks (independent tasks + timeout per service) |
| Overlapping checks | Impossible (in-flight set) |
| False alarms from one blip | Impossible (consecutive failure threshold) |
| Severity misclassification | Impossible (worst-in-streak; monotonic within a streak) |
| Severity downgrade | Impossible (outage stays outage) |
| Missed escalation | Handled (degradation + down → escalate + timeline event) |
| Flapping noise | Suppressed (thresholds + streak reset on up) |
| DB outage | API 503s cleanly; scheduler buffers and flushes; loop never dies |
| Webhook endpoint dead | Retried w/ backoff; failure recorded; nothing blocked |
| Restart mid-streak | Counters persisted → no phantom recovery |

---

## 6. Security posture (and limits)

- Bearer-token auth on all internal endpoints; public surface explicitly enumerated.
- Input validation via Pydantic (ranges enforced at the boundary); SQL via SQLAlchemy (no raw user
  input in SQL).
- CORS restricted to the frontend origin.
- **Limits**: sha256 passwords (dev-grade), stateless tokens (no revocation), no rate limiting on
  public endpoints, no HTTPS handling (assumed behind a proxy in production).

---

## 7. Testing strategy

- **Pure unit tests** for the state machine and classification (no DB needed).
- **Scenario harness** (`backend/scripts/detection-drill.sh`) driving real failure sequences
  (down/down/degraded, degraded→down, flapping, streak resets) through the live API.
- **Resilience drill** (`backend/scripts/db-resilience-drill.sh`): kill Postgres mid-run, verify
  503s, buffering, and recovery.
- **Browser E2E**: full flows via the in-app browser — login, register/edit/delete service,
  file/ack/resolve incident, delivery history, public status; console-error free.

## 8. Known limitations

See README ("Current limitations") and `progress.md` ("Remaining work"): Alembic, bcrypt, token
revocation, email/SMS channels, WebSockets, multi-worker scheduler, maintenance-window suppression,
status-page customization, on-call escalation policies.
