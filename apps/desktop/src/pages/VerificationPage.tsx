import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Input, Select, Space, Table, Tag, Typography, message } from 'antd';
import { useState } from 'react';
import { api } from '../api';
import { useAppStore } from '../store';
import type { Shipment } from '../types';
import type { ShipmentItem } from '../types';

const statusMeta: Record<string, { label: string; color: string }> = {
  PICKING: { label: '待验货', color: 'warning' },
  VERIFIED: { label: '验货通过', color: 'blue' },
  SHIPPED: { label: '已出库', color: 'success' },
  CANCELLED: { label: '已取消', color: 'default' },
};

export function VerificationPage() {
  const session = useAppStore((state) => state.session)!;
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Shipment | null>(null);
  const [barcode, setBarcode] = useState('');
  const [scanType, setScanType] = useState<'ORDER' | 'SKU'>('ORDER');
  const [orderId, setOrderId] = useState('');
  const shipments = useQuery({ queryKey: ['shipments'], queryFn: () => api.shipments(session.token) });
  const orders = useQuery({
    queryKey: ['verification-orders'],
    queryFn: () => {
      const params = new URLSearchParams({ status: 'PENDING_SHIPMENT', page: '1', page_size: '50' });
      return api.orders(session.token, params);
    },
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['shipments'] });
    queryClient.invalidateQueries({ queryKey: ['orders'] });
  };
  const prepare = useMutation({
    mutationFn: () => api.prepareShipment(session.token, orderId),
    onSuccess: (result) => {
      message.success(`拣货任务 ${result.shipment_no} 已就绪`);
      setSelected(result);
      setOrderId('');
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });
  const scan = useMutation({
    mutationFn: (body: object) => api.scanShipment(session.token, selected!.id, body),
    onSuccess: (result) => {
      setSelected(result);
      setBarcode('');
      invalidate();
    },
    onError: (error: Error) => message.error(error.message),
  });
  const verify = useMutation({
    mutationFn: () => api.verifyShipment(session.token, selected!.id),
    onSuccess: (result) => { setSelected(result); message.success('验货确认通过'); invalidate(); },
    onError: (error: Error) => message.error(error.message),
  });
  const ship = useMutation({
    mutationFn: () => api.shipShipment(session.token, selected!.id),
    onSuccess: (result) => { setSelected(result); message.success('出库确认完成，库存已扣减'); invalidate(); },
    onError: (error: Error) => message.error(error.message),
  });

  return (
    <div className="page-stack">
      <div className="page-heading"><div><Typography.Title level={3}>扫码验货</Typography.Title><Typography.Text type="secondary">订单条码、SKU 条码、数量核验与确认出库</Typography.Text></div></div>
      <Alert type="info" showIcon message="打印成功不等于已经出库" description="只有扫码验货通过并执行出库确认后，才会扣减库存并生成库存流水。" />
      <div className="filter-bar">
        <Select showSearch allowClear placeholder="选择已审核待发货订单" style={{ width: 360 }} value={orderId || undefined}
          options={(orders.data?.records ?? []).filter((item) => item.warehouse_id).map((item) => ({ value: item.id, label: `${item.erp_order_no} · ${item.warehouse_name}` }))}
          onChange={(value) => setOrderId(value ?? '')}
          filterOption={(input, option) => String(option?.label ?? '').toLowerCase().includes(input.toLowerCase())}
        />
        <Button type="primary" loading={prepare.isPending} disabled={!orderId} onClick={() => prepare.mutate()}>创建拣货任务</Button>
      </div>
      <Card title="拣货与验货">
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Select style={{ width: 360 }} placeholder="选择拣货任务" value={selected?.id}
            options={(shipments.data ?? []).map((item) => ({ value: item.id, label: `${item.shipment_no} · ${statusMeta[item.status]?.label ?? item.status}` }))}
            onChange={(value) => setSelected((shipments.data ?? []).find((item) => item.id === value) ?? null)}
          />
          {selected && <Space wrap>
            <Tag color={statusMeta[selected.status]?.color}>{statusMeta[selected.status]?.label}</Tag>
            <Typography.Text>{selected.erp_order_no}</Typography.Text>
            <Typography.Text type="secondary">{selected.warehouse_name}</Typography.Text>
          </Space>}
          <Space.Compact style={{ width: '100%' }}>
            <Select style={{ width: 140 }} value={scanType} onChange={setScanType} options={[{ value: 'ORDER', label: '订单条码' }, { value: 'SKU', label: 'SKU 条码' }]} />
            <Input placeholder="扫描或输入条码后回车" value={barcode} onChange={(event) => setBarcode(event.target.value)}
              onPressEnter={() => selected && scanType === 'ORDER' ? scan.mutate({ scan_type: scanType, barcode }) : undefined}
              disabled={!selected || selected.status !== 'PICKING'}
            />
            <Button type="primary" disabled={!selected || !barcode || selected.status !== 'PICKING'} loading={scan.isPending} onClick={() => scan.mutate({ scan_type: scanType, barcode })}>扫码</Button>
          </Space.Compact>
          <Space>
            <Button disabled={!selected || selected.status !== 'PICKING'} loading={verify.isPending} onClick={() => verify.mutate()}>确认验货通过</Button>
            <Button type="primary" disabled={!selected || selected.status !== 'VERIFIED'} loading={ship.isPending} onClick={() => ship.mutate()}>确认出库</Button>
          </Space>
          {selected && <Table rowKey="id" size="small" pagination={false} dataSource={selected.items} columns={[
            { title: '商品', dataIndex: 'product_name' },
            { title: 'SKU', dataIndex: 'sku_code' },
            { title: '条码', dataIndex: 'barcode' },
            { title: '规格', dataIndex: 'specification' },
            { title: '应扫', dataIndex: 'expected_quantity' },
            { title: '已扫', dataIndex: 'verified_quantity' },
            { title: '结果', render: (_: unknown, row: ShipmentItem) => row.verified_quantity === row.expected_quantity ? <Tag color="success">完成</Tag> : <Tag color="warning">待扫</Tag> },
          ]} />}
        </Space>
      </Card>
      <Card title="出库记录">
        <Table rowKey="id" loading={shipments.isLoading} dataSource={(shipments.data ?? []).filter((item) => item.status === 'SHIPPED')} columns={[
          { title: '出库单', dataIndex: 'shipment_no' },
          { title: 'ERP 订单号', dataIndex: 'erp_order_no' },
          { title: '仓库', dataIndex: 'warehouse_name' },
          { title: '出库时间', dataIndex: 'shipped_at', render: (value: string | null) => value ? new Date(value).toLocaleString('zh-CN') : '—' },
          { title: '商品项', render: (_: unknown, row: Shipment) => row.items.length },
        ]} />
      </Card>
    </div>
  );
}
