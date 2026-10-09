# Verification

## Verified Baseline (2026-10-09)

The integrity repair was verified on Windows with **Python 3.12.10 and Node 22.23.1**. The backend suite contains 195 passing tests, including 58 new integrity regressions. The frontend has four passing behavior tests. Ruff lint and format checks, frontend lint, both real TypeScript projects and production build pass. `pip check` passes. Both Docker images build on the Linux Docker engine, and Compose validates without printing secrets.

The tests use temporary SQLite databases/directories, fake HTTP streams and mocked Pixiv clients. An autouse fixture isolates default runtime paths and rejects unmocked requests. No real Pixiv login/download, user scheduler or user's runtime database is needed.

## Commands

Windows installer runtime:

```bat
env\python\python.exe -m pip install -c requirements.lock -e ".[dev]"
env\python\python.exe -m ruff check .
env\python\python.exe -m ruff format --check .
env\python\python.exe -m pytest
env\python\python.exe -m pip check
```

For an independently created venv use `.venv\Scripts\python.exe` instead. See [Development](development.md).

```bat
cd frontend
npm ci
npm run lint
npm run test
npm run typecheck
npm run build
npm audit --omit=dev
```

`typecheck` checks application and configuration projects explicitly; `build` invokes it again before Vite. Keep strict checking enabled.

Sidecar checks (run shell syntax checking in Git Bash, WSL or Linux):

```text
cd auth-browser
npm ci
npm audit
node --check src/server.js
sh -n start.sh
```

Use `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` for dependency-only verification. The sidecar runs the system Chromium installed by its Dockerfile.

## Integrity Regression Coverage

`tests/test_integrity_regressions.py` exercises:

- Interrupted and cancelled streams, content-length mismatch, response closure, preservation of an existing file and retry of historic fragments.
- Candidate sources through chained filters, per-page retry, tag naming/skip behavior, limits, filtered gaps and multi-page restart recovery.
- Job/node association through activation, cancellation and recovery; concurrent progression; a crash during multi-artist job initialization; terminal failure/cancellation propagation; GET reads with no execution side effects.
- SQL/version rollback, repeated upgrade, original legacy sync/download/retry actions, retained filters/options and protection of later user edits.
- Read-only settings loads and concurrent merge, serializable validation errors, explicit null rejection and invalid timezone handling.
- Mid-run cancellation and persisted progress, cancellation through metadata boundaries and retry delays, stale cursor protection, real thread concurrency/shutdown, worker infrastructure recovery and atomic activation capacity.
- UTC compatibility, Tokyo daily/weekly/monthly schedules, both DST transitions, startup flags, trigger overlap/capacity, result-based success timestamps and preservation of dispatch errors.
- Health degradation and multipart size limits before parsing, including requests without Content-Length.

Frontend behavior tests cover the first settings request failing, selection retained across workflow polling, reset on a different workflow, job stream switching/stale events, updating actual jobs cache keys, and displaying the specific server validation reason.

### Advanced workflow editor follow-up (2026-10-09)

The editor uses one selected trigger for schedule hydration, draft initialization, change comparison, configuration merging and submission. An omitted or null trigger ID selects the first trigger in the definition's list; an explicit missing ID blocks saving and running. The editor displays the selected trigger ID and status. Switching triggers refreshes the draft and comparison baseline, and Reset restores the current selection.

Ordinary target/node edits send no trigger update, preserving every schedule, pause state, next-run time and other trigger. Explicit schedule edits write the displayed rule and retain the selected trigger's compatibility options and pause state. Rule-type changes remove old fields that the new rule does not use, including calendar time/timezone fields when switching to an interval. Interval timezones already stored as compatibility options remain intact on interval-only edits; the timezone input is shown only for daily, weekly and monthly rules.

`frontend/src/test/advancedWorkflowTriggers.test.tsx` adds 27 mocked behavior cases, including the WorkflowsPage entry point, different rules on multiple triggers, default/missing IDs, trigger switches/Reset, ordinary target/node edits, all 12 rule-type conversions, and Run + schedule with a paused trigger. Together with the existing target and state regressions, all 84 frontend tests pass. Frontend lint, both TypeScript projects and the production build are checked without starting the backend, accessing user runtime data or dispatching real workflows.

## Docker Checks

To build without starting any application/scheduler or attaching user volumes:

```text
docker compose config --quiet
docker build -t pixivdownloader-repair-check:local .
docker build -t pixivdownloader-auth-repair-check:local auth-browser
```

The sidecar startup guard was also tested in an isolated container with `--network none`, no bind mounts and no secrets; it exits before starting its browser. JavaScript/shell syntax checks pass. Full interactive Pixiv sign-in remains a separately authorized manual test.

## Health and Manual Checks

A live healthy `/api/health` returns HTTP 200 and:

```json
{
  "status": "ok",
  "version": "0.2.0",
  "executors": {"enabled": true, "queue": true, "scheduler": true}
}
```

A stopped or faulting enabled executor returns HTTP 503. Tests that explicitly disable executors report `enabled=false` and remain healthy.

Manual checks against a disposable environment should include settings errors, job progress/cancellation, filtered candidates, node selection while polling and timezone editing. Running a real Pixiv authentication/download or existing scheduled trigger requires the user's authorization. Do not use a user's runtime data for automated smoke tests.

## Dependency Audit

Frontend runtime audit (`npm audit --omit=dev`) and sidecar audit report zero vulnerabilities. Full frontend audit retains eight findings in the Tailwind 3 build chain (five high, three moderate). These findings are documented with reachability and upgrade tradeoffs in [Repair Report](repair-report.md#依赖审计与剩余事项); they are not suppressed or automatically fixed across major versions.
