import {
  AppstoreOutlined, BarcodeOutlined, BellOutlined, CarOutlined, DashboardOutlined,
  DollarOutlined, InboxOutlined, LogoutOutlined, MenuFoldOutlined, MenuUnfoldOutlined,
  PrinterOutlined, ProductOutlined, RobotOutlined, ScanOutlined, SearchOutlined,
  SettingOutlined, ShopOutlined, ShoppingCartOutlined, SwapOutlined, SyncOutlined,
  TeamOutlined, UserOutlined,
} from '@ant-design/icons';
import { Avatar, Badge, Dropdown, Input, Layout, Menu, Select, Space, Tag, Tooltip, Typography } from 'antd';
import { useState } from 'react';
import { useAppStore } from '../store';
import { DashboardPage } from '../pages/DashboardPage';
import { ModulePage } from '../pages/ModulePage';
import { OrdersPage } from '../pages/OrdersPage';
import { PrintCenterPage } from '../pages/PrintCenterPage';

const { Header, Sider, Content } = Layout;
const menu = [
  { key: 'dashboard', icon: <DashboardOutlined />, label: '经营首页' },
  { key: 'orders', icon: <ShoppingCartOutlined />, label: '订单管理' },
  { key: 'printing', icon: <PrinterOutlined />, label: '智能打单' },
  { key: 'batch', icon: <AppstoreOutlined />, label: '批量打印' },
  { key: 'verify', icon: <ScanOutlined />, label: '扫码验货' },
  { key: 'logistics', icon: <CarOutlined />, label: '快递物流' },
  { type: 'divider' as const },
  { key: 'sku', icon: <ProductOutlined />, label: '商品 SKU' },
  { key: 'inventory', icon: <InboxOutlined />, label: '仓库库存' },
  { key: 'purchase', icon: <TeamOutlined />, label: '采购管理' },
  { key: 'finance', icon: <DollarOutlined />, label: '财务利润' },
  { key: 'aftersale', icon: <SwapOutlined />, label: '售后管理' },
  { key: 'ai', icon: <RobotOutlined />, label: 'AI 智能中心' },
  { type: 'divider' as const },
  { key: 'shops', icon: <ShopOutlined />, label: '店铺管理' },
  { key: 'printers', icon: <BarcodeOutlined />, label: '打印机管理' },
  { key: 'settings', icon: <SettingOutlined />, label: '系统设置' },
];

export function AppShell() {
  const [collapsed, setCollapsed] = useState(false);
  const { session, activeMenu, setActiveMenu, setSession } = useAppStore();
  const renderPage = () => {
    if (activeMenu === 'dashboard') return <DashboardPage />;
    if (activeMenu === 'orders') return <OrdersPage />;
    if (activeMenu === 'printing') return <PrintCenterPage />;
    return <ModulePage moduleKey={activeMenu} />;
  };
  return <Layout className="app-layout">
    <Sider width={230} collapsedWidth={76} collapsed={collapsed} className="app-sider">
      <div className="sider-brand"><div className="brand-mark small">智</div>{!collapsed && <div><strong>智单 ERP</strong><span>SmartOrder</span></div>}</div>
      <Menu theme="dark" mode="inline" selectedKeys={[activeMenu]} items={menu} onClick={({ key }) => setActiveMenu(key)} />
      <button className="collapse-button" onClick={() => setCollapsed(!collapsed)}>{collapsed ? <MenuUnfoldOutlined /> : <><MenuFoldOutlined /> 收起导航</>}</button>
    </Sider>
    <Layout>
      <Header className="app-header">
        <div className="company-block"><Typography.Text strong>{session?.tenantName}</Typography.Text><Tag color="blue">开发环境</Tag></div>
        <Select defaultValue="all" variant="borderless" className="shop-selector" options={[{ value: 'all', label: '全部店铺 · 4 个模拟店' }, { value: 'douyin', label: '抖音旗舰店' }, { value: 'pdd', label: '拼多多一号店' }]} />
        <Input prefix={<SearchOutlined />} placeholder="搜索订单、商品、SKU" className="global-search" />
        <Space size={18} className="header-actions">
          <Tooltip title="订单同步正常"><Tag icon={<SyncOutlined spin />} color="processing">同步正常</Tag></Tooltip>
          <Tooltip title="MockPrinter 已连接"><Tag icon={<PrinterOutlined />} color="success">打印机已连接</Tag></Tooltip>
          <Badge count={3} size="small"><BellOutlined className="header-icon" /></Badge>
          <Dropdown menu={{ items: [{ key: 'profile', icon: <UserOutlined />, label: '个人资料' }, { type: 'divider' }, { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: () => setSession(null) }] }}>
            <Space className="user-block"><Avatar size="small">管</Avatar><span>{session?.userName}</span></Space>
          </Dropdown>
        </Space>
      </Header>
      <Content className="app-content">{renderPage()}</Content>
    </Layout>
  </Layout>;
}

