import { Alert, Button, Card, Col, Empty, Row, Space, Statistic, Table, Tag, Typography } from 'antd';

const moduleCopy: Record<string, { title: string; subtitle: string; stats: string[] }> = {
  batch: { title: '批量打印', subtitle: '按仓库与模板组织大批量打印任务', stats: ['等待 0', '处理中 0', '失败 0'] },
  verify: { title: '扫码验货', subtitle: '扫描订单、SKU 与包裹码，阻止错发漏发', stats: ['今日验货 0', '异常拦截 0', '待复核 0'] },
  logistics: { title: '快递物流', subtitle: '快递账户、运单与发货回传状态集中管理', stats: ['运输中 0', '揽收异常 0', '待回传 0'] },
  sku: { title: '商品 SKU', subtitle: '商品档案、多规格与平台 SKU 映射', stats: ['商品 5', 'SKU 5', '未映射 1'] },
  inventory: { title: '仓库库存', subtitle: '多仓库存、预留、流水与预警', stats: ['可用 12,680', '预留 386', '预警 3'] },
  purchase: { title: '采购管理', subtitle: '采购订单、供应商与缺货建议', stats: ['待采购 3', '在途 0', '本月入库 0'] },
  finance: { title: '财务利润', subtitle: '销售、成本、物流与利润经营分析', stats: ['今日销售 ¥0', '预计利润 ¥0', '异常成本 0'] },
  aftersale: { title: '售后管理', subtitle: '退款、退货入库、换货与售后记录', stats: ['退款中 0', '待退货 0', '待入库 0'] },
  ai: { title: 'AI 智能中心', subtitle: '确定性风险规则先行，建议不直接执行业务操作', stats: ['规则 8', '风险订单 17', '待处理 17'] },
  shops: { title: '店铺管理', subtitle: '管理平台店铺与授权能力状态', stats: ['模拟店铺 4', '正式授权 0', '待接入 4'] },
  printers: { title: '打印机管理', subtitle: 'Windows 队列、模板绑定与连接状态', stats: ['MockPrinter 1', '在线 1', '离线 0'] },
  settings: { title: '系统设置', subtitle: '企业、安全、通知与数据维护设置', stats: ['当前企业 1', '用户 1', '角色 1'] },
};

export function ModulePage({ moduleKey }: { moduleKey: string }) {
  const value = moduleCopy[moduleKey] ?? moduleCopy.settings;
  return <div className="page-stack">
    <div className="page-heading"><div><Typography.Title level={3}>{value.title}</Typography.Title><Typography.Text type="secondary">{value.subtitle}</Typography.Text></div><Button type="primary">新建</Button></div>
    {['finance', 'ai', 'shops'].includes(moduleKey) && <Alert showIcon type="info" message={moduleKey === 'finance' ? '经营分析不替代专业会计和报税系统' : moduleKey === 'ai' ? 'AI 不会直接修改库存、金额或发起真实发货' : '当前全部平台均为模拟能力，正式授权数为 0'} />}
    <Row gutter={16}>{value.stats.map((stat, index) => <Col span={8} key={stat}><Card><Statistic title={['总览', '处理中', '异常/待办'][index]} value={stat} /></Card></Col>)}</Row>
    <Card title="业务列表" extra={<Space><Tag>支持筛选</Tag><Tag>支持分页</Tag></Space>}>
      <Table pagination={false} dataSource={[]} columns={[{ title: '编号', dataIndex: 'id' }, { title: '名称', dataIndex: 'name' }, { title: '状态', dataIndex: 'status' }, { title: '更新时间', dataIndex: 'updated' }]} locale={{ emptyText: <Empty description="当前没有业务数据；模块流程与数据模型已预留，Stage 4 继续实现闭环" /> }} />
    </Card>
  </div>;
}

