# 架构说明

项目采用模块化单体：Electron/React 客户端通过 HTTP 调用 FastAPI 业务 API；本地 Print Agent 仅监听回环地址并使用令牌鉴权。PostgreSQL 保存业务数据，Redis/Celery 预留给同步和异步任务。平台能力通过统一适配器隔离，当前只有 Mock 与文件导入可执行。

