import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App as AntdApp, Button, Card, Form, Input, Select, Space, Table, Tag, Typography } from 'antd';
import { useState } from 'react';
import { api } from '../api';
import type { Product } from '../types';
import { useAppStore } from '../store';

export function CatalogPage() {
  const session = useAppStore((state) => state.session)!;
  const { message } = AntdApp.useApp();
  const queryClient = useQueryClient();
  const [keyword, setKeyword] = useState('');
  const [form] = Form.useForm();
  const [skuForm] = Form.useForm();
  const [mappingForm] = Form.useForm();
  const [categoryForm] = Form.useForm();
  const products = useQuery({
    queryKey: ['products', keyword],
    queryFn: () => api.products(session.token, keyword),
  });
  const categories = useQuery({
    queryKey: ['product-categories'],
    queryFn: () => api.categories(session.token),
  });
  const shops = useQuery({ queryKey: ['shops'], queryFn: () => api.shops(session.token) });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['products'] });
    queryClient.invalidateQueries({ queryKey: ['product-categories'] });
    queryClient.invalidateQueries({ queryKey: ['inventory'] });
  };
  const createCategory = useMutation({
    mutationFn: (name: string) => api.createCategory(session.token, name),
    onSuccess: (result) => {
      message.success(`分类 ${result.name} 已创建`, 10);
      categoryForm.resetFields();
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });
  const createProduct = useMutation({
    mutationFn: (body: object) => api.createProduct(session.token, body),
    onSuccess: () => {
      message.success('商品档案已创建', 10);
      form.resetFields(['name', 'description']);
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });
  const createSku = useMutation({
    mutationFn: (body: object) => api.createSku(session.token, body),
    onSuccess: (result) => {
      message.success(`SKU ${result.sku_code} 已创建`, 10);
      skuForm.resetFields();
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });
  const createMapping = useMutation({
    mutationFn: (body: object) => api.createSkuMapping(session.token, body),
    onSuccess: () => {
      message.success('平台 SKU 映射已创建', 10);
      mappingForm.resetFields();
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });

  const allSkus = (products.data ?? []).flatMap((product) => product.skus);
  const columns = [
    { title: '商品名称', dataIndex: 'name', width: 220 },
    { title: '分类', dataIndex: 'category_id', render: (value: string | null) => categories.data?.find((item) => item.id === value)?.name ?? '—' },
    { title: 'SKU 数', render: (_: unknown, row: Product) => row.skus.length },
    { title: '状态', dataIndex: 'status', render: (value: string) => <Tag color={value === 'ACTIVE' ? 'success' : 'default'}>{value === 'ACTIVE' ? '在售' : value}</Tag> },
    { title: '描述', dataIndex: 'description', ellipsis: true },
  ];

  return (
    <div className="page-stack">
      <div className="page-heading"><div><Typography.Title level={3}>商品 SKU</Typography.Title><Typography.Text type="secondary">商品档案、多规格 SKU 与平台映射</Typography.Text></div></div>
      <div className="filter-bar">
        <Input.Search allowClear placeholder="搜索商品或内部 SKU" onSearch={setKeyword} style={{ width: 320 }} />
      </div>
      <Card title="商品与 SKU">
        <Table<Product> rowKey="id" loading={products.isLoading} columns={columns} dataSource={products.data}
          expandable={{ expandedRowRender: (row) => (
            <Table size="small" pagination={false} rowKey="id" dataSource={row.skus} columns={[
              { title: '内部 SKU', dataIndex: 'sku_code' },
              { title: '条码', dataIndex: 'barcode' },
              { title: '规格', dataIndex: 'specification' },
              { title: '采购价', dataIndex: 'purchase_price' },
              { title: '销售价', dataIndex: 'sale_price' },
              { title: '状态', dataIndex: 'status', render: (value: string) => <Tag color={value === 'ACTIVE' ? 'success' : 'default'}>{value}</Tag> },
            ]} />
          ) }}
        />
      </Card>
      <Card title="新建商品 / SKU / 平台映射">
        <Space direction="vertical" size={20} style={{ width: '100%' }}>
          <Form form={form} layout="vertical" data-testid="catalog-product-form" onFinish={(values) => createProduct.mutate(values)}>
            <Space wrap align="start">
              <Form.Item name="name" label="商品名称" rules={[
                { required: true, message: '请输入商品名称' },
                { whitespace: true, message: '商品名称不能为空' },
                { max: 255, message: '商品名称不能超过 255 个字符' },
              ]}><Input style={{ width: 260 }} maxLength={255} /></Form.Item>
              <Form.Item name="category_id" label="分类"><Select allowClear style={{ width: 180 }} options={categories.data?.map((item) => ({ value: item.id, label: item.name }))} /></Form.Item>
              <Form.Item name="description" label="描述"><Input style={{ width: 320 }} /></Form.Item>
              <Form.Item><Button type="primary" htmlType="submit" loading={createProduct.isPending}>创建商品</Button></Form.Item>
            </Space>
          </Form>
          <Form form={skuForm} layout="vertical" data-testid="catalog-sku-form" onFinish={(values) => createSku.mutate(values)}>
            <Space wrap align="start">
              <Form.Item name="product_id" label="商品" rules={[{ required: true }]}><Select style={{ width: 240 }} options={products.data?.map((item) => ({ value: item.id, label: item.name }))} /></Form.Item>
              <Form.Item name="sku_code" label="内部 SKU" rules={[
                { required: true, message: '请输入内部 SKU' },
                { whitespace: true, message: '内部 SKU 不能为空' },
                { max: 100, message: '内部 SKU 不能超过 100 个字符' },
                { pattern: /^[A-Za-z0-9][A-Za-z0-9._-]*$/, message: '内部 SKU 只能使用字母、数字、点、下划线和短横线' },
              ]}><Input style={{ width: 200 }} maxLength={100} /></Form.Item>
              <Form.Item name="barcode" label="条码" rules={[{ max: 80, message: '条码不能超过 80 个字符' }]}><Input style={{ width: 180 }} maxLength={80} /></Form.Item>
              <Form.Item name="specification" label="规格" rules={[{ max: 120, message: '规格不能超过 120 个字符' }]}><Input style={{ width: 180 }} maxLength={120} /></Form.Item>
              <Form.Item name="purchase_price" label="采购价" initialValue="0" rules={[
                { required: true, message: '请输入采购价' },
                { pattern: /^\d+(\.\d{1,2})?$/, message: '采购价必须是不小于 0 的金额' },
              ]}><Input type="number" min="0" step="0.01" style={{ width: 120 }} /></Form.Item>
              <Form.Item name="sale_price" label="销售价" initialValue="0" rules={[
                { required: true, message: '请输入销售价' },
                { pattern: /^\d+(\.\d{1,2})?$/, message: '销售价必须是不小于 0 的金额' },
              ]}><Input type="number" min="0" step="0.01" style={{ width: 120 }} /></Form.Item>
              <Form.Item><Button type="primary" htmlType="submit" loading={createSku.isPending}>创建 SKU</Button></Form.Item>
            </Space>
          </Form>
          <Form form={mappingForm} layout="vertical" data-testid="catalog-mapping-form" onFinish={(values) => createMapping.mutate(values)}>
            <Space wrap align="start">
              <Form.Item name="sku_id" label="内部 SKU" rules={[{ required: true }]}><Select style={{ width: 240 }} options={allSkus.map((item) => ({ value: item.id, label: `${item.sku_code} · ${item.product_name}` }))} /></Form.Item>
              <Form.Item name="shop_id" label="店铺" rules={[{ required: true }]}><Select style={{ width: 220 }} options={shops.data?.map((item) => ({ value: item.id, label: item.name }))} /></Form.Item>
              <Form.Item name="platform_sku" label="平台 SKU" rules={[
                { required: true, message: '请输入平台 SKU' },
                { whitespace: true, message: '平台 SKU 不能为空' },
                { max: 100, message: '平台 SKU 不能超过 100 个字符' },
              ]}><Input style={{ width: 240 }} maxLength={100} /></Form.Item>
              <Form.Item><Button htmlType="submit" loading={createMapping.isPending}>创建映射</Button></Form.Item>
            </Space>
          </Form>
          <Form form={categoryForm} layout="inline" data-testid="catalog-category-form" onFinish={(values) => createCategory.mutate(values.name)}>
            <Form.Item name="name" rules={[
              { required: true, message: '请输入商品分类' },
              { whitespace: true, message: '商品分类不能为空' },
              { max: 120, message: '商品分类不能超过 120 个字符' },
            ]}><Input placeholder="新建商品分类" maxLength={120} /></Form.Item>
            <Form.Item><Button htmlType="submit" loading={createCategory.isPending}>创建分类</Button></Form.Item>
          </Form>
        </Space>
      </Card>
    </div>
  );
}
