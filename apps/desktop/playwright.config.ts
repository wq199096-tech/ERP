import { defineConfig } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const desktopRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(desktopRoot, '../..');
const python = process.env.SMARTORDER_TEST_PYTHON ?? 'python';
// 运行器（runner）与 worker 是两个进程，各自会重新求值本配置。
// 只有运行器设置的路径允许生效，worker 必须复用同一份数据库，否则 E2E 断言会读到空库。
const inheritedApiDatabase = process.env.SMARTORDER_E2E_API_DB;
const apiDatabase = inheritedApiDatabase ?? path.join(repoRoot, 'services/api', `e2e-api-${process.pid}.sqlite3`);
const runId = path.basename(apiDatabase).replace(/^e2e-api-/, '').replace(/\.sqlite3$/, '');
process.env.SMARTORDER_E2E_API_DB = apiDatabase;

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { baseURL: 'http://127.0.0.1:5173', trace: 'retain-on-failure' },
  webServer: [
    {
      command: `"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
      cwd: path.join(repoRoot, 'services/api'),
      url: 'http://127.0.0.1:8000/api/v1/health',
      env: { DATABASE_URL: `sqlite:///${apiDatabase.split(path.sep).join('/')}`, APP_ENV: 'development', ENABLE_DEMO_DATA: 'true' },
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: `"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 17321`,
      cwd: path.join(repoRoot, 'services/print-agent'),
      url: 'http://127.0.0.1:17321/docs',
      env: {
        PRINT_AGENT_DB: `./e2e-agent-${runId}.sqlite3`,
        PRINT_AGENT_OUTPUT: `./e2e-output-${runId}`,
        PRINT_AGENT_TOKEN: 'replace-with-local-agent-token',
      },
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: 'pnpm dev:web --host 127.0.0.1',
      cwd: desktopRoot,
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
