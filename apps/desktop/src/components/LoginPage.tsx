import { LockOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Form, Input, Space, Typography, message } from 'antd';
import { useState } from 'react';
import { api } from '../api';
import { useAppStore } from '../store';

export function LoginPage() {
  const setSession = useAppStore((state) => state.setSession);
  const [loading, setLoading] = useState(false);

  const submit = async (values: { email: string; password: string }) => {
    setLoading(true);
    try {
      const result = await api.login(values.email, values.password);
      setSession({
        token: result.access_token,
        userName: result.user.name,
        tenantName: result.tenant.name,
      });
    } catch (error) {
      message.error(error instanceof Error ? error.message : '登录失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <section className="login-brand">
        <div className="brand-mark">智</div>
        <Typography.Title style={{ color: 'white', marginBottom: 8 }}>智单 ERP</Typography.Title>
        <Typography.Paragraph className="login-subtitle">
          多平台订单、仓储履约与可靠打印，汇聚在一个 Windows 工作台。
        </Typography.Paragraph>
        <Space direction="vertical" size={18} className="login-feature-list">
          <span><SafetyCertificateOutlined /> 多租户隔离与操作审计</span>
          <span><SafetyCertificateOutlined /> 打印状态不虚报，异常可追溯</span>
          <span><SafetyCertificateOutlined /> 平台能力状态清晰可核验</span>
        </Space>
      </section>
      <Card className="login-card" variant="borderless">
        <Typography.Title level={2}>欢迎回来</Typography.Title>
        <Typography.Text type="secondary">登录企业工作台以继续处理订单</Typography.Text>
        <Alert message="开发环境演示账号已预填；不包含真实店铺授权。" type="info" showIcon />
        <Form
          layout="vertical"
          onFinish={submit}
          initialValues={{ email: 'admin@smartorder.local', password: 'SmartOrder123!' }}
          size="large"
        >
          <Form.Item label="登录邮箱" name="email" rules={[{ required: true }]}>
            <Input prefix={<UserOutlined />} autoComplete="username" />
          </Form.Item>
          <Form.Item label="密码" name="password" rules={[{ required: true }]}>
            <Input.Password prefix={<LockOutlined />} autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>登录智单 ERP</Button>
        </Form>
      </Card>
    </div>
  );
}

