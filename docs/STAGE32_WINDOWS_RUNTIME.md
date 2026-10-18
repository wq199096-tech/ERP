# Stage 3.2 Windows runtime guide

## Components

Stage 3.2 has three processes:

1. **Backend API** - order import, audit, print task persistence and receipts.
2. **Print Agent** - local PDF rendering, Windows GDI printing and job history.
3. **Electron client** - desktop UI; browser mode intentionally cannot submit local print jobs.

Installing the desktop client alone is not the same as the complete ERP system being usable.
The packaged client still requires the backend and Print Agent on the local machine or a controlled
LAN host that the operator explicitly configures.

## Development startup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r services/api/requirements-dev.txt -r services/print-agent/requirements-dev.txt
pnpm install
```

Start the backend from `services/api`:

```powershell
.\..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Set `APP_ENV`, `JWT_SECRET`, `DATABASE_URL`, and `ENABLE_DEMO_DATA` before starting. Development
may use demo data. Production must use `APP_ENV=production`, a random `JWT_SECRET` of at least 32
characters, and `ENABLE_DEMO_DATA=false`.

Start Print Agent from `services/print-agent`:

```powershell
.\..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 17321
```

Set:

- `PRINT_AGENT_TOKEN`: at least 32 random characters; use the same value in the Electron process.
- `PRINT_AGENT_DB`: a local, backed-up SQLite path.
- `PRINT_AGENT_OUTPUT`: a local PDF output directory.
- `APP_ENV`: use production for commercial operation.

Start the desktop client from the repository root:

```powershell
$env:SMARTORDER_API_URL="http://127.0.0.1:8000/api/v1"
$env:SMARTORDER_PRINT_AGENT_URL="http://127.0.0.1:17321/api/v1"
$env:PRINT_AGENT_TOKEN="<same 32+ character random token>"
pnpm dev
```

For a packaged client, set these values before launching `智单 ERP.exe`. A packaged build refuses to
proxy print requests when the agent token is missing; it does not ship the development token.

## Production checks

1. Backend health must return `ok`.
2. Print Agent health must be reachable from the Electron main process only.
3. The Print Agent database and PDF output directory must be included in backup and restart recovery.
4. Confirm the target Windows printer is online and reports no paper/error state.
5. Print one 100 x 150 mm test waybill and one A4 manifest on actual paper before commercial use.

The statuses mean different things:

- `RENDERED`: a PDF was generated locally.
- `SUBMITTED`: Windows Spooler accepted a job; this is not proof of paper output.
- `PRINTED`: a device report or operator confirmed actual paper output.
- `UNKNOWN`: restart/queue state could not be confirmed; it requires human verification before retry.

Without access to real thermal/laser hardware and paper stock, thermal printer acceptance remains
pending. CI and automated tests validate the rendering and GDI submission path with mocks and PDF
extraction; they do not claim physical paper acceptance.
