# 数据库设计

所有业务核心表均带 `tenant_id` 或通过父记录关联租户。订单以 `(tenant_id, platform, shop_id, platform_order_no)` 唯一约束完成幂等同步；金额使用 `NUMERIC(18, 2)`；库存与打印任务使用幂等键和状态机。首个 Alembic 迁移创建任务要求的核心表、外键和唯一索引。

