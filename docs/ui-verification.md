# UI Verification Notes

Last updated: 2026-06-24

## Automated Checks

The integrated backend and frontend were verified with:

```bat
env\python.exe -m ruff format --check .
env\python.exe -m ruff check .
env\python.exe -m pytest
```

Frontend verification was run against the local `frontend\node_modules` tools with the bundled Codex Node runtime because `npm` is not available on this machine's PATH:

```bat
.\node_modules\.bin\eslint.CMD .
.\node_modules\.bin\tsc.CMD --noEmit
.\node_modules\.bin\vite.CMD build
```

## Manual Workflow Checklist

Use `run-webui.bat`, then verify these WebUI flows:

- Dashboard loads and shows recent job state.
- Settings loads masked refresh token state.
- Settings saves download path and request options.
- Settings `Test Auth` reports Pixiv authentication success or a clear token failure.
- Download creates a job from a Pixiv user ID.
- Download creates a job from an artwork ID.
- Active job progress and recent events update.
- Running or queued jobs can be cancelled.
- Failed files can be retried from the file retry action.
- Library lists artists after jobs discover them.
- Artist detail opens and lists artworks/files for the selected artist.
- Logs page shows recent job events without exposing the refresh token.

## Notes

No Pixiv network smoke test was run in this environment because it requires a real local refresh token and network access to Pixiv. Regression coverage uses faked Pixiv and file downloader boundaries for job creation, cancellation, failed downloads, settings masking, auth validation routing, migrations, repositories, and API behavior.
