import { AlertOutlined, ClockCircleOutlined, PrinterOutlined, ShoppingCartOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Alert, Card, Col, Empty, Row, Statistic, Tag, Typography } from 'antd';
import { api, printAgent } from '../api';
import { useAppStore } from '../store';

export function DashboardPage() {
  const session = useAppStore((state) => state.session)!;
  const summary = useQuery({ queryKey: ['dashboard'], queryFn: () => api.dashboard(session.token) });
  const agent = useQuery({ queryKey: ['agent-health'], queryFn: printAgent.health, retry: false });
  const data = summary.data;
  const printCount = Object.values(data?.print_jobs ?? {}).reduce((sum, value) => sum + value, 0);
  return (
    <div className="page-stack">
      <div className="page-heading">
        <div><Typography.Title level={3}>经营首页</Typography.Title><Typography.Text type="secondary">所有指标均来自当前企业实时 API</Typography.Text></div>
        <Tag color={agent.isSuccess ? 'success' : 'default'}>{agent.isSuccess ? 'Print Agent 在线' : 'Print Agent 未连接'}</Tag>
      </div>
      {summary.isError && <Alert type="error" showIcon message="实时经营数据加载失败" description={summary.error.message} />}
      {data && !data.has_data ? <Card><Empty description="暂无业务数据，请先导入或同步订单" /></Card> : <>
        <Row gutter={[16, 16]}>
          <Col span={6}><Card loading={summary.isLoading}><Statistic title="全部订单" value={data?.orders_total ?? 0} prefix={<ShoppingCartOutlined />} suffix="单" /></Card></Col>
          <Col span={6}><Card loading={summary.isLoading}><Statistic title="待发货" value={data?.pending_shipment ?? 0} prefix={<ClockCircleOutlined />} suffix="单" /></Card></Col>
          <Col span={6}><Card loading={summary.isLoading}><Statistic title="打印任务" value={printCount} prefix={<PrinterOutlined />} suffix="个" /><Typography.Text type="secondary">提交不等于实际出纸</Typography.Text></Card></Col>
          <Col span={6}><Card loading={summary.isLoading}><Statistic title="异常订单" value={data?.exception_orders ?? 0} prefix={<AlertOutlined />} suffix="单" valueStyle={{ color: '#d92d20' }} /></Card></Col>
        </Row>
        <Card title="实时状态">
          <Typography.Text>数据更新时间：{data?.generated_at ? new Date(data.generated_at).toLocaleString('zh-CN') : '加载中'}</Typography.Text>
          <br /><Typography.Text type="secondary">库存、采购、财务等后续 ERP 模块仍在开发中，本页不展示估算或演示指标。</Typography.Text>
        </Card>
      </>}
    </div>
  );
}
