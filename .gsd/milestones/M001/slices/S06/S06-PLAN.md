# S06: Docker + CI/CD

**Goal:** Package the complete application into a production Docker image, create docker-compose configs for zero-config and secure deployment, and set up GitHub Actions CI/CD for lint/test on PR and build/push on tag.
**Demo:** `docker compose up` → app works at :8080 with zero config. Tag v0.1.0 → GitHub Actions builds multi-arch image → pushes to GHCR. PR triggers lint + test.

## Must-Haves

- Multi-stage Dockerfile: build frontend, install backend deps, minimal runtime image
- docker-compose.yml for zero-config startup
- docker-compose.example.yml with reverse proxy (Caddy) for TLS
- GitHub Actions: CI workflow (PR: lint + test), Release workflow (tag: build + push)
- Multi-arch support: amd64 + arm64
- Health check in Docker and compose
- Zero outbound telemetry verification

## Proof Level

- This slice proves: operational + final-assembly
- Real runtime required: yes (Docker build + run)
- Human/UAT required: yes (verify full flow in container)

## Verification

- `docker build -t media-rip .` — image builds successfully
- `docker compose up -d && curl localhost:8080/api/health` — returns healthy
- GitHub Actions workflow files pass `actionlint` (if available)
- Zero telemetry: container makes no outbound requests

## Tasks

- [x] **T01: Dockerfile + .dockerignore** `est:30m`
  - Why: The core deliverable — package everything into a production image.
  - Files: `Dockerfile`, `.dockerignore`
  - Do: Multi-stage build: (1) Node stage builds frontend, (2) Python stage installs backend deps, (3) Runtime stage copies built assets + installed packages. Use python:3.12-slim as base. Install yt-dlp + ffmpeg. Configure uvicorn entrypoint. Add HEALTHCHECK instruction.
  - Verify: `docker build -t media-rip .` succeeds
  - Done when: Image builds, contains frontend dist + backend + yt-dlp + ffmpeg

- [x] **T02: Docker Compose configs** `est:20m`
  - Why: Zero-config startup and secure deployment example.
  - Files: `docker-compose.yml`, `docker-compose.example.yml`
  - Do: Basic compose: single service, port 8080, /downloads and /themes volumes. Example compose: add Caddy sidecar with auto-TLS, admin enabled. Add .env.example with documented variables.
  - Verify: Compose file valid (docker compose config)
  - Done when: Both compose files parse correctly, volumes and ports mapped

- [x] **T03: GitHub Actions CI workflow** `est:20m`
  - Why: Automated quality gates on every PR.
  - Files: `.github/workflows/ci.yml`
  - Do: Trigger on PR to main. Jobs: backend lint (ruff) + test (pytest), frontend lint (vue-tsc) + test (vitest) + build. Use matrix for parallel execution. Cache pip and npm.
  - Verify: Workflow YAML is valid
  - Done when: CI workflow covers lint + test + build for both stacks

- [x] **T04: GitHub Actions Release workflow** `est:20m`
  - Why: Tag-triggered build and push to container registries.
  - Files: `.github/workflows/release.yml`
  - Do: Trigger on tag v*. Build multi-arch (amd64, arm64) via docker buildx. Push to GHCR. Create GitHub Release with auto-generated notes. Cache Docker layers.
  - Verify: Workflow YAML is valid
  - Done when: Release workflow builds and pushes on tag

- [x] **T05: Final integration + docs** `est:20m`
  - Why: Verify everything works end-to-end and document for operators.
  - Files: `README.md`
  - Do: Write README with quickstart, configuration, theme customization, admin setup, deployment. Verify Docker build. Run full test suites one final time.
  - Verify: All tests pass, Docker builds, README is complete
  - Done when: Project is ship-ready with documentation

## Files Likely Touched

- `Dockerfile`
- `.dockerignore`
- `docker-compose.yml`
- `docker-compose.example.yml`
- `.env.example`
- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`
- `README.md`
