# Pulse — Project Plan

> **Pulse** is a service monitoring and incident management platform. It continuously monitors
> registered services, detects failures and degradation, creates and tracks incidents until
> recovery, keeps customers updated through a public status page, and surfaces reliability
> metrics to engineering and support teams.

---

# Evaluation of the Proposed Architecture with Additional Features and Add-ons

- Clear separation of the three backend engines (Monitoring, Incident, Notification) — each has a distinct lifecycle and can be developed/tested independently.
- React SPA for the internal dashboard plus a separate public status page is the right split: internal pages need auth, the status page needs to be public, fast, and cacheable.
- FastAPI is a good fit: async-native (important for a monitoring loop hitting many health endpoints concurrently), Pydantic models, built-in background tasks, easy WebSocket support.
- Data Model (core tables) users, services, incidents, timeline_events
---

## Component Breakdown

```
pulse/
├── backend/                  # FastAPI app
│   ├── app/
│   │   ├── main.py           # App factory, router registration, startup/shutdown
│   │   ├── config.py         # Settings (env-driven)
│   │   ├── database.py       # Engine, session, migrations
│   │   ├── models/           # SQLModel/SQLAlchemy models
│   │   ├── schemas/          # Pydantic request/response models
│   │   ├── routers/          # api routes: services, incidents, metrics, status, auth, subscribers, ws
│   │   ├── engines/
│   │   │   ├── monitor.py    # Monitoring engine (async check loop)
│   │   │   ├── incident.py   # Incident engine (state machine, timeline)
│   │   │   └── notifier.py   # Notification engine (webhooks, email stubs, subscribers)
│   │   └── services/         # Business logic shared by routers/engines
│   └── tests/
├── frontend/                 # React dashboard (Vite)
│   └── src/
│       ├── pages/            # Dashboard, Services, Incidents, Reliability, Settings
│       ├── components/
│       └── api/              # API client + websocket hooks
├── status/                   # Public status page (route of same React app or separate lightweight build)
└── docker-compose.yml        # Pulse + starter-kit services together
```

### Backend engines

#### 2.1 Monitoring Engine
- Async loop (per check interval, default 30s) that fans out health checks to all active services concurrently (`httpx.AsyncClient`).
- Check types: HTTP GET health endpoint (primary); optional expected status code, timeout (default ~5s), and keyword match.
- Result classification per check:
  - `up` — 2xx within timeout
  - `degraded` — 2xx but latency > threshold, OR intermittent failures
  - `down` — non-2xx, timeout, connection error
- Persists every check result (timestamp, service, status, latency ms, error detail).
- Applies **detection policy**: N consecutive `down` → declare outage; N consecutive `degraded` (or latency above threshold for a window) → declare degradation. N successes → recovery.
- Feeds state transitions to the Incident engine and publishes events on the WebSocket bus.

#### 2.2 Incident Engine
- Owns the incident state machine:
  - **Creation**: monitoring transition (auto) or manual (engineer files one).
  - **States**: `investigating → identified → monitoring → resolved` (timeline events record each transition + actor).
  - **Acknowledgement**: `acknowledged` boolean + ack timestamp + acked_by (support team workflow).
  - **Severity**: `outage` (service down) vs `degradation` (slow/flaky).
  - **Recovery**: monitoring reports sustained success → auto-resolve (or prompt engineer). Reopen if it re-breaks within cooldown; otherwise create a new linked incident.
  - **Flapping suppression**: don't open a new incident within X minutes of resolving a similar one — reopen instead.
- Maintains the incident **timeline**: opened, acked, status updates (human-written notes), auto-detected transitions, resolved — each with timestamp, actor (system/user), message.
- Notifies the Notification engine on every interesting event (created, status changed, resolved).

#### 2.3 Notification Engine
- **Channels**:
  - Webhook (POST incident payload to configured URLs — the starter-kit webhook receiver at `:9900` is the demo target).
  - Email stub / logging backend (pluggable `Notifier` interface so real SMTP/SMS can be added later).
- **Audiences**:
  - Engineers & support: incident created/updated/acked/resolved, routing rules by service.
  - Customers: public status page subscribers — notified on incident create/update/resolve for services (or global) they subscribe to.
