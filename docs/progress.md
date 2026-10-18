# 开发进度记录

## 2026-10-17

- 初始化 Monorepo、Docker Compose、环境变量模板、质量与测试命令。
- 当前环境缺少 Docker CLI，因此容器联调留待安装 Docker Desktop 后执行。

## 2026-10-18 · Stage 0–3 可运行版本

- Stage 0：Monorepo、FastAPI、SQLAlchemy/Alembic、PostgreSQL/Redis Compose、环境模板、质量命令和 Windows 脚本完成。
- Stage 1：登录、商业工作台、15 项导航、经营首页、订单表格、筛选、批量选择、详情抽屉和异常/空状态完成。
- Stage 2：JWT 租户上下文、4 个模拟平台、1000 条确定性订单、幂等同步、CSV/XLSX 导入、批量审核和打印队列完成。
- Stage 3：本地令牌鉴权 Print Agent、Windows 打印机枚举、SQLite 持久化、队列暂停/恢复、重启恢复、失败重试、人工确认以及面单/清单/标签 PDF 完成。
- 商品标签编辑器支持毫米尺寸、字段拖动、对齐、保存模板、条形码和二维码。
- Windows NSIS x64 安装包实际构建成功；MockPrinter 自动化通过，未进行真实热敏打印机硬件验收。
- 本机仍缺少 Docker CLI，因此 PostgreSQL/Redis 容器连接只完成配置和迁移离线验证，未虚报容器联调通过。

### 本轮实测

- Python API：5 passed。
- Print Agent：8 passed（含 1000 任务持久化与 100×150 mm 尺寸）。
- React：1 passed。
- Ruff、ESLint、TypeScript：通过。
- Vite 生产构建、Electron `win-unpacked` 启动冒烟、NSIS 安装包构建：通过。

