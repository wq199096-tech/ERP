import { FilePdfOutlined, PrinterOutlined, RedoOutlined, WarningOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Col, Form, Input, message, Modal, Row, Select, Space, Table, Tag, Typography } from 'antd';
import { useState } from 'react';
import { api, printAgent, type JobVerification, type ManualRetryRequest } from '../api';
import { LabelDesigner, type LabelTemplate } from '../components/LabelDesigner';
import { useAppStore } from '../store';
import type { PrintJob } from '../types';

const TYPES = [
  { value: 'WAYBILL', label: '电子面单测试样张', description: '100 × 150 mm，带醒目测试水印', color: '#2366e8' },
  { value: 'MANIFEST_A4', label: '发货清单', description: 'A4 / A5 / 80 mm 可切换', color: '#12b76a' },
  { value: 'PRODUCT_LABEL', label: '商品标签', description: '60 × 40 mm，含条形码', color: '#f79009' },
];
const statusColors: Record<string, string> = { ACKNOWLEDGED: 'processing', FAILED: 'error', UNKNOWN: 'warning', CANCELLED: 'default', PRINTED: 'success', RENDERED: 'default', SUBMITTED: 'blue' };
const statusLabels: Record<string, string> = { ACKNOWLEDGED: '打印机已接收', FAILED: '失败', UNKNOWN: '状态未知', CANCELLED: '已取消', PRINTED: '已确认出纸', RENDERED: 'PDF 已生成', SUBMITTED: 'Spooler 已接收' };

