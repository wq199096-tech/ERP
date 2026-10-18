import { _electron as electron, expect, test } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

test('real Electron window logs in, reads orders, sees printers and previews PDF', async () => {
  test.setTimeout(300_000);
  const app = await electron.launch({
    args: ['.'],
    cwd: path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..'),
    env: {
      ...process.env,
      SMARTORDER_RENDERER_URL: 'http://127.0.0.1:5173',
      SMARTORDER_API_URL: 'http://127.0.0.1:8000/api/v1',
      SMARTORDER_PRINT_AGENT_URL: 'http://127.0.0.1:17321/api/v1',
      PRINT_AGENT_TOKEN: 'replace-with-local-agent-token',
    },
  });
  try {
    const page = await app.firstWindow();
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await expect(page.getByRole('heading', { name: '智单 ERP', exact: true })).toBeVisible();
    await page.getByRole('button', { name: '登录智单 ERP' }).click();
    await expect(page.getByRole('heading', { name: '经营首页' })).toBeVisible();
    await page.getByText('订单管理', { exact: true }).click();
    await expect(page.getByRole('heading', { name: '订单管理' })).toBeVisible();
    await page.getByRole('button', { name: /同步 1000 条模拟订单/ }).click();
    await expect(page.getByText('共 1000 单')).toBeVisible({ timeout: 120_000 });
    await expect(page.locator('.ant-table-row')).toHaveCount(20, { timeout: 30_000 });
    await page.locator('.filter-bar .ant-select').nth(1).click();
    await page.getByText('待发货', { exact: true }).last().click();
    const validRows = page.locator('.ant-table-row').filter({ hasText: '订单尚未审核' });
    await expect(validRows.nth(9)).toBeVisible({ timeout: 30_000 });
    for (let index = 0; index < 10; index += 1) {
      await validRows.nth(index).getByRole('checkbox').click();
    }
    await page.getByRole('button', { name: /批量审核/ }).click();
    await expect(page.locator('.ant-table-row').filter({ hasText: '已审核' }).nth(9)).toBeVisible();
    await page.getByRole('button', { name: /加入打印队列/ }).click();
    await expect(page.locator('.ant-table-row').filter({ hasText: 'PROCESSING' }).nth(9)).toBeVisible({ timeout: 120_000 });
    await page.getByText('智能打单', { exact: true }).click();
    await expect(page.getByText(/Agent 已连接/)).toBeVisible();
    await page.getByRole('button', { name: /PDF 打印预览/ }).click();
    await expect(page.getByText(/生成预览失败/)).not.toBeVisible();
  } finally {
    await app.close();
  }
});
