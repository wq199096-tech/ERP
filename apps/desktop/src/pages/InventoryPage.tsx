import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App as AntdApp, Button, Card, Checkbox, Form, Input, Select, Space, Table, Tag, Typography } from 'antd';
import { useState } from 'react';
import { api } from '../api';
import { useAppStore } from '../store';
import type { InventoryBalance } from '../types';

export function InventoryPage() {
  const session = useAppStore((state) => state.session)!;
  const { message } = AntdApp.useApp();
  const queryClient = useQueryClient();
  const [warehouseId, setWarehouseId] = useState<string>();
  const [keyword, setKeyword] = useState('');
  const [lowStock, setLowStock] = useState(false);
  const [inboundForm] = Form.useForm();
  const [transferForm] = Form.useForm();
  const [stocktakeForm] = Form.useForm();
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: () => api.warehouses(session.token) });
  const inventory = useQuery({
    queryKey: ['inventory', warehouseId, keyword, lowStock],
    queryFn: () => {
      const params = new URLSearchParams();
      if (warehouseId) params.set('warehouse_id', warehouseId);
      if (keyword) params.set('keyword', keyword);
      if (lowStock) params.set('low_stock', 'true');
      return api.inventory(session.token, params);
    },
  });
  const movements = useQuery({
    queryKey: ['stock-movements', warehouseId],
    queryFn: () => {
      const params = new URLSearchParams();
      if (warehouseId) params.set('warehouse_id', warehouseId);
      return api.movements(session.token, params);
    },
  });
  const products = useQuery({ queryKey: ['products'], queryFn: () => api.products(session.token) });
  const allSkus = (products.data ?? []).flatMap((item) => item.skus);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['inventory'] });
    queryClient.invalidateQueries({ queryKey: ['stock-movements'] });
  };
  const inbound = useMutation({
    mutationFn: (body: object) => api.inventoryInbound(session.token, body),
    onSuccess: (result) => {
      message.success(`入库完成，当前在库 ${result.on_hand}`, 10);
      inboundForm.resetFields(['quantity', 'note']);
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });
  const transfer = useMutation({
    mutationFn: (body: object) => api.inventoryTransfer(session.token, body),
    onSuccess: (result) => {
      message.success(`调拨完成：源 ${result.source_on_hand}，目标 ${result.target_on_hand}`, 10);
      transferForm.resetFields(['quantity', 'note']);
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });
  const stocktake = useMutation({
    mutationFn: (body: object) => api.inventoryStocktake(session.token, body),
    onSuccess: (result) => {
      message.success(`盘点完成，当前在库 ${result.on_hand}`, 10);
      stocktakeForm.resetFields(['counted_quantity', 'note']);
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });

  const positiveInteger = { pattern: /^\d+$/, message: '数量必须是正整数' };

  const skuOptions = allSkus.map((item) => ({ value: item.id, label: `${item.sku_code} · ${item.product_name}` }));
  const warehouseOptions = warehouses.data?.map((item) => ({ value: item.id, label: `${item.code} · ${item.name}` })) ?? [];
  const columns = [
    { title: '仓库', render: (_: unknown, row: InventoryBalance) => `${row.warehouse_code} · ${row.warehouse_name}` },
    { title: '商品', dataIndex: 'product_name' },
    { title: 'SKU', dataIndex: 'sku_code' },
    { title: '规格', dataIndex: 'specification' },
    { title: '在库', dataIndex: 'on_hand' },
    { title: '预留', dataIndex: 'reserved' },
    { title: '可用', dataIndex: 'available' },
    { title: '预警', dataIndex: 'low_stock', render: (value: boolean) => value ? <Tag color="error">需补货</Tag> : <Tag color="success">正常</Tag> },
  ];

  return (
    <div className="page-stack">
      <div className="page-heading"><div><Typography.Title level={3}>仓库库存</Typography.Title><Typography.Text type="secondary">库存余额、预留、出入库、调拨与盘点</Typography.Text></div></div>
      <div className="filter-bar">
        <Select allowClear placeholder="全部仓库" style={{ width: 240 }} value={warehouseId} onChange={setWarehouseId} options={warehouseOptions} />
        <Input.Search allowClear placeholder="搜索商品、SKU 或条码" onSearch={setKeyword} style={{ width: 280 }} />
        <Checkbox checked={lowStock} onChange={(event) => setLowStock(event.target.checked)}>只看库存预警</Checkbox>
      </div>
      <Card title="库存余额">
        <Table rowKey="id" loading={inventory.isLoading} columns={columns} dataSource={inventory.data} pagination={{ pageSize: 20, showTotal: (total) => `共 ${total} 条` }} />
      </Card>
      <Card title="库存操作">
        <Space direction="vertical" size={20} style={{ width: '100%' }}>
          <Form form={inboundForm} layout="vertical" data-testid="inventory-inbound-form" onFinish={(values) => inbound.mutate(values)} initialValues={{ low_stock_threshold: 0 }}>
            <Space wrap align="start">
              <Form.Item name="warehouse_id" label="仓库" rules={[{ required: true, message: '请选择仓库' }]}><Select style={{ width: 220 }} options={warehouseOptions} /></Form.Item>
              <Form.Item name="sku_id" label="SKU" rules={[{ required: true, message: '请选择 SKU' }]}><Select style={{ width: 260 }} options={skuOptions} /></Form.Item>
              <Form.Item name="quantity" label="入库数量" rules={[{ required: true, message: '请输入入库数量' }, positiveInteger]}><Input type="number" min="1" style={{ width: 120 }} /></Form.Item>
              <Form.Item name="low_stock_threshold" label="预警阈值" rules={[{ pattern: /^\d+$/, message: '预警阈值必须是不小于 0 的整数' }]}><Input type="number" min="0" style={{ width: 120 }} /></Form.Item>
              <Form.Item name="note" label="备注" rules={[{ max: 500, message: '备注不能超过 500 个字符' }]}><Input style={{ width: 240 }} maxLength={500} /></Form.Item>
              <Form.Item><Button type="primary" htmlType="submit" loading={inbound.isPending}>入库</Button></Form.Item>
            </Space>
          </Form>
          <Form form={transferForm} layout="vertical" data-testid="inventory-transfer-form" onFinish={(values) => transfer.mutate(values)}>
            <Space wrap align="start">
              <Form.Item name="source_warehouse_id" label="源仓库" rules={[{ required: true, message: '请选择源仓库' }]}><Select style={{ width: 200 }} options={warehouseOptions} /></Form.Item>
              <Form.Item name="target_warehouse_id" label="目标仓库" dependencies={['source_warehouse_id']} rules={[
                { required: true, message: '请选择目标仓库' },
                ({ getFieldValue }) => ({
                  validator: (_, value) => value && value === getFieldValue('source_warehouse_id')
                    ? Promise.reject(new Error('目标仓库不能与源仓库相同'))
                    : Promise.resolve(),
                }),
              ]}><Select style={{ width: 200 }} options={warehouseOptions} /></Form.Item>
              <Form.Item name="sku_id" label="SKU" rules={[{ required: true, message: '请选择 SKU' }]}><Select style={{ width: 260 }} options={skuOptions} /></Form.Item>
              <Form.Item name="quantity" label="数量" rules={[{ required: true, message: '请输入调拨数量' }, positiveInteger]}><Input type="number" min="1" style={{ width: 120 }} /></Form.Item>
              <Form.Item name="note" label="备注" rules={[{ max: 500, message: '备注不能超过 500 个字符' }]}><Input style={{ width: 240 }} maxLength={500} /></Form.Item>
              <Form.Item><Button htmlType="submit" loading={transfer.isPending}>调拨</Button></Form.Item>
            </Space>
          </Form>
          <Form form={stocktakeForm} layout="vertical" data-testid="inventory-stocktake-form" onFinish={(values) => stocktake.mutate(values)}>
            <Space wrap align="start">
              <Form.Item name="warehouse_id" label="仓库" rules={[{ required: true, message: '请选择仓库' }]}><Select style={{ width: 220 }} options={warehouseOptions} /></Form.Item>
              <Form.Item name="sku_id" label="SKU" rules={[{ required: true, message: '请选择 SKU' }]}><Select style={{ width: 260 }} options={skuOptions} /></Form.Item>
              <Form.Item name="counted_quantity" label="实盘数量" rules={[{ required: true, message: '请输入实盘数量' }, { pattern: /^\d+$/, message: '实盘数量必须是不小于 0 的整数' }]}><Input type="number" min="0" style={{ width: 120 }} /></Form.Item>
              <Form.Item name="note" label="备注" rules={[{ max: 500, message: '备注不能超过 500 个字符' }]}><Input style={{ width: 240 }} maxLength={500} /></Form.Item>
              <Form.Item><Button htmlType="submit" loading={stocktake.isPending}>盘点调整</Button></Form.Item>
            </Space>
          </Form>
        </Space>
      </Card>
      <Card title="库存流水">
        <Table rowKey="id" loading={movements.isLoading} pagination={{ pageSize: 10 }} dataSource={movements.data} columns={[
          { title: '时间', dataIndex: 'created_at', render: (value: string) => new Date(value).toLocaleString('zh-CN') },
          { title: '类型', dataIndex: 'movement_type', render: (value: string) => <Tag color="blue">{value}</Tag> },
          { title: '数量', dataIndex: 'quantity', render: (value: number) => value > 0 ? `+${value}` : value },
          { title: '余额', dataIndex: 'balance_after' },
          { title: '订单', dataIndex: 'order_id' },
          { title: '备注', dataIndex: 'note' },
        ]} />
      </Card>
    </div>
  );
}