export function PrintCenterPage() {
  const session = useAppStore((state) => state.session)!;
  const queryClient = useQueryClient();
  const [type, setType] = useState('WAYBILL');
  const [labelTemplate, setLabelTemplate] = useState<LabelTemplate>();
  const [form] = Form.useForm();
  const [verificationJob, setVerificationJob] = useState<PrintJob>();
  const [verificationInfo, setVerificationInfo] = useState<JobVerification>();
  const [operatorNote, setOperatorNote] = useState('');
  const printers = useQuery({ queryKey: ['printers'], queryFn: printAgent.printers, retry: false });
  const jobs = useQuery({ queryKey: ['print-jobs'], queryFn: printAgent.jobs, refetchInterval: 5000, retry: false });
  const buildTestPayload = (values: Record<string, string>) => ({
    data_source: 'MANUAL_TEST',
    server_task_id: `manual-${values.order_no}`,
    erp_order_no: values.order_no,
    order_version: 1,
    package_id: `MANUAL-${values.order_no}`,
    receiver_name: '本地测试收件人',
    receiver_phone: '138****0000',
    receiver_address: '测试样张地址，不用于寄件',
    warehouse_name: '本地测试仓',
    remark: values.remark || '',
    items: [{
      internal_sku: 'SO-TEST-SKU',
      product_name: values.product_name,
      specification: '测试规格',
      quantity: Number(values.quantity || 1),
      barcode: '6970000010011',
      copies: Number(values.quantity || 1),
    }],
  });
  const create = useMutation({
    mutationFn: (values: Record<string, string>) => {
      const jobType = type.startsWith('MANIFEST') ? (values.paper_size || type) : type;
      return printAgent.create({
        idempotency_key: `${jobType}-${values.order_no}`,
        job_type: jobType,
        printer_name: values.printer_name,
        payload: buildTestPayload(values),
        ...(jobType === 'PRODUCT_LABEL' && labelTemplate ? { label_template: labelTemplate } : {}),
      });
    },
    onSuccess: (job) => { message.success(`任务已创建，状态：${statusLabels[job.status] ?? job.status}`); queryClient.invalidateQueries({ queryKey: ['print-jobs'] }); },
    onError: (error) => message.error(`Print Agent 不可用：${error.message}`),
  });
  const openVerification = async (job: PrintJob) => {
    setVerificationJob(job);
    setVerificationInfo(undefined);
    setOperatorNote('');
    try {
      setVerificationInfo(await printAgent.verification(job.id));
    } catch (error) {
      message.error((error as Error).message);
    }
  };
  const retry = useMutation({
    mutationFn: async (input: { job: PrintJob; body?: ManualRetryRequest }) => {
      const retried = await printAgent.retry(input.job.id, input.body);
      const serverTaskId = input.job.payload?.server_task_id;
      if (typeof serverTaskId === 'string') await api.receipt(session.token, serverTaskId, retried);
      return retried;
    },
    onSuccess: () => {
      setVerificationJob(undefined);
      setVerificationInfo(undefined);
      queryClient.invalidateQueries({ queryKey: ['print-jobs'] });
    },
  });
  const preview = useMutation({
    mutationFn: async () => {
      const values = form.getFieldsValue();
      const jobType = type.startsWith('MANIFEST') ? (values.paper_size || type) : type;
      const blob = await printAgent.preview(jobType, {
        ...buildTestPayload(values),
        ...(jobType === 'PRODUCT_LABEL' && labelTemplate ? { label_template: labelTemplate } : {}),
      });
      window.open(URL.createObjectURL(blob), '_blank');
    },
    onError: (error) => message.error(error.message),
  });

  return (
    <div className="page-stack">
      <div className="page-heading"><div><Typography.Title level={3}>智能打单</Typography.Title><Typography.Text type="secondary">三类打印 · PDF 输出 · 失败重试 · 幂等保护</Typography.Text></div><Tag color={printers.isSuccess ? 'success' : 'error'}>{printers.isSuccess ? `Agent 已连接 · ${printers.data.length} 台打印机` : 'Agent 未连接'}</Tag></div>
      <Alert showIcon type="warning" icon={<WarningOutlined />} message="电子面单仅为测试样张" description="当前没有任何真实快递账户授权。测试运单号以 TEST- 开头，不可用于寄件；“已接收”也不代表纸张实际输出。" />
      <Row gutter={16}>
        {TYPES.map((item) => <Col span={8} key={item.value}><Card hoverable className={type === item.value ? 'type-card selected' : 'type-card'} onClick={() => setType(item.value)}><div className="type-icon" style={{ background: `${item.color}18`, color: item.color }}><PrinterOutlined /></div><Typography.Title level={4}>{item.label}</Typography.Title><Typography.Text type="secondary">{item.description}</Typography.Text></Card></Col>)}
      </Row>
      {type === 'PRODUCT_LABEL' && <LabelDesigner onChange={setLabelTemplate} />}
      <Card title={`创建${TYPES.find((item) => item.value === type)?.label}`} extra={<Button icon={<FilePdfOutlined />} loading={preview.isPending} onClick={() => preview.mutate()}>PDF 打印预览</Button>}>
        <Form form={form} layout="inline" initialValues={{ order_no: 'SO-DEMO-001', product_name: '304 不锈钢保温杯', quantity: '1', paper_size: 'MANIFEST_A4', printer_name: 'MockPrinter 智单测试打印机' }} onFinish={(values) => create.mutate(values)}>
          <Form.Item name="order_no" label="订单号" rules={[{ required: true }]}><Input style={{ width: 170 }} /></Form.Item>
          <Form.Item name="product_name" label="商品" rules={[{ required: true }]}><Input style={{ width: 210 }} /></Form.Item>
          <Form.Item name="quantity" label="数量"><Input style={{ width: 70 }} /></Form.Item>
          {type.startsWith('MANIFEST') && <Form.Item name="paper_size" label="纸张"><Select style={{ width: 130 }} options={[{ value: 'MANIFEST_A4', label: 'A4' }, { value: 'MANIFEST_A5', label: 'A5' }, { value: 'MANIFEST_80', label: '80 mm 热敏纸' }]} /></Form.Item>}
          <Form.Item name="printer_name" label="打印机" rules={[{ required: true }]}><Select style={{ width: 250 }} loading={printers.isLoading} options={(printers.data ?? [{ name: 'MockPrinter 智单测试打印机' }]).map((printer) => ({ value: printer.name, label: `${printer.name}${'is_online' in printer && !printer.is_online ? '（离线）' : ''}` }))} /></Form.Item>
          <Button type="primary" htmlType="submit" loading={create.isPending}>生成并提交</Button>
        </Form>
      </Card>
      <Card title="打印任务历史" extra={<Button onClick={() => jobs.refetch()}>刷新</Button>}>
        <Table<PrintJob> rowKey="id" loading={jobs.isLoading} dataSource={jobs.data} pagination={{ pageSize: 8 }} columns={[
          { title: '创建时间', dataIndex: 'created_at', width: 180, render: (value) => new Date(value).toLocaleString('zh-CN') },
          { title: '类型', dataIndex: 'job_type', width: 150, render: (value) => TYPES.find((item) => item.value === value)?.label ?? value },
          { title: '打印机', dataIndex: 'printer_name' },
          { title: '测试运单号', dataIndex: 'waybill_no', render: (value) => value ?? '—' },
          { title: '状态', dataIndex: 'status', width: 130, render: (value) => <Tag color={statusColors[value]}>{statusLabels[value] ?? value}</Tag> },
          { title: '说明', dataIndex: 'error_message', ellipsis: true },
          { title: '操作', width: 130, render: (_, row) => (
            <Space>
              {row.status === 'FAILED' && <Button type="link" icon={<RedoOutlined />} loading={retry.isPending} onClick={() => retry.mutate({ job: row })}>重试</Button>}
              {row.status === 'UNKNOWN' && <Button type="link" icon={<RedoOutlined />} onClick={() => openVerification(row)}>人工核验后重试</Button>}
            </Space>
          ) },
        ]} />
      </Card>
      <Modal
        open={Boolean(verificationJob)}
        title="人工核验未知打印状态"
        okText="确认后安全重试"
        cancelText="取消"
        okButtonProps={{ disabled: !verificationInfo || operatorNote.trim().length < 4, loading: retry.isPending }}
        onOk={() => verificationJob && verificationInfo && retry.mutate({
          job: verificationJob,
          body: {
            confirmed_waybill_no: verificationInfo.waybill_no || 'NO_WAYBILL',
            confirmed_spooler_status: verificationInfo.spooler_status.status,
            operator_name: session.userName,
            operator_note: operatorNote.trim(),
          },
        })}
        onCancel={() => setVerificationJob(undefined)}
      >
        {verificationInfo && (
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Typography.Text strong>必须先核对以下原始数据：</Typography.Text>
            <Typography.Paragraph>打印任务：{verificationInfo.job_id}</Typography.Paragraph>
            <Typography.Paragraph>ERP 订单号：{verificationInfo.erp_order_no ?? '—'}</Typography.Paragraph>
            <Typography.Paragraph>原运单号：{verificationInfo.waybill_no ?? '无运单'}</Typography.Paragraph>
            <Typography.Paragraph>Spooler Job：{verificationInfo.system_job_id ?? '无'}</Typography.Paragraph>
            <Typography.Paragraph>
              Spooler 状态：{verificationInfo.spooler_status.status} · {verificationInfo.spooler_status.message}
            </Typography.Paragraph>
            <Input.TextArea
              value={operatorNote}
              onChange={(event) => setOperatorNote(event.target.value)}
              placeholder="填写人工核对结论和依据，至少 4 个字符"
              rows={3}
            />
          </Space>
        )}
      </Modal>
    </div>
  );
}

