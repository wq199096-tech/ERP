# API 接口说明

启动业务 API 后访问 `http://127.0.0.1:8000/docs` 可查看 OpenAPI 交互文档，Print Agent 文档位于 `http://127.0.0.1:17321/docs`。

主要接口：

- `POST /api/v1/auth/login`：开发环境账号登录，返回租户范围 JWT。
- `GET /api/v1/shops`：查询当前租户店铺及能力状态。
- `POST /api/v1/orders/mock/sync?count=1000`：幂等生成/同步模拟订单。
- `GET /api/v1/orders`：分页、平台、店铺、状态及关键词筛选。
- `POST /api/v1/orders/import`：导入 UTF-8 CSV 或 XLSX。
- `POST /api/v1/orders/batch/audit`：批量审核。
- `POST /api/v1/orders/batch/print-queue`：批量标记进入打印队列。
- `GET /api/v1/printers`：Print Agent 枚举 MockPrinter 与 Windows 系统队列。
- `POST /api/v1/jobs`：提交幂等打印任务。
- `POST /api/v1/jobs/{id}/retry`：重试失败或状态未知任务，复用原测试运单号。
- `POST /api/v1/jobs/{id}/cancel`：取消未终结任务。
- `POST /api/v1/queue/pause`、`/queue/resume`：暂停与恢复持久化队列。
- `POST /api/v1/jobs/{id}/confirm-printed`：对已接收或状态未知任务进行人工出纸确认。
- `GET /api/v1/jobs/{id}/pdf`：获取任务 PDF。

业务 API 使用 `Authorization: Bearer <JWT>`；Print Agent 使用仅本机配置的独立 Bearer Token。

