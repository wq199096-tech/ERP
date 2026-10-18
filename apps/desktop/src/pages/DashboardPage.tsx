import {
  AlertOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  PrinterOutlined,
  RiseOutlined,
  ShoppingCartOutlined,
} from '@ant-design/icons';
import { Card, Col, Progress, Row, Space, Statistic, Table, Tag, Typography } from 'antd';

const activity = [
  { key: 1, time: '10:42', event: '抖音旗舰店增量同步完成', result: '新增 36 单', status: '成功' },
  { key: 2, time: '10:38', event: '批次 PK20261017008 提交打印', result: '48 个任务', status: '已接收' },
  { key: 3, time: '10:31', event: '库存预警规则执行', result: '3 个 SKU 低库存', status: '需处理' },
];

export function DashboardPage() {
  return (
    <div className="page-stack">
      <div className="page-heading">
        <div><Typography.Title level={3}>经营首页</Typography.Title><Typography.Text type="secondary">今天是 2026 年 10 月 17 日，仓库正在稳定履约</Typography.Text></div>
      </div>
      <Row gutter={[16, 16]}>
        <Col span={6}><Card><Statistic title="今日订单" value={1268} prefix={<ShoppingCartOutlined />} suffix="单" /><span className="positive"><RiseOutlined /> 较昨日 12.8%</span></Card></Col>
        <Col span={6}><Card><Statistic title="待发货" value={386} prefix={<ClockCircleOutlined />} suffix="单" /><Typography.Text type="secondary">其中 42 单即将超时</Typography.Text></Card></Col>
        <Col span={6}><Card><Statistic title="打印已接收" value={829} prefix={<PrinterOutlined />} suffix="个" /><Typography.Text type="secondary">实际出纸以人工/硬件回执为准</Typography.Text></Card></Col>
        <Col span={6}><Card><Statistic title="异常订单" value={17} prefix={<AlertOutlined />} suffix="单" valueStyle={{ color: '#d92d20' }} /><Typography.Text type="secondary">退款、地址变化或 SKU 未映射</Typography.Text></Card></Col>
      </Row>
      <Row gutter={16}>
        <Col span={16}>
          <Card title="履约进度" extra={<Tag color="blue">杭州一号仓</Tag>}>
            <Row gutter={24}>
              <Col span={8}><Progress type="dashboard" percent={82} strokeColor="#2366e8" /><div className="progress-label">订单审核</div></Col>
              <Col span={8}><Progress type="dashboard" percent={67} strokeColor="#12b76a" /><div className="progress-label">拣货完成</div></Col>
              <Col span={8}><Progress type="dashboard" percent={54} strokeColor="#f79009" /><div className="progress-label">扫码出库</div></Col>
            </Row>
          </Card>
        </Col>
        <Col span={8}>
          <Card title="风险提醒">
            <Space direction="vertical" size={16}>
              <div><Tag color="error">高</Tag> 5 个订单收货地址发生变化</div>
              <div><Tag color="warning">中</Tag> 3 个 SKU 预计 2 天内缺货</div>
              <div><Tag color="processing">提示</Tag> 拼多多店铺仅为模拟能力</div>
              <div><CheckCircleOutlined className="positive" /> Print Agent 最近心跳正常</div>
            </Space>
          </Card>
        </Col>
      </Row>
      <Card title="最近业务动态">
        <Table pagination={false} dataSource={activity} columns={[
          { title: '时间', dataIndex: 'time', width: 100 },
          { title: '事件', dataIndex: 'event' },
          { title: '结果', dataIndex: 'result' },
          { title: '状态', dataIndex: 'status', render: (value) => <Tag>{value}</Tag> },
        ]} />
      </Card>
    </div>
  );
}

