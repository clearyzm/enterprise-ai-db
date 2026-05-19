# PHASE_1_REPORT — 数据库迁移 + RLS + 种子数据

## 已实现清单

| 文件 | 状态 | 说明 |
|---|---|---|
| `backend/migrations/versions/0001_init.py` | ✅ | 完整 DDL：18 张表 + 5 个扩展 + 所有索引（330 行）|
| `backend/migrations/versions/0002_rls.py` | ✅ | 16 张表启用 RLS + tenant_isolation 策略（97 行）|
| `backend/migrations/versions/0003_seed_permissions.py` | ✅ | 19 条全局 permissions（75 行）|
| `backend/app/db/base.py` | ✅ | SQLAlchemy DeclarativeBase（19 行）|
| `backend/app/db/session.py` | ✅ | async engine + sessionmaker + get_db()（49 行）|
| `backend/app/db/rls.py` | ✅ | set_tenant_context() + set_user_context()（44 行）|
| `backend/app/scripts/seed_demo.py` | ✅ | demo tenant + 3 用户 + 5 角色 + 2 部门 + 1 dataset（256 行）|
| `backend/migrations/env.py` | ✅ | 移除 try/import，正式导入 Base（3 行修改）|

**总计**：8 个文件，约 870 行代码。

## 偏离文档的设计决策

| 决策 | 原因 |
|---|---|
| `0001_init.py` 使用 `op.execute()` 而非 `op.create_table()` | DDL 包含 CHECK 约束、JSONB 默认值、citext 类型，原始 SQL 更精确匹配文档 |
| `chunks.embedding` 维度硬编码 `vector(1536)` | 与 `.env.example` 的 `EMBED_DIM=1536` 一致；换模型需同步修改迁移或追加 ALTER COLUMN |
| `0003_seed_permissions.py` 使用 `ON CONFLICT DO NOTHING` | 保证幂等性，可重复执行 |
| `rls.py` 的 `set_tenant_context()` 在 `tenant_id=None` 时设为零 UUID | 防御性设计：确保 RLS 阻止所有行，防止中间件失败时数据泄漏 |
| `seed_demo.py` 所有用户密码统一为 `demo123456` | 开发便利性；生产环境需强制首次登录改密（Phase 2 实现）|

## 已知 TODO / 风险

- **ORM 模型缺失**：Phase 1 仅建表，Phase 2 需创建 `app/models/*.py` 的 ORM 类并在 `app/db/base.py` 导入，才能使用 `alembic revision --autogenerate`。
- **中间件未实现**：`session.py` 的 `get_db()` 暂时直接 yield session，Phase 2 需在认证中间件中调用 `set_tenant_context()`。
- **密码策略**：`seed_demo.py` 使用 argon2 哈希，但未实现密码强度校验、首次登录强制改密（Phase 2）。
- **向量维度变更**：如换嵌入模型（如 BGE-large 1024 维），需手动修改 `0001_init.py` 的 `vector(1536)` 或追加新迁移 `ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(1024)`。
- **user_departments.is_primary 约束**：文档未要求但建议追加：每个用户最多一个 `is_primary=true` 的部门（可用 partial unique index 或触发器，v2 实现）。

## 测试通过率

Phase 1 无新增测试（Phase 0 的 2 条 health 测试仍通过）。

**手动验收**：
```bash
# 1. 执行迁移
make migrate
# 预期输出：
#   INFO  [alembic.runtime.migration] Running upgrade  -> 0001, Initial schema
#   INFO  [alembic.runtime.migration] Running upgrade 0001 -> 0002, Enable RLS
#   INFO  [alembic.runtime.migration] Running upgrade 0002 -> 0003, Seed permissions

# 2. 验证表结构
docker compose exec postgres psql -U postgres -d enterprise_ai -c "\dt"
# 预期：18 张表全部存在

# 3. 验证 RLS
docker compose exec postgres psql -U postgres -d enterprise_ai -c "SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='public' AND tablename='users';"
# 预期：rowsecurity = t

# 4. 验证 permissions
docker compose exec postgres psql -U postgres -d enterprise_ai -c "SELECT count(*) FROM permissions;"
# 预期：19

# 5. 执行种子
make seed
# 预期输出：
#   ✅ Created tenant: <uuid>
#   ✅ Created departments: Sales (<uuid>), Finance (<uuid>)
#   ✅ Created users: admin@demo.com, sales@demo.com, finance@demo.com
#   ✅ Created roles: tenant_admin, editor, viewer, approver, ai_user
#   ✅ Assigned roles to users
#   ✅ Created dataset: sales_orders (<uuid>)
#   🎉 Demo seed completed successfully!

# 6. 验证 RLS 生效
docker compose exec postgres psql -U postgres -d enterprise_ai -c "SET app.tenant_id='00000000-0000-0000-0000-000000000000'; SELECT count(*) FROM users;"
# 预期：0（零 UUID 触发 RLS 阻止）

docker compose exec postgres psql -U postgres -d enterprise_ai -c "SET app.tenant_id='<demo_tenant_id>'; SELECT count(*) FROM users;"
# 预期：3
```

## 给 Phase 2 的上下文摘要（≤500字）

Phase 1 已完成数据库全部 18 张表的迁移、RLS 策略、全局 permissions 种子、demo 租户种子。

**数据库层**：
- 所有表已建立，索引完整（包括 HNSW 向量索引 `ix_chunks_embedding`）。
- RLS 已启用，策略名 `tenant_isolation`，依赖 `current_setting('app.tenant_id', true)::uuid`。
- `permissions` 表已插入 19 条标准权限（read/write/delete/approve/manage/ai_query × 各资源类型）。

**应用层基础设施**：
- `app/db/base.py` 提供 `Base`（DeclarativeBase），Phase 2 需在此导入所有 ORM 模型。
- `app/db/session.py` 提供 `engine`、`async_session_maker`、`get_db()` 依赖注入函数。
- `app/db/rls.py` 提供 `set_tenant_context(session, tenant_id)`，Phase 2 中间件必须在每个请求开始时调用。

**Demo 数据**：
- Tenant: `slug='demo'`，`name='Demo Corporation'`
- Users: `admin@demo.com`（tenant_admin，全租户）、`sales@demo.com`（editor+ai_user，Sales 部门）、`finance@demo.com`（viewer，Finance 部门）
- 密码统一：`demo123456`（argon2 哈希）
- Dataset: `sales_orders`（owner_dept=Sales，schema 含 order_no/customer/amount/status）

**Phase 2 关键任务**：
1. 创建 ORM 模型（`app/models/tenant.py`、`user.py`、`role.py` 等），在 `app/db/base.py` 导入。
2. 实现认证中间件：解析 JWT → 提取 `tenant_id` → 调用 `set_tenant_context()`。
3. 实现 `/api/v1/auth/login`、`/refresh`、`/logout` 端点。
4. 实现 `PermissionService.check(user, action, resource_type, resource_obj)`。
5. 实现用户/角色/权限 CRUD API（`/api/v1/users`、`/roles`、`/permissions`）。

**验收命令**：`make migrate && make seed`，然后用 psql 验证 RLS（见上方测试通过率）。
