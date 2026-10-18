import { CloudSyncOutlined, EyeOutlined, FileExcelOutlined, PrinterOutlined, SafetyOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert, Button, Descriptions, Drawer, Empty, Input, message, Select, Space, Table, Tag, Typography, Upload,
} from 'antd';
import type { TableColumnsType, TablePaginationConfig } from 'antd';
import { useMemo, useState } from 'react';
import { api, printAgent } from '../api';
import { useAppStore } from '../store';
import type { Order } from '../types';

const platformMeta: Record<string, { label: string; color: string }> = {
  DOUYIN: { label: '抖音', color: 'magenta' },
  PINDUODUO: { label: '拼多多', color: 'red' },
  TAOBAO: { label: '淘宝/天猫', color: 'orange' },
  JD: { label: '京东', color: 'volcano' },
  CSV: { label: '文件导入', color: 'blue' },
};
const statusMeta: Record<string, { label: string; color: string }> = {
  PENDING_SHIPMENT: { label: '待发货', color: 'processing' },
  SHIPPED: { label: '已发货', color: 'success' },
  CANCELLED: { label: '已取消', color: 'default' },
  REFUNDED: { label: '已退款', color: 'error' },
};

export function OrdersPage() {
  const session = useAppStore((state) => state.session)!;
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [platform, setPlatform] = useState<string>();
  const [status, setStatus] = useState<string>();
  const [keyword, setKeyword] = useState('');
  const [selected, setSelected] = useState<React.Key[]>([]);
  const [detail, setDetail] = useState<Order | null>(null);
  const query = useMemo(() => {
    const value = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (platform) value.set('platform', platform);
    if (status) value.set('status', status);
    if (keyword) value.set('keyword', keyword);
    return value;
  }, [page, pageSize, platform, status, keyword]);
  const orders = useQuery({ queryKey: ['orders', query.toString()], queryFn: () => api.orders(session.token, query) });
  const printers = useQuery({ queryKey: ['printers'], queryFn: printAgent.printers, retry: false });
  const sync = useMutation({
    mutationFn: () => api.syncMock(session.token),
    onSuccess: (result) => {
      message.success(`同步完成：新增 ${result.created}，更新 ${result.updated}`);
      queryClient.invalidateQueries({ queryKey: ['orders'] });
    },
    onError: (error) => message.error(error.message),
  });
  const audit = useMutation({
    mutationFn: () => api.audit(session.token, selected as string[]),
    onSuccess: (result) => { message.success(`已审核 ${result.updated} 单，拦截 ${Object.keys(result.blocked).length} 单`); queryClient.invalidateQueries({ queryKey: ['orders'] }); },
    onError: (error) => message.error(error.message),
  });
  const print = useMutation({
    mutationFn: async () => {
      const printer = printers.data?.find((item) => item.is_default && item.is_online) ?? printers.data?.find((item) => item.is_online);
      if (!printer) throw new Error('没有可用的本机打印机');
      const prepared = await api.preparePrint(session.token, selected as string[], printer.name, ['WAYBILL', 'MANIFEST_A4', 'PRODUCT_LABEL']);
      for (const task of prepared.tasks) {
        const job = await printAgent.create({
          idempotency_key: task.idempotency_key,
          job_type: task.payload.job_type,
          printer_name: task.payload.printer_name,
          payload: task.payload,
        });
        await api.receipt(session.token, task.id, job);
      }
      return prepared;
    },
    onSuccess: (result) => {
      message.success(`已提交 ${result.tasks.length} 个任务，拦截 ${Object.keys(result.blocked).length} 单`);
      setSelected([]);
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      queryClient.invalidateQueries({ queryKey: ['print-jobs'] });
    },
    onError: (error) => message.error(error.message),
  });

  const columns: TableColumnsType<Order> = [
    { title: '平台', dataIndex: 'platform', width: 100, render: (value) => <Tag color={platformMeta[value]?.color}>{platformMeta[value]?.label ?? value}</Tag> },
    { title: '订单', width: 190, render: (_, row) => <div><Typography.Text strong>{row.erp_order_no}</Typography.Text><br /><Typography.Text type="secondary" copyable>{row.platform_order_no}</Typography.Text></div> },
    { title: '店铺', dataIndex: 'shop_name', width: 135 },
    { title: '商品', width: 260, render: (_, row) => <div><Typography.Text>{row.items[0]?.product_name}</Typography.Text><br /><Typography.Text type="secondary">{row.items[0]?.internal_sku ?? 'SKU 未映射'} · ×{row.items[0]?.quantity}</Typography.Text></div> },
    { title: '实付', dataIndex: 'paid_amount', width: 90, render: (value) => `¥${value}` },
    { title: '状态', dataIndex: 'status', width: 90, render: (value, row) => <Space direction="vertical" size={2}><Tag color={statusMeta[value]?.color}>{statusMeta[value]?.label ?? value}</Tag>{row.after_sale_status !== 'NONE' && <Tag color="error">退款中</Tag>}</Space> },
    { title: '审核/打印', width: 120, render: (_, row) => <Space direction="vertical" size={2}><Tag color={row.audit_status === 'APPROVED' ? 'success' : 'warning'}>{row.audit_status === 'APPROVED' ? '已审核' : '待审核'}</Tag><Tag>{row.print_status}</Tag>{row.print_blockers.length > 0 && <Tag color="error">{row.print_blockers[0]}</Tag>}</Space> },
    { title: '创建时间', dataIndex: 'created_at', width: 160, render: (value) => new Date(value).toLocaleString('zh-CN') },
    { title: '操作', fixed: 'right', width: 74, render: (_, row) => <Button type="link" icon={<EyeOutlined />} onClick={() => setDetail(row)}>详情</Button> },
  ];

  return (
    <div className="page-stack">
      <div className="page-heading"><div><Typography.Title level={3}>订单管理</Typography.Title><Typography.Text type="secondary">多平台统一视图 · 数据均来自 Mock 或文件导入</Typography.Text></div><Space><Upload accept=".csv,.xlsx" showUploadList={false} customRequest={async ({ file, onSuccess, onError }) => { try { const result = await api.importOrders(session.token, file as File); message.success(`导入 ${result.created} 个订单`); onSuccess?.(result); queryClient.invalidateQueries({ queryKey: ['orders'] }); } catch (error) { onError?.(error as Error); } }}><Button icon={<FileExcelOutlined />}>导入订单</Button></Upload><Button type="primary" icon={<CloudSyncOutlined />} loading={sync.isPending} onClick={() => sync.mutate()}>同步 1000 条模拟订单</Button></Space></div>
      <Alert type="info" showIcon message="真实平台尚未授权" description="抖音、拼多多、淘宝/天猫与京东当前只生成结构统一的模拟订单，不会向真实平台发送请求。" />
      <div className="filter-bar">
        <Input.Search allowClear placeholder="搜索订单号、商品或 SKU" onSearch={(value) => { setKeyword(value); setPage(1); }} style={{ width: 320 }} />
        <Select allowClear placeholder="全部平台" style={{ width: 150 }} value={platform} onChange={(value) => { setPlatform(value); setPage(1); }} options={Object.entries(platformMeta).slice(0, 4).map(([value, item]) => ({ value, label: item.label }))} />
        <Select allowClear placeholder="全部状态" style={{ width: 140 }} value={status} onChange={(value) => { setStatus(value); setPage(1); }} options={Object.entries(statusMeta).map(([value, item]) => ({ value, label: item.label }))} />
        <span className="filter-spacer" />
        <Typography.Text type="secondary">已选 {selected.length} 单</Typography.Text>
        <Button icon={<SafetyOutlined />} disabled={!selected.length} loading={audit.isPending} onClick={() => audit.mutate()}>批量审核</Button>
        <Button icon={<PrinterOutlined />} disabled={!selected.length || !printers.isSuccess} loading={print.isPending} onClick={() => print.mutate()}>加入打印队列</Button>
      </div>
      <Table<Order>
        rowKey="id" loading={orders.isLoading} columns={columns} dataSource={orders.data?.records}
        locale={{ emptyText: orders.isError ? <Empty description={`加载失败：${orders.error.message}`} /> : <Empty description="暂无订单，请同步模拟订单或导入文件" /> }}
        rowSelection={{ selectedRowKeys: selected, onChange: setSelected, preserveSelectedRowKeys: true }}
        scroll={{ x: 1350, y: 'calc(100vh - 370px)' }}
        pagination={{ current: page, pageSize, total: orders.data?.total, showSizeChanger: true, showTotal: (total) => `共 ${total} 单` }}
        onChange={(pagination: TablePaginationConfig) => { setPage(pagination.current ?? 1); setPageSize(pagination.pageSize ?? 20); }}
      />
      <Drawer title="订单详情" width={680} open={Boolean(detail)} onClose={() => setDetail(null)}>
        {detail && <Space direction="vertical" size={20} style={{ width: '100%' }}>
          <Descriptions bordered size="small" column={2} items={[
            { key: 'erp', label: 'ERP 订单号', children: detail.erp_order_no }, { key: 'platform', label: '平台', children: platformMeta[detail.platform]?.label },
            { key: 'shop', label: '店铺', children: detail.shop_name }, { key: 'warehouse', label: '仓库', children: detail.warehouse_name },
            { key: 'receiver', label: '收件人', children: detail.receiver_name }, { key: 'phone', label: '手机', children: detail.receiver_phone_masked },
            { key: 'address', label: '脱敏地址', children: detail.receiver_address_masked, span: 2 }, { key: 'remark', label: '备注', children: detail.remark || '—', span: 2 },
          ]} />
          <Table rowKey="id" size="small" pagination={false} dataSource={detail.items} columns={[
            { title: '商品', dataIndex: 'product_name' }, { title: '内部 SKU', dataIndex: 'internal_sku', render: (value) => value ?? <Tag color="error">未映射</Tag> },
            { title: '规格', dataIndex: 'specification' }, { title: '数量', dataIndex: 'quantity' },
          ]} />
        </Space>}
      </Drawer>
    </div>
  );
}

