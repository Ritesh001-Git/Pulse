# Pulse — Completed Work

## Overview

Pulse has a React dashboard and a FastAPI backend connected to PostgreSQL. The work completed so far covers service monitoring, incident tracking, webhook delivery, reliability metrics, authentication, and a public status page.

## Planning and documentation

- Documented the initial architecture, API design, and implementation phases in `Plan.md`.
- Added `design.md` with an architecture and feature overview.
- Updated `README.md` with setup instructions, features, API information, and development credentials.
- Added a root `.gitignore` for local environment files, dependencies, build output, caches, and other generated files.

## Backend and database

- Created async FastAPI and SQLAlchemy integration with PostgreSQL.
- Added database models for users, services, health checks, incidents, timeline events, notifications, webhook channels, subscribers, and maintenance windows.
- Added development schema bootstrap, connection timeouts, transient-error handling, and database health endpoints.
- Added a database constraint limiting each service to one active incident.
- Implemented APIs for services, incidents, metrics, webhook channels, authentication, and public status data. API responses use camelCase fields and epoch-millisecond timestamps.

## Monitoring and service registration

- Implemented a scheduler that loads active services from the database and runs health checks using asyncio and httpx. It uses per-service intervals and timeouts and a configurable concurrency limit.
- Added an in-flight guard for scheduled checks and a bounded in-memory buffer for checks that cannot be saved immediately.
- Separated response classification and service-state transitions into `backend/app/state.py`.
- Implemented failure and recovery thresholds, latency-based degradation, and persistent state counters.
- Added worst-in-streak incident severity detection and escalation from degradation to outage.
- Connected the **Register Service** form to the backend, with validation, duplicate-name feedback, persistence, and scheduler pickup.
- Added service editing, a confirmation step for deletion, and an on-demand check action in the service detail page.

## Incidents and webhook notifications

- Added automatic incident detection, recovery-based resolution, and reopening of recently resolved incidents.
- Added manual incident filing, acknowledgement, status updates, notes, resolution, and timeline views.
- Implemented webhook channel configuration, delivery attempts with retries, and delivery-history records.
- Added a Notifications page for viewing delivery outcomes.

## Metrics and frontend

- Added uptime, latency percentile, incident count, MTTR, SLO, and error-budget endpoints based on database records.
- Built the Overview, Services, Service Detail, Incidents, Incident Detail, Notifications, Login, and Public Status pages using real backend data.
- Added login, bearer-token requests, protected dashboard routes, sign-out, loading and error states, charts, and status badges.
- Added SLO and error-budget information to the Overview page and a standalone public status page.

## Verification completed during development

- Ran state-transition and mixed-failure scenarios, including recovery thresholds, escalation, and flapping.
- Tested service registration, duplicate-name feedback, editing, deletion, and scheduler pickup through the browser.
- Tested login, protected-route redirects, incident actions, and public status rendering.
- Tested webhook delivery to the starter-kit receiver and retry/failure reporting for an unreachable endpoint.
- Ran a database-outage drill and a frontend production build during development.
