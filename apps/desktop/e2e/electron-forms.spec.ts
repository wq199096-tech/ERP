import { _electron as electron, expect, test } from '@playwright/test';
import { DatabaseSync } from 'node:sqlite';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

test('real Electron forms submit catalog and inventory operations', async () => {
  test.setTimeout(180_000);
  const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  const apiDatabase = process.env.SMARTORDER_E2E_API_DB;
  if (!apiDatabase) throw new Error('SMARTORDER_E2E_API_DB 未由 Playwright 配置提供');
  const unique = Date.now();
  const categoryName = `E2E分类${unique}`;
  const productName = `E2E商品${unique}`;
  const skuCode = `E2E-SKU-${unique}`;
  const platformSku = `E2E-PLATFORM-${unique}`;
  const sourceCode = `WH-E2E-SRC-${unique}`;
  const sourceName = `E2E源仓${unique}`;
  const targetCode = `WH-E2E-${unique}`;
  const targetName = `E2E目标仓${unique}`;
  const inboundNote = `inbound-${unique}`;
  const transferNote = `transfer-${unique}`;
  const stocktakeNote = `stocktake-${unique}`;

  const app = await electron.launch({
    args: ['.'],
    cwd: desktopRoot,
    env: {
      ...process.env,
      SMARTORDER_RENDERER_URL: 'http://127.0.0.1:5173',
      SMARTORDER_API_URL: 'http://127.0.0.1:8000/api/v1',
      SMARTORDER_PRINT_AGENT_URL: 'http://127.0.0.1:17321/api/v1',
      SMARTORDER_FORCE_MOCK_PRINTER: 'true',
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

    const token = await page.evaluate(() => {
      const persisted = JSON.parse(localStorage.getItem('smartorder-session') ?? '{}');
      return persisted?.state?.session?.token;
    });
    expect(token).toBeTruthy();
    const authHeaders = { Authorization: `Bearer ${token}` };
    const sourceWarehouse = await page.request.post('http://127.0.0.1:8000/api/v1/warehouses', {
      headers: authHeaders,
      data: { code: sourceCode, name: sourceName, address: 'E2E 源仓地址', is_default: false },
    });
    expect(sourceWarehouse.ok()).toBeTruthy();
    const warehouseResponse = await page.request.post('http://127.0.0.1:8000/api/v1/warehouses', {
      headers: authHeaders,
      data: { code: targetCode, name: targetName, address: 'E2E 目标仓地址', is_default: false },
    });
    expect(warehouseResponse.ok()).toBeTruthy();

    await page.getByText('商品 SKU', { exact: true }).click();
    await expect(page.getByRole('heading', { name: '商品 SKU' })).toBeVisible();

    const categoryForm = page.getByTestId('catalog-category-form');
    await categoryForm.getByPlaceholder('新建商品分类').fill(categoryName);
    await categoryForm.getByRole('button', { name: '创建分类' }).click();
    await expect(page.getByText(`分类 ${categoryName} 已创建`)).toBeVisible();

    const productForm = page.getByTestId('catalog-product-form');
    await productForm.getByLabel('商品名称').fill(productName);
    await productForm.getByLabel('描述').fill('Electron 真实点击验收');
    await productForm.getByRole('button', { name: '创建商品' }).click();
    await expect(page.getByText('商品档案已创建')).toBeVisible();

    const skuForm = page.getByTestId('catalog-sku-form');
    await skuForm.locator('#product_id').click();
    await page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
      .locator('.ant-select-item-option', { hasText: productName }).first().click();
    await skuForm.locator('#sku_code').fill(skuCode);
    await skuForm.locator('#barcode').fill(`697${unique}`);
    await skuForm.locator('#specification').fill('E2E 规格');
    await skuForm.getByRole('button', { name: '创建 SKU' }).click();
    await expect(page.getByText(`SKU ${skuCode} 已创建`)).toBeVisible();

    const mappingForm = page.getByTestId('catalog-mapping-form');
    await mappingForm.locator('#sku_id').click();
    await page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
      .locator('.ant-select-item-option', { hasText: skuCode }).first().click();
    await mappingForm.locator('#shop_id').click();
    await page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
      .locator('.ant-select-item-option').first().click();
    await mappingForm.locator('#platform_sku').fill(platformSku);
    await mappingForm.getByRole('button', { name: '创建映射' }).click();
    await expect(page.getByText('平台 SKU 映射已创建')).toBeVisible();

    await page.getByText('仓库库存', { exact: true }).click();
    await expect(page.getByRole('heading', { name: '仓库库存' })).toBeVisible();

    const inboundForm = page.getByTestId('inventory-inbound-form');
    await inboundForm.getByRole('button', { name: /入\s*库/ }).click();
    await expect(page.getByText('请选择仓库')).toBeVisible();
    await inboundForm.locator('#warehouse_id').click();
    await page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
      .locator('.ant-select-item-option', { hasText: sourceCode }).first().click();
    await inboundForm.locator('#sku_id').click();
    await page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
      .locator('.ant-select-item-option', { hasText: skuCode }).first().click();
    await inboundForm.locator('#quantity').fill('7');
    await inboundForm.locator('#note').fill(inboundNote);
    await inboundForm.getByRole('button', { name: /入\s*库/ }).click();
    await expect(page.getByText('入库完成，当前在库 7')).toBeVisible();

    const transferForm = page.getByTestId('inventory-transfer-form');
    await transferForm.locator('#source_warehouse_id').click();
    await page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
      .locator('.ant-select-item-option', { hasText: sourceCode }).first().click();
    await transferForm.locator('#target_warehouse_id').click();
    await page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
      .locator('.ant-select-item-option', { hasText: targetCode }).first().click();
    await transferForm.locator('#sku_id').click();
    await page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
      .locator('.ant-select-item-option', { hasText: skuCode }).first().click();
    await transferForm.locator('#quantity').fill('2');
    await transferForm.locator('#note').fill(transferNote);
    await transferForm.getByRole('button', { name: /调\s*拨/ }).click();
    await expect(page.getByText('调拨完成：源 5，目标 2')).toBeVisible();

    const stocktakeForm = page.getByTestId('inventory-stocktake-form');
    await stocktakeForm.locator('#warehouse_id').click();
    await page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
      .locator('.ant-select-item-option', { hasText: sourceCode }).first().click();
    await stocktakeForm.locator('#sku_id').click();
    await page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last()
      .locator('.ant-select-item-option', { hasText: skuCode }).first().click();
    await stocktakeForm.locator('#counted_quantity').fill('20');
    await stocktakeForm.locator('#note').fill(stocktakeNote);
    await stocktakeForm.getByRole('button', { name: '盘点调整' }).click();
    await expect(page.getByText('盘点完成，当前在库 20')).toBeVisible();

    const db = new DatabaseSync(apiDatabase);
    try {
      const category = db.prepare('SELECT id FROM product_categories WHERE name = ?').get(categoryName);
      const product = db.prepare('SELECT id, description FROM products WHERE name = ?').get(productName) as { id: string; description: string } | undefined;
      const sku = db.prepare('SELECT id, barcode, specification FROM product_skus WHERE sku_code = ?').get(skuCode) as { id: string; barcode: string; specification: string } | undefined;
      const mapping = db.prepare('SELECT id FROM shop_sku_mappings WHERE platform_sku = ?').get(platformSku);
      expect(category).toBeTruthy();
      expect(product?.description).toBe('Electron 真实点击验收');
      expect(sku?.barcode).toBe(`697${unique}`);
      expect(sku?.specification).toBe('E2E 规格');
      expect(mapping).toBeTruthy();

      const movementCount = db.prepare(`
        SELECT movement_type, COUNT(*) AS count
        FROM stock_movements
        WHERE note IN (?, ?, ?)
        GROUP BY movement_type
      `).all(inboundNote, transferNote, stocktakeNote) as Array<{ movement_type: string; count: number }>;
      expect(Object.fromEntries(movementCount.map((row) => [row.movement_type, row.count]))).toEqual({
        INBOUND: 1,
        TRANSFER_OUT: 1,
        TRANSFER_IN: 1,
        STOCKTAKE: 1,
      });
      const balances = db.prepare(`
        SELECT w.code, b.on_hand
        FROM inventory_balances b
        JOIN warehouses w ON w.id = b.warehouse_id
        JOIN product_skus s ON s.id = b.sku_id
        WHERE s.sku_code = ? AND w.code IN (?, ?)
      `).all(skuCode, sourceCode, targetCode) as Array<{ code: string; on_hand: number }>;
      expect(Object.fromEntries(balances.map((row) => [row.code, row.on_hand]))).toEqual({
        [sourceCode]: 20,
        [targetCode]: 2,
      });
    } finally {
      db.close();
    }
  } finally {
    await app.close();
  }
});
