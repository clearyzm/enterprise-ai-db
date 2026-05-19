# PHASE_4_REPORT — DataRecord + 乐观锁 + 列表过滤

## 已实现清单

| 文件 | 状态 | 说明 |
|---|---|---|
| `backend/app/models/record.py` | ✅ | DataRecord + RecordVersion 模型 (335 行) |
| `backend/app/schemas/record.py` | ✅ | Pydantic schemas (257 行) |
| `backend/app/utils/filter_parser.py` | ✅ | 安全过滤解析器 (296 行) |
| `backend/app/services/record_service.py` | ✅ | Record CRUD + 乐观锁 (390 行) |
| `backend/app/api/records.py` | ✅ | REST API 端点 (309 行) |
| `backend/migrations/versions/0005_add_records.py` | ✅ | 数据库迁移 (185 行) |
| `backend/app/services/dataset_service.py` | ✅ | 补充 scope 过滤 (已更新) |
| `backend/app/models/__init__.py` | ✅ | 导出更新 |
| `backend/app/schemas/__init__.py` | ✅ | 导出更新 |
| `backend/app/main.py` | ✅ | 路由注册 |

**总计**：6 个新文件 + 4 个更新，约 1,772 行代码。

---

## 核心功能

### 1. DataRecord 模型
- 字段：id, tenant_id, dataset_id, department_id, payload (JSONB), status, version, created_by, updated_by, timestamps
- **乐观锁**：version 字段，每次更新递增
- 状态：active, soft_deleted
- 索引：(tenant_id, dataset_id), (tenant_id, department_id) 仅 active 记录
- RLS 策略：tenant_isolation

### 2. RecordVersion 模型
- 字段：id, tenant_id, record_id (nullable), dataset_id, op, before_payload, after_payload, state, workflow_id, current_step, proposed_by, applied_at, reason, reject_reason, created_at
- 操作类型：insert, update, delete
- 状态：pending, approved, rejected, applied, superseded, cancelled
- **业务约束**：
  - INSERT: before_payload 必须为 NULL
  - DELETE: after_payload 必须为 NULL
- 索引：pending 版本索引，记录历史索引

### 3. FilterParser（安全过滤）
- **白名单操作符**：eq, ne, gt, gte, lt, lte, in, contains
- **字段白名单**：仅允许 dataset.schema 中定义的字段
- **参数化绑定**：所有值使用 bindparam()，严禁字符串拼接
- 类型转换：根据 JSON Schema 类型自动转换（string, number, integer, boolean）
- JSONB 查询：payload->>'field' 或 (payload->>'field')::numeric

### 4. RecordService（CRUD + 乐观锁）
- `create_record()` - 提交 INSERT，返回 (version, record)
- `update_record()` - 提交 UPDATE，检查 expected_version
- `delete_record()` - 提交 DELETE（软删除）
- `list_records()` - 列表 + 过滤 + 分页
- `get_record()` - 详情（含 version）
- `get_record_history()` - 历史版本
- **乐观锁实现**：
  ```sql
  UPDATE data_records
  SET payload = ?, version = version + 1, updated_at = now()
  WHERE id = ? AND version = ?
  ```
  - 如果 rowcount = 0 → 409 VERSION_CONFLICT

### 5. Phase 4 自动审批
- 所有变更写入 record_versions (state='pending')
- 立即调用 `_apply_insert/update/delete()`
- 更新 state='applied', applied_at=now()
- Phase 5 将替换为真正的工作流

### 6. REST API

| Method | Path | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/v1/datasets/{ds_id}/records` | read:record | 列表 + 过滤 + 分页 |
| POST | `/api/v1/datasets/{ds_id}/records` | write:record | 提交新增 |
| GET | `/api/v1/datasets/{ds_id}/records/{id}` | read:record | 详情 |
| PATCH | `/api/v1/datasets/{ds_id}/records/{id}` | write:record | 提交修改 |
| DELETE | `/api/v1/datasets/{ds_id}/records/{id}` | delete:record | 提交删除 |
| GET | `/api/v1/datasets/{ds_id}/records/{id}/history` | read:record | 历史版本 |
| GET | `/api/v1/records/{id}` | read:record | 详情（备用路由） |

### 7. Scope 过滤（补充）
- `dataset_service.list_datasets()` 现在集成 `PermissionService.get_accessible_dataset_ids()`
- 如果返回非空列表 → 添加 `WHERE id IN (...)`
- 如果返回空列表 → 全租户访问（tenant_admin 或无 scope 限制的角色）

---

## 偏离文档的决策

| 决策 | 原因 |
|---|---|
| Phase 4 全部自动审批 | 按设计要求，Phase 5 才实现真正工作流 |
| `list_records()` 暂未解析 query_params 中的 filter | API 层需要手动解析，Phase 4 先占位 |
| `workflow_id` 暂无外键 | workflows 表在 Phase 5 创建 |

---

## 数据库迁移（0005_add_records.py）

### 创建的枚举类型
- `record_status_enum`: active, soft_deleted
- `record_version_op_enum`: insert, update, delete
- `record_version_state_enum`: pending, approved, rejected, applied, superseded, cancelled

### 创建的表
- `data_records`: 当前活跃记录
- `record_versions`: 变更历史 + 审批队列

### 创建的索引
- `ix_records_tenant_dataset_active`: (tenant_id, dataset_id) WHERE status='active'
- `ix_records_tenant_dept_active`: (tenant_id, department_id) WHERE status='active'
- `ix_rv_tenant_pending`: (tenant_id, state) WHERE state='pending'
- `ix_rv_record_created`: (record_id, created_at)

### RLS 策略
- 两张表均启用 RLS
- 策略名：tenant_isolation
- 条件：tenant_id = current_setting('app.tenant_id')::uuid

---

## 安全保证

### 1. SQL 注入防护
- FilterParser 使用白名单操作符
- 所有值使用 `text().bindparams()` 参数化
- 字段名白名单（仅 schema 中定义的字段）

### 2. 乐观锁
- UPDATE 必须携带 expected_version
- WHERE 子句包含 `version = ?`
- 冲突返回 409 ConflictError

### 3. Payload 校验
- 所有写操作先调用 `validate_payload()`
- 使用 jsonschema.Draft7Validator
- 校验失败返回 422 ValidationError

### 4. RLS 隔离
- 所有查询自动过滤 tenant_id
- 防止跨租户数据泄露

---

## 测试命令

```bash
# 运行迁移
cd backend && uv run alembic upgrade head

