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

Ordinary target/node edits send no trigger update, preserving every schedule, pause state, next-run time and other trigger. Same-type schedule edits merge only changed fields into the original rule, retaining omitted fields, compatibility options and the selected trigger's pause state. Explicit rule-type changes produce a complete displayed rule and remove old fields that the new rule does not use, including calendar time/timezone fields when switching to an interval. Interval timezones already stored as compatibility options remain intact on interval-only edits; the timezone input is shown only for daily, weekly and monthly rules.

`frontend/src/test/advancedWorkflowTriggers.test.tsx` adds 27 mocked behavior cases, including the WorkflowsPage entry point, different rules on multiple triggers, default/missing IDs, trigger switches/Reset, ordinary target/node edits, all 12 rule-type conversions, and Run + schedule with a paused trigger. Together with the existing target and state regressions, all 84 frontend tests pass. Frontend lint, both TypeScript projects and the production build are checked without starting the backend, accessing user runtime data or dispatching real workflows.

### Existing schedule defaults (2026-10-09)

Existing schedules hydrate according to `backend/services/workflow_schedule_service.py`, independently of the defaults offered for new forms: an omitted interval count is 1, an omitted or unknown interval unit executes in days, calendar time defaults to 00:00, timezone defaults to UTC and monthly day defaults to 1. Numeric interval/monthly values use the backend's integer/fallback semantics; monthly values above 31 execute on the last day. Same-type edits preserve the original representations of all untouched values rather than normalizing historical rules.

Weekly rules with omitted, empty or wholly ineffective weekdays use the local weekday at the moment the backend computes the next run. The editor leaves every weekday unselected and explains this dynamic behavior. Choosing weekdays replaces only `days_of_week`; clearing every weekday explicitly selects the dynamic behavior. Reset and trigger switching restore both the original semantics and the comparison baseline. New forms still offer 6 hours, 03:00 and Monday/Wednesday/Friday. Explicit type switches use the displayed values to build a new rule, including when switching away and back; Reset cancels that conversion.

Run + schedule without schedule edits sends an empty `schedule_patch` for the selected trigger. The backend retains the original rule, including omitted fields and compatibility options. The unchanged scheduling behavior still recomputes `next_run_at` for Run + schedule; this change preserves the rule, not its previously calculated next-run timestamp. Rules whose type, time, timezone or numeric representation cannot safely be expressed and resubmitted show an alert and block saving/running. This includes time values rejected by the schedule API, timezones unavailable to the browser, unsafe numeric precision and non-ASCII interval/monthly numeric strings. Such rules remain untouched and require editing outside this editor.

The trigger test file contains 68 mocked cases covering implicit defaults, field-level merging, dynamic weekdays, conversions, new-form defaults and unsupported values. These checks use mocked API calls and do not start a backend or execute user schedules.

### Weekday JSON round trips (2026-10-09)

Python's scheduler ignores floating weekday values such as `1.0`, while a JavaScript JSON round trip turns them into integers. Workflow trigger responses now include `effective_days_of_week`, calculated from the stored Python values by the same helper used for execution. An empty list denotes the dynamic local-weekday behavior; null on a weekly rule means its semantics could not be interpreted safely. The editor and workflow list/detail summaries use this backend result instead of reinterpreting parsed numbers. Rules without this response field, including responses from older backends, block saving/running so that unsupported patch requests cannot silently replace a schedule with defaults.

Saving an existing trigger sends only `schedule_patch`; untouched schedule values are read from the database and never sent back through JavaScript. An empty patch preserves the entire rule, and editing time/timezone leaves even ignored floating weekdays intact. Explicit weekday edits replace that field with the chosen integer list. An explicit `type` in the patch creates the displayed new rule and clears inapplicable schedule fields while retaining compatibility options on the server. The API validates the merged rule and trigger ownership before writing; new triggers and older clients continue to use the supported full `schedule` request. The scheduler's execution semantics, stored rule format and historical records are unchanged; no migration is needed.

`frontend/src/test/advancedWorkflowWeekdays.test.tsx` exercises actual response parsing and request serialization for floating, mixed and Unicode weekdays, untouched rules, time edits, explicit weekday/type edits, target edits, Reset, trigger switches, older backend responses and workflow list/detail summaries. `tests/test_workflow_schedule_roundtrip.py` adds 30 API regressions, including 18 that pass actual GET responses through Node's JSON parser/stringifier and submit the resulting patches to the save endpoint. They check stored Python types, original schedule JSON, pause states, other triggers and next-run semantics. The Node-dependent cases skip when Node is unavailable. Tests use temporary databases with executors disabled and manual execution mocked; no user plan or real Pixiv operation runs.

The complete backend suite passes all 284 tests, including every Node round-trip case; all 142 frontend tests pass. Ruff lint/format checks for changed Python files, frontend lint, both TypeScript projects and the production build also pass.

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