- **Delivery rules**: event → template → channel fan-out; deduplication and rate limiting (don't send 50 emails for a flapping service).
- Persists a notification log (what was sent, to whom, when, channel, success/failure).

### Frontend pages (React + Vite)

| Page | Purpose |
| --- | --- |
| **Dashboard** | Overall system status grid, active incidents banner, live updates via WebSocket. |
| **Services** | List/register/edit services (name, URL, health path, interval, thresholds, team owner). Per-service: current status, uptime sparkline, recent checks. |
| **Incidents** | Active incident list + history. Incident detail: timeline, ack/resolve/annotate actions, linked service, severity. |
| **Reliability** | Uptime % (24h/7d/30d), latency trends, MTTR, incident counts per service, availability heat bars. |
| **Status (public)** | `/status` — current status of all services, active incidents with timeline, uptime summary, subscriber signup. No auth, no internal data. |
| **Settings** | Notification channels, subscribers, maintenance windows, user/team management (stretch). |

---

## 3. Data Model (core tables)

```
users            (id, email, name, role, password_hash)
services         (id, name, description, url, health_path, check_interval_s,
                  timeout_ms, degraded_latency_ms, failure_threshold,
                  team_owner, is_active, created_at)
check_results    (id, service_id, checked_at, status(up|degraded|down),
                  latency_ms, status_code, error)
incidents        (id, service_id, title, severity(outage|degradation),
                  state(investigating|identified|monitoring|resolved),
                  acknowledged, acked_by, acked_at,
                  opened_at, resolved_at, reopened_count, parent_incident_id)
timeline_events  (id, incident_id, at, actor(system|user:<id>),
                  kind(opened|acked|status_changed|note|auto_detected|resolved), message)
subscribers      (id, email, webhook_url, service_id nullable, unsubscribe_token)
notification_log (id, at, channel, audience, incident_id, event, status, detail)
maintenance_windows (id, service_id, starts_at, ends_at, reason)
```

---

## 4. API Design

Base: `/api` (internal, authenticated) and `/api/public` (status page, unauthenticated).

### Auth
| Method | Path | Description |
| --- | --- | --- |
| POST | `/api/auth/login` | Login, returns session token |
| POST | `/api/auth/logout` | Invalidate session |
| GET | `/api/auth/me` | Current user |

### Services
| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/services` | List services with current status |
| POST | `/api/services` | Register a service (name, url, health_path, interval, thresholds) |
| GET | `/api/services/{id}` | Service detail + latest check result |
| PATCH | `/api/services/{id}` | Update config / pause monitoring |
| DELETE | `/api/services/{id}` | Remove service |
| GET | `/api/services/{id}/checks?since=&limit=` | Recent check history |
| POST | `/api/services/{id}/check` | Trigger an immediate on-demand check |

### Incidents
| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/incidents?state=&service_id=&active=` | List/filter incidents |
| POST | `/api/incidents` | Manually open an incident |
| GET | `/api/incidents/{id}` | Detail incl. timeline |
| POST | `/api/incidents/{id}/ack` | Acknowledge (who, when) |
| POST | `/api/incidents/{id}/updates` | Add timeline note / status change (`identified`, `monitoring`, …) |
| POST | `/api/incidents/{id}/resolve` | Resolve with summary |
| GET | `/api/incidents/{id}/timeline` | Timeline events |

### Reliability metrics
| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/metrics/uptime?service_id=&window=24h\|7d\|30d` | Uptime % per service |
| GET | `/api/metrics/latency?service_id=&window=` | Latency percentiles/trend |
| GET | `/api/metrics/incidents?window=` | Incident counts, MTTR, per-service breakdown |

### Notifications & subscribers (internal)
| Method | Path | Description |
| --- | --- | --- |
| GET/POST/DELETE | `/api/channels` | Manage webhook/email channels |
| GET | `/api/notifications/log` | Delivery log |

### Public status page API (no auth)
| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/public/status` | Overall status + every service's current state and active incidents |
| GET | `/api/public/incidents` | Active + recent resolved incidents (sanitized) |
| GET | `/api/public/incidents/{id}` | Public incident detail + timeline |
| GET | `/api/public/uptime?window=` | 90-day uptime bars per service |
| POST | `/api/public/subscribe` | Subscribe email/webhook to updates |
| POST | `/api/public/unsubscribe` | Unsubscribe via token |

### Real-time
| Path | Description |
| --- | --- |
| WS `/api/ws` | Authenticated: check results, service status changes, incident events |
| WS/SSE `/api/public/ws` | Status page live updates (public, sanitized) |

---

## 5. Data Flow (happy path & incident path)

1. **Monitor loop** fires → checks all active services concurrently → stores `check_results`.
2. Consecutive-failure threshold crossed → Monitoring emits `service_down(service)` event.
3. **Incident engine** receives event → opens incident (`investigating`, severity `outage`), writes timeline event → emits `incident_created`.
4. **Notifier** fans out: engineer/support channels + customer subscribers + public status (state change is live on the page via WS).
5. Engineer acks and posts updates from the dashboard → timeline grows → status page reflects updates.
6. Service recovers → M consecutive successes → Incident engine resolves the incident (auto, with final timeline entry) → Notifier sends `resolved` to all audiences → metrics updated.

---

## 6. Build Phases

1. **Phase 1 — Foundation**: DB models, auth, services CRUD, public status API, basic React shell with Services page.
2. **Phase 2 — Monitoring engine**: async check loop, check-result storage, WebSocket feed, status derivation, dashboard grid.
3. **Phase 3 — Incident engine**: detection thresholds → incident creation, state machine, timeline, ack/resolve, Incidents UI.
4. **Phase 4 — Notification engine**: webhook channel (point at starter-kit receiver `:9900`), subscriber signup on status page, notification log.
5. **Phase 5 — Reliability metrics**: uptime/latency/MTTR computation, Reliability page.
6. **Phase 6 — Polish**: maintenance windows, flapping suppression tuning, docker-compose integration with the starter kit, end-to-end run of `incident-drill.sh`.

---

## 7. Risks & Decisions to Confirm

- **Deployment topology**: single FastAPI process with an asyncio background loop (simple, fine for this scale) vs. separate worker process (scale later). Start with the former.
- **DB choice**: SQLite for dev, Postgres-ready via SQLAlchemy — confirm target.
- **Auth scope**: full user management vs. simple single-user token for demo — confirm.
- **Email delivery**: real SMTP vs. logged stub for the evaluation — stub is likely sufficient; webhooks are the tested channel.
- **Status page hosting**: route in the same React app (`/status`) vs. separate build — same app is simpler; separate build isolates it better.
