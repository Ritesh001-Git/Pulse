# Pulse — Progress Log

Last updated: Nov 18, 2026

## Overall status: MVP complete, end-to-end verified ✅

The platform is fully functional as a self-hosted monitoring + incident management product:
scheduler running, incidents auto-detected and auto-resolved, webhook notifications delivered,
metrics/SLOs computed from real data, login + protected dashboard working, and all six pages
rendering real backend data with zero console errors.

---

## Completed

### Phase 0 — Planning
- [x] `plan.md`: architecture evaluation, component breakdown, API contract design.

### Phase 1 — Database & resilience
- [x] All models: User, Service, CheckResult, Incident, TimelineEvent, Notification,
      MaintenanceWindow, Subscriber, WebhookChannel.
- [x] PG-native enums (8 types) via `_pg_enum()` helper with `values_callable` (asyncpg quirk).
- [x] Partial unique index `uq_incidents_service_active` — one active incident per service.
- [x] Resilience layer (`app/resilience.py`): transient-error classification, retry helpers,
      `DatabaseUnavailable` → clean 503 mapping; 5s connect / 10s command timeouts; pool pre-ping.
- [x] DB failure drill verified live: 200 on `/health`, 503 on `/health/db` during outage,
      monitoring loop survives and buffers.
- [x] Dev bootstrap: `create_all_with_enums()` + idempotent `COLUMN_MIGRATIONS` + startup retry.

### Phase 2 — Backend APIs
- [x] Routers: services (CRUD + checks + on-demand check-now), incidents (full lifecycle),
      metrics (uptime/latency p50-p95/incidents+MTTR/SLO+error-budgets), public (status, incidents,
      uptime, subscribe/unsubscribe), auth (login/logout/me), ops (health/db-health), channels
      (webhook config + delivery history).
- [x] camelCase wire contract + epoch-ms timestamps (`app/serializers.py`, `app/schemas.py`).
- [x] HMAC bearer-token auth with `PULSE_AUTH_ENABLED` toggle; seeded admin.
- [x] CORS for the frontend; `email-validator` installed.

### Phase 3 — State machine & detection
- [x] `app/state.py`: pure, unit-tested state logic (19/19 tests pass):
      - classify: error/timeout/non-2xx-3xx → down; 2xx/3xx above degraded-latency → degraded; else up
      - transitions: threshold-based (failure_threshold, recovery_threshold), flapping suppressed,
        `down` never downgraded by `degraded`, recovery needs consecutive ups
- [x] Streak-based incident detection with **worst-in-streak severity**:
      - down,down,degraded → OUTAGE (degraded can't downgrade)
      - degraded streak + down → escalation + timeline event
      - streaks reset at `up` (no cross-recovery bleed)
- [x] Scenario harness (`backend/scripts/detection-drill.sh`): 6 scenarios, all PASS live.

### Phase 4 — Monitoring scheduler
- [x] `app/engines/scheduler.py`: per-service independent asyncio tasks, configurable global
      concurrency (semaphore), no-overlap guard (in-flight set), per-service interval/timeout
      respected, all results persisted, buffered during DB outage + auto-flush on recovery,
      service list re-read each tick (new services auto-monitored).
- [x] Live transition demo verified: healthy→down at threshold, down→healthy only after 2 ups,
      degraded escalation, degraded-during-down stays down.

### Phase 5 — Incident lifecycle & notifications
- [x] Auto-resolve after sustained recovery (recovery_threshold ups) + timeline event.
- [x] Reopen-vs-new: 15-min cooldown reopens the same incident (≤3 cycles); older re-breaks open new.
- [x] Complete timeline: auto_detected, acked, status_changed, note, resolved, reopened, escalated.
- [x] `app/engines/notifier.py`: webhook fan-out per lifecycle event (created/acknowledged/updated/
      resolved/reopened/escalated), 3 attempts with backoff (0.5/1.5/4s), 5s timeout, fire-and-forget
      (never blocks incident flow), per-event-per-channel history rows with outcome detail.
- [x] Channels API: CRUD + service-scoped channels + `GET /api/channels/deliveries`.
- [x] Live drill: kit receiver got every event (200 on attempt 1); dead endpoint retried → `failed`
      with detail; auto-resolve delivered; reopen delivered.

### Phase 6 — Frontend
- [x] All 6 pages (Overview, Services, ServiceDetail, Incidents, IncidentDetail, PublicStatus)
      + Login + Notifications; TanStack Query throughout; skeletons/error-retry everywhere.
- [x] Mock data fully removed; every page renders real backend data.
- [x] Auth: Login page, AuthProvider, Protected routes, token injection, 401 → auto sign-out
      + redirect, sidebar shows real user + sign-out.
- [x] SLO/error-budget table with bars on Overview; Notifications delivery-history page.
- [x] Status page guidance banner (our-side vs your-side), no auth, no internal data leak.

### Phase 7 — Integration hardening (final sweep)
- [x] **Register Service** complete flow: modal form, validation, POST, 409 surfacing, success
      screen, scheduler auto-pickup — all verified in the browser.
- [x] **File Incident** modal wired and verified.
- [x] ServiceDetail "Run check now" (result badge) and "Edit" (full edit modal) functional.
- [x] Rename-to-duplicate → clean 409 (was 500). Delete with two-step confirmation via UI.
- [x] Owner null → "—"; subtitle "undefined" fix.
- [x] Edge case: unreachable service → state machine degrades correctly, exactly one incident,
      no crashes, no spam.
- [x] Zero console errors across all pages; production build passes.
- [x] `backend/requirements.txt` (pinned); README rewritten with setup, features, credentials,
      limitations.

---

## Remaining work (not started)

- [ ] Email/SMS notification channels (models exist, not wired).
- [ ] WebSocket/live updates (dashboard currently polls at 10s stale time).
- [ ] Maintenance windows (pause detection during scheduled maintenance).
- [ ] Status-page customization (custom domain, theming, per-service public messages editing).