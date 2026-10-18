# 智单 ERP（SmartOrder ERP）

面向中国大陆电商商家的 Windows 智能打单 ERP。当前交付包含桌面客户端、统一订单中心、模拟平台、CSV/Excel 导入、三类打印预览与本地 Print Agent。所有模拟面单均有醒目的“测试样张”标识，不代表任何平台或快递公司的正式授权能力。

## 本地启动（Windows PowerShell）

```powershell
.\scripts\setup.ps1
Copy-Item .env.example .env
docker compose up -d postgres redis
Push-Location services\api
& ..\..\.venv\Scripts\python.exe -m alembic upgrade head
Pop-Location
```

分别启动三个进程：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir services\api
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 17321 --app-dir services\print-agent
pnpm dev
```

开发账号：`admin@smartorder.local`，密码：`SmartOrder123!`（仅开发模式）。

## 验证命令

```powershell
.\.venv\Scripts\python.exe -m ruff check services
.\.venv\Scripts\python.exe -m pytest services\api\tests services\print-agent\tests
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm package:win
```

## 重要边界

- 真实抖音、拼多多、淘宝/天猫、京东授权尚未提供，适配器状态明确为“待授权”。
- 本地 Print Agent 默认使用 MockPrinter；系统打印机仅枚举 Windows 已安装队列，未在本机宣称硬件打印验收通过。
- 财务模块用于经营分析，不替代专业会计总账或报税软件。
- 密钥只从环境变量读取，仓库不包含生产凭证。

更多资料见 `docs/`。

