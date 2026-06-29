# Infrastructure & DevOps

> **Goal:** Run the whole stack locally for $0, gate every change with CI, and have a clear,
> low-cost path to production — without over-building before launch.
> Parent: [master-plan.md](master-plan.md). Touches every other plan (it deploys them).

---

## 1. Local development (the default, $0)

One command — `docker-compose up` — brings up the full stack:
- **Postgres**, **Redis**, **MinIO** (local S3), **MLflow** (Postgres-backed, MinIO artifacts),
  the **FastAPI** app, a **Prefect worker**, the **live poller**, and the **Next.js** dev server.
- Config via `.env` (documented by `.env.example`); nothing leaves the laptop.

This is where ~all development happens. Cloud is only for public launch.

## 2. Containerization

- Multi-stage **Dockerfiles**: one for the Python package (run as api / worker / poller via the
  different entrypoints from [architecture.md §2](architecture.md)), one for the Next.js app.
- Same images run locally and in prod → no environment drift.

## 3. CI (GitHub Actions, every PR)

- **Backend:** `ruff` (lint/format), `mypy` (types), `pytest` (unit + data-validation + ML
  leakage/calibration + API tests) against an ephemeral Postgres service.
- **Frontend:** lint, type-check, `vitest`, `next build`, and an **OpenAPI codegen drift check**
  (regenerate the client and fail if it differs from what's committed — keeps frontend types
  honest against the API).
- **Images:** build (and on main, push) the Docker images.

## 4. CD / production path

**Phase A — cheap PaaS (recommended start, ~$15–40/mo):**
- API + worker + poller on **Render/Fly.io**; **Next.js on Vercel** (hobby = free).
- Managed **Postgres** + **Redis** add-ons; object storage on **Cloudflare R2** (no egress fees).
- Deploy on merge to `main`.

**Phase B — AWS (resume-direct target):**
- **ECS Fargate** tasks (api / worker / poller), **RDS** Postgres, **ElastiCache** Redis, **S3**,
  **EventBridge** for scheduled flows; MLflow on a small instance or container.
- Migrate when traffic/portfolio goals justify it (free tier softens year one).

**Scheduling in prod:** Prefect deployments run ingestion + retraining (the live poller is its own
always-on service, not a scheduled job).

## 5. Secrets & config

- Local: `.env` (gitignored). Prod: the platform's secret store (Render/Fly/Vercel env, or **AWS
  SSM Parameter Store / Secrets Manager**). Never commit secrets; `.env.example` documents keys.

## 6. Infrastructure-as-Code (§7 decision)

Terraform for the AWS target — either written now or deferred until the Phase-B migration.

## 7. Observability (§7 decision)

- Structured request/flow logging everywhere (baseline, always).
- Error tracking (Sentry free tier) + uptime check + basic timing metrics — scope per decision.

## 8. Cost recap
- **Dev:** $0 (all local).
- **Phase A prod:** ~$15–40/mo + ~$12/yr domain.
- **Phase B AWS:** ~$5–15/mo first year (free tier), then ~$25–50/mo.

---

## 9. Decisions
- **Observability (resolved 2026-06-28): Sentry free tier + structured logs.**
- **Deployment target (resolved 2026-06-28): PaaS-first** — design toward Render/Fly + Vercel +
  Cloudflare R2 (~$15–40/mo when launched); AWS (Phase B) is an optional later migration. Actual
  deploy is a roadmap milestone; dev stays $0.
- **Terraform (resolved 2026-06-28): deferred** until an actual cloud deploy (and mainly if/when
  migrating to AWS). PaaS is configured via platform manifests/dashboards, so no IaC needed for
  Phase A.

**Cost principle (clarified):** development is $0 (local); *any* 24/7 cloud hosting costs money,
and AWS in particular incurs non-free charges beyond the free tier (ALB ~$16/mo, NAT ~$32/mo,
Fargate not free-tier). Designing *toward* a target is free; cost begins only at the actual deploy
milestone. Terraform is free/open-source itself (only the resources it creates cost) and is most
relevant to the AWS path.

## 10. Build prompts (executable)

> **Prompt 1 — Local stack.** Author `docker-compose.yml` wiring Postgres, Redis, MinIO, MLflow,
> API, Prefect worker, live poller, and the Next.js dev server, with healthchecks and `.env`
> wiring. `docker-compose up` must yield a working `GET /health` and a reachable frontend.

> **Prompt 2 — Dockerfiles.** Multi-stage Dockerfile for the Python package (api/worker/poller
> entrypoints) and one for Next.js. Optimize layer caching; non-root runtime.

> **Prompt 3 — CI.** GitHub Actions workflow running the §3 backend + frontend gates (incl. the
> OpenAPI codegen drift check) on PRs, and building images on `main`.

> **Prompt 4 — Deploy config.** Per §7, configuration for the chosen target (PaaS service
> manifests + Vercel project, or AWS task/Terraform), with secrets wired via the platform store.

> **Prompt 5 — Observability.** Structured logging across API/flows/poller; integrate the chosen
> error tracker; add healthchecks/uptime + basic timing metrics.

> **Prompt 6 — Terraform (if chosen).** IaC for the AWS target (ECS, RDS, ElastiCache, S3,
> EventBridge, SSM) so the environment is reproducible.

## 11. Definition of done
- `docker-compose up` runs the entire stack locally; CI gates green on PRs.
- Images build reproducibly; chosen deploy target documented and runnable.
- Secrets sourced from a store, never committed; observability baseline in place.
