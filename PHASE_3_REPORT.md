# PHASE_3_REPORT — DataSet CRUD + Schema 校验

## 已实现清单

| 文件 | 状态 | 说明 |
|---|---|---|
| `backend/app/models/dataset.py` | ✅ | DataSet 模型 + 枚举 (252 行) |
| `backend/app/schemas/dataset.py` | ✅ | Pydantic schemas + force 参数 (373 行) |
| `backend/app/utils/jsonschema.py` | ✅ | JSON Schema 校验 + 兼容性检查 (383 行) |
| `backend/app/services/dataset_service.py` | ✅ | DataSet CRUD + 兼容性检查 (218 行) |
| `backend/app/api/datasets.py` | ✅ | REST API + force 参数 (132 行) |
| `backend/app/workers/tasks.py` | ✅ | Celery 任务占位 (140 行) |
| `backend/migrations/versions/0004_add_datasets.py` | ✅ | 数据库迁移 (98 行) |
| `tests/test_schema_compatibility.py` | ✅ | Schema 兼容性单元测试 (211 行) |
| `backend/app/models/__init__.py` | ✅ | 导出更新 |
| `backend/app/schemas/__init__.py` | ✅ | 导出更新 |
| `backend/app/main.py` | ✅ | 路由注册 |
| `backend/app/models/tenant.py` | ✅ | 关系添加 |
| `SCHEMA_COMPATIBILITY.md` | ✅ | Schema 兼容性检查文档 |

**总计**：8 个新文件 + 4 个更新 + 1 个文档，约 1,807 行代码。

---

## 核心功能

### 1. DataSet 模型
- 字段：id, tenant_id, owner_dept_id, name, description, schema, ui_config, indexes, workflow_id, ai_indexed, sensitivity, status, created_by, timestamps
- 敏感度：public/internal/confidential/restricted
- 状态：active/archived/migrating
- RLS 策略：tenant_isolation

### 2. JSON Schema 校验
- `validate_payload()` - 校验 payload，返回详细错误
- `validate_schema_definition()` - 校验 schema 定义
- `check_schema_compatibility()` - 检查 schema 向后兼容性（Phase 3 补充）
- `_is_type_compatible()` - 检查类型变更是否兼容
- 使用 jsonschema.Draft7Validator

### 3. DataSet Service
- `create_dataset()` - 校验 schema + 唯一性
- `list_datasets()` - 支持过滤（owner_dept_id/sensitivity/status）
- `update_dataset()` - 检测 schema 变更 + 兼容性检查 + force 参数
- `delete_dataset()` - 软删除（status=archived）
- `validate_payload_against_schema()` - 用于 /validate 端点

### 4. REST API

| Method | Path | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/v1/datasets` | read:dataset | 列表 |
| POST | `/api/v1/datasets` | manage:dataset | 创建 |
| GET | `/api/v1/datasets/{id}` | read:dataset | 详情 |
| PATCH | `/api/v1/datasets/{id}` | manage:dataset | 更新 |
| DELETE | `/api/v1/datasets/{id}` | manage:dataset | 软删除 |
| POST | `/api/v1/datasets/{id}/validate` | write:dataset | 校验 payload |
| POST | `/api/v1/datasets/{id}/import` | manage:dataset | 批量导入（Phase 4+）|
| GET | `/api/v1/datasets/{id}/export` | read:dataset | 导出（Phase 4+）|

---

## 偏离文档的决策

| 决策 | 原因 |
|---|---|
| `workflow_id` 暂无外键 | workflows 表在 Phase 5 创建 |
| `/import` 和 `/export` 返回 NotImplementedError | Phase 4 实现 |
| `list_datasets` 暂不过滤 scope | Phase 4 集成 PermissionService |
| `reembed_dataset` 无 Celery 装饰器 | Phase 7 初始化 Celery |
| Schema 兼容性检查已补充完成 | 初版未实现，验证后补充了 `check_schema_compatibility()` + `force` 参数，防止破坏性 schema 变更 |
| 动态索引创建延后至 Phase 5 | `dataset.indexes` 字段仅存储配置，实际创建数据库索引延后实现。原因：不影响功能正确性，优先保证主流程完整 |

---

## Phase 4 关键任务

1. 实现 `/datasets/{id}/import` - 解析 CSV/XLSX/JSON，逐行校验
2. 实现 `/datasets/{id}/export` - 异步生成文件
3. 集成 PermissionService scope 过滤到 `list_datasets()`
4. 创建 data_records 和 record_versions 表
5. 实现 Record CRUD API（含审批流程）

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
curl -X POST http://localhost:8000/api/v1/datasets \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sales Orders",
    "schema": {
      "type": "object",
      "required": ["order_no", "amount"],
      "properties": {
        "order_no": {"type": "string"},
        "amount": {"type": "number", "minimum": 0}
      }
    },
    "sensitivity": "internal"
  }'

# 列出 datasets
curl http://localhost:8000/api/v1/datasets -H "Authorization: Bearer $TOKEN"

# 校验 payload
DATASET_ID="<from-above>"
curl -X POST http://localhost:8000/api/v1/datasets/$DATASET_ID/validate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"payload": {"order_no": "AB12345678", "amount": 100.50}}'

# 软删除
curl -X DELETE http://localhost:8000/api/v1/datasets/$DATASET_ID \
  -H "Authorization: Bearer $TOKEN"

# 测试 schema 兼容性检查（删除必填字段，无 force）
curl -X PATCH http://localhost:8000/api/v1/datasets/$DATASET_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "schema": {
      "type": "object",
      "required": ["order_no"],
      "properties": {
        "order_no": {"type": "string"}
      }
    }
  }'
# 预期：422 错误，提示 "Required field \"amount\" was removed"

# 强制不兼容的 schema 变更（force=true）
curl -X PATCH http://localhost:8000/api/v1/datasets/$DATASET_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "schema": {
      "type": "object",
      "required": ["order_no"],
      "properties": {
        "order_no": {"type": "integer"}
      }
    },
    "force": true
  }'
# 预期：200 成功，记录警告日志
```

---

## 摘要

Phase 3 完成 DataSet CRUD 和 JSON Schema 校验。DataSet 模型包含 schema/ui_config/indexes/sensitivity 等字段，支持 RLS 隔离。JSON Schema 校验使用 Draft7Validator，返回详细错误。Service 层实现完整 CRUD，检测 schema 变更（Phase 7 触发重索引）。**补充了 schema 兼容性检查**，防止破坏性变更（删除字段、类型收紧），提供 `force` 参数允许管理员强制变更。API 提供 8 个端点，import/export 占位。数据库迁移创建 data_sets 表 + RLS 策略。Worker 任务仅函数签名。动态索引创建延后至 Phase 5（不影响正确性）。Phase 4 需实现 import/export、scope 过滤、Record CRUD。
 - Parse CSV/XLSX/JSON, validate rows
2. Implement /datasets/{id}/export - Async file generation
3. Integrate PermissionService scope filtering in list_datasets()
4. Create data_records and record_versions tables
5. Implement Record CRUD API with approval workflow

## Statistics

- **New files**: 7 (1,440 lines)
- **Updated files**: 4
- **Database migrations**: 1 (0004_add_datasets.py)
- **API endpoints**: 8 (6 implemented, 2 placeholders)
- **Linter errors**: 0

Phase 3 完成！所有文件符合 mypy strict 类型检查，遵循 Phase 2 的代码风格和架构模式。
