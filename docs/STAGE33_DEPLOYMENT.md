# Stage 3.3 deployment and operations

## 1. System boundary

The Windows installer contains only the desktop client. A complete deployment also requires:

- the backend API on `127.0.0.1:8000` or an explicitly configured controlled host;
- Print Agent on the operator workstation at `127.0.0.1:17321`;
- PostgreSQL for production data;
- the same random Print Agent token supplied to both Print Agent and the desktop process.

The installer opening successfully is **not** proof that the complete ERP system is usable. The
packaged client performs startup health checks and shows a clear error when either service is
unavailable.

## 2. Production backend

Create an isolated PostgreSQL database (for example `smartorder_erp`) and a dedicated least-privilege
account. Do not use the CI test database. Initialize the schema once:

```powershell
cd services/api
..\\..\\.venv\\Scripts\\python.exe -c "from app.database import Base, engine; import app.models; Base.metadata.create_all(engine)"
```

Start the backend:

```powershell
$env:APP_ENV="production"
$env:ENABLE_DEMO_DATA="false"
$env:DATABASE_URL="postgresql+psycopg://smartorder:<random-password>@127.0.0.1:5432/smartorder_erp"
$env:JWT_SECRET="<at-least-32-random-characters>"
$env:CREDENTIAL_ENCRYPTION_KEY="<Fernet-key>"
..\\..\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Health endpoint: `GET http://127.0.0.1:8000/api/v1/health`. It performs a database `SELECT 1` and
returns HTTP 503 when the database is unavailable.

## 3. Print Agent

Run Print Agent on the same workstation as the physical printer:

```powershell
cd services/print-agent
$env:APP_ENV="production"
$env:PRINT_AGENT_TOKEN="<at-least-32-random-characters>"
$env:PRINT_AGENT_DB="D:\\SmartOrderData\\print-agent.sqlite3"
$env:PRINT_AGENT_OUTPUT="D:\\SmartOrderData\\print-output"
..\\..\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 17321
```

It accepts only loopback requests and requires bearer-token authorization. On startup it marks
non-final jobs:

- `CREATED`, `QUEUED`, and `RENDERED` without a Spooler job ID as `FAILED` (safe to retry);
- `SUBMITTED`, or any job with a Spooler job ID, as `UNKNOWN`;
- it automatically queries Windows for `UNKNOWN` jobs, but never automatically resubmits them.

## 4. Desktop client

After installing `SmartOrder-ERP-0.1.0-x64.exe`, launch the client with:

```powershell
$env:SMARTORDER_API_URL="http://127.0.0.1:8000/api/v1"
$env:SMARTORDER_PRINT_AGENT_URL="http://127.0.0.1:17321/api/v1"
$env:PRINT_AGENT_TOKEN="<same 32+ character random token>"
& "C:\\Program Files\\SmartOrder ERP\\智单 ERP.exe"
```

Never set `SMARTORDER_FORCE_MOCK_PRINTER=true` in production. That value is reserved for automated
tests and forces the in-process mock printer.

## 5. Print acceptance

Use the following operational meanings:

- `RENDERED`: PDF generated; no printer submission claim.
- `SUBMITTED`: Windows accepted a Spooler job; not proof of paper output.
- `PRINTED`: device report or trained operator confirmed paper output.
- `FAILED`: submission/rendering failed; retry may be safe.
- `UNKNOWN`: must be human-verified. The UI requires the original job, waybill and Spooler status to
  be shown and requires an audit note before resubmission.

Automated tests cover 100 x 150 mm and A4 DEVMODE values with a mock GDI device. Physical thermal
printer, A4 printer, paper-out, offline, and hardware cancellation acceptance remain **pending until
tested with real hardware**.
