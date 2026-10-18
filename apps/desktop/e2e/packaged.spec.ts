import { _electron as electron, expect, test } from '@playwright/test';

test('packaged Electron uses secure IPC for API and Print Agent', async () => {
  test.skip(!process.env.SMARTORDER_PACKAGED_EXE, 'set SMARTORDER_PACKAGED_EXE after Windows build');
  const app = await electron.launch({
    executablePath: process.env.SMARTORDER_PACKAGED_EXE,
    env: {
      ...process.env,
      SMARTORDER_API_URL: 'http://127.0.0.1:8000/api/v1',
      SMARTORDER_PRINT_AGENT_URL: 'http://127.0.0.1:17321/api/v1',
      PRINT_AGENT_TOKEN: 'replace-with-local-agent-token',
    },
  });
  try {
    const page = await app.firstWindow();
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.getByRole('button', { name: '登录智单 ERP' }).click();
    await expect(page.getByRole('heading', { name: '经营首页' })).toBeVisible();
    await page.getByText('智能打单', { exact: true }).click();
    await expect(page.getByText(/Agent 已连接/)).toBeVisible();
  } finally {
    await app.close();
  }
});