# 启动服务
uv run uvicorn app.main:app --reload

# 登录
TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"tenant_slug":"demo","email":"admin@demo.com","password":"demo123456"}' \
  | jq -r '.access_token')

# 创建 dataset
DATASET_ID=$(curl -X POST http://localhost:8000/api/v1/datasets \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sales Orders",
    "schema": {
      "type": "object",
      "required": ["order_no", "amount"],
      "properties": {
        "order_no": {"type": "string"},
        "amount": {"type": "number", "minimum": 0},
        "status": {"type": "string", "enum": ["draft", "paid", "cancelled"]}
      }
    }
  }' | jq -r '.id')

# 创建 record
RECORD_ID=$(curl -X POST http://localhost:8000/api/v1/datasets/$DATASET_ID/records \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "payload": {
      "order_no": "AB12345678",
      "amount": 100.50,
      "status": "draft"
    },
    "reason": "New order"
  }' | jq -r '.record.id')

# 列出 records
curl http://localhost:8000/api/v1/datasets/$DATASET_ID/records \
  -H "Authorization: Bearer $TOKEN"

# 获取 record 详情（含 version）
curl http://localhost:8000/api/v1/datasets/$DATASET_ID/records/$RECORD_ID \
  -H "Authorization: Bearer $TOKEN"

# 更新 record（乐观锁）
curl -X PATCH http://localhost:8000/api/v1/datasets/$DATASET_ID/records/$RECORD_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "payload": {
      "order_no": "AB12345678",
      "amount": 150.75,
      "status": "paid"
    },
    "expected_version": 1,
    "reason": "Payment received"
  }'

# 测试版本冲突（使用错误的 expected_version）
curl -X PATCH http://localhost:8000/api/v1/datasets/$DATASET_ID/records/$RECORD_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "payload": {
      "order_no": "AB12345678",
      "amount": 200.00,
      "status": "paid"
    },
    "expected_version": 1,
    "reason": "Price adjustment"
  }'
# 预期：409 Conflict (version mismatch)

# 获取历史版本
curl http://localhost:8000/api/v1/datasets/$DATASET_ID/records/$RECORD_ID/history \
  -H "Authorization: Bearer $TOKEN"

# 删除 record（软删除）
curl -X DELETE http://localhost:8000/api/v1/datasets/$DATASET_ID/records/$RECORD_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Duplicate entry"}'

# 测试过滤（TODO: Phase 4 需要在 API 层解析 query_params）
# curl "http://localhost:8000/api/v1/datasets/$DATASET_ID/records?amount__gte=100&status__eq=paid" \
#   -H "Authorization: Bearer $TOKEN"
```

---

## Phase 5 关键任务

1. 创建 workflows 和 approval_actions 表
2. 实现真正的审批流程（多步骤、会签）
3. 将 `_apply_*()` 方法改为仅在 workflow 完成后调用
4. 实现审批 API（approve/reject）
5. 在 API 层解析 filter query_params

---

## 统计

- **新文件**：6 (1,772 行)
- **更新文件**：4
- **数据库迁移**：1 (0005_add_records.py)
- **API 端点**：7
- **Linter 错误**：0

---

## 摘要

Phase 4 完成 DataRecord CRUD 和乐观锁机制。DataRecord 模型包含 payload (JSONB) 和 version 字段，支持 RLS 隔离。RecordVersion 模型跟踪所有变更（insert/update/delete），包含审批状态机。FilterParser 提供安全的 JSONB 过滤，使用白名单操作符和参数化查询。RecordService 实现完整 CRUD，UPDATE 操作使用 `WHERE version = ?` 实现乐观锁，冲突返回 409。Phase 4 使用自动审批（立即 apply），Phase 5 将实现真正工作流。API 提供 7 个端点，支持列表、详情、历史、提交变更。数据库迁移创建 data_records 和 record_versions 表，包含 3 个枚举类型和 4 个索引。补充了 dataset_service.list_datasets() 的 scope 过滤。所有代码符合 mypy strict 类型检查，遵循 Phase 1-3 的架构模式。
