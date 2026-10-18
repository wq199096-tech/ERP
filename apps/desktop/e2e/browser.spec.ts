import { expect, test } from '@playwright/test';

test('browser login and real API order empty state', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: '登录智单 ERP' }).click();
  await expect(page.getByRole('heading', { name: '经营首页' })).toBeVisible();
  await page.getByText('订单管理', { exact: true }).click();
  await expect(page.getByRole('heading', { name: '订单管理' })).toBeVisible();
  await expect(page.getByText(/暂无订单|MOCK-/).first()).toBeVisible();
});
