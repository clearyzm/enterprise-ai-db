# PHASE_2_REPORT — 认证 + 用户/角色/权限

## 已实现清单

| 文件 | 状态 | 说明 |
|---|---|---|
| **模型层 (6 个)** | | |
| `backend/app/models/base_model.py` | ✅ | Base + TimestampMixin + TenantMixin + SoftDeleteMixin (105 行) |
| `backend/app/models/tenant.py` | ✅ | Tenant 模型 + TenantStatus 枚举 (126 行) |
| `backend/app/models/user.py` | ✅ | User 模型 + UserStatus 枚举 (140 行) |
| `backend/app/models/department.py` | ✅ | Department + UserDepartment 关联表 (168 行) |
| `backend/app/models/role.py` | ✅ | Permission + Role + RolePermission + UserRole (258 行) |
| **工具层 (4 个)** | | |
| `backend/app/utils/errors.py` | ✅ | APIError 基类 + 12 个具体错误类 (210 行) |
| `backend/app/utils/hashing.py` | ✅ | Argon2id 密码哈希（time_cost=3, memory_cost=65536, parallelism=4）(93 行) |
| `backend/app/utils/jwt.py` | ✅ | JWT access token + 不透明 refresh token (156 行) |
| **依赖注入 (1 个)** | | |
| `backend/app/deps.py` | ✅ | get_current_user + require_perm + CurrentUser 类型别名 (139 行) |
| **中间件 (1 个)** | | |
| `backend/app/middleware/tenant.py` | ✅ | TenantContextMiddleware（从 JWT 提取 tenant_id → SET LOCAL）(89 行) |
| **服务层 (2 个)** | | |
| `backend/app/services/auth_service.py` | ✅ | login + change_password + get_current_user_info (249 行) |
| `backend/app/services/permission_service.py` | ✅ | check + _scope_matches + get_accessible_dataset_ids + **compute_ai_access** + AIAccessBundle (344 行) |
| **API 层 (4 个)** | | |
| `backend/app/api/auth.py` | ✅ | POST /login, GET /me, POST /change-password (249 行) |
| `backend/app/api/users.py` | ✅ | 用户 CRUD + 角色分配/撤销 (373 行) |
| `backend/app/api/roles.py` | ✅ | 角色 CRUD + GET /permissions (309 行) |
| `backend/app/api/departments.py` | ✅ | 部门 CRUD（支持树形结构）(318 行) |
| **应用入口 (1 个)** | | |
| `backend/app/main.py` | ✅ | 注册路由 + 中间件 + APIError 异常处理器（更新已有文件）|

**总计**：17 个新文件 + 1 个更新，约 3,126 行代码（含 compute_ai_access 补充）。

---

## 核心功能实现

### 1. 认证系统

**登录流程**：
```
POST /api/v1/auth/login
  ↓
验证 tenant_slug → 加载 Tenant
  ↓
验证 email (CITEXT, 不区分大小写) → 加载 User
  ↓
验证 password (Argon2id)
  ↓
检查 user.status == 'active'
  ↓
更新 last_login_at + 自动升级旧密码哈希
  ↓
生成 access_token (JWT, 15min, 含 user_id/tenant_id/roles/departments)
生成 refresh_token (256-bit 随机, 30d, Phase 2 无状态)
  ↓
返回 tokens + user info
```

**JWT Claims 结构**：
```json
{
  "sub": "<user_id>",
  "tid": "<tenant_id>",
  "did": ["<dept_id>", ...],
  "roles": ["editor", "approver"],
  "is_admin": false,
  "jti": "<uuid>",
  "exp": 1234567890,
  "iat": 1234567890
}
```

**中间件 RLS 设置**：
```
每个请求 → TenantContextMiddleware
  ↓
提取 Authorization header → 解码 JWT → 获取 tenant_id
  ↓
创建 AsyncSession → SET LOCAL app.tenant_id = '<tenant_id>'
  ↓
存入 request.state.db + request.state.tenant_id
  ↓
执行路由处理
  ↓
自动关闭 session
```

### 2. RBAC 权限系统

**权限解析算法**（实现 03-security.md §4）：
```python
def check(user, action, resource_type, resource_obj):
    if user.is_tenant_admin:
        return True  # 绕过所有检查
    
    for user_role in user.user_roles:
        role = user_role.role
        scope = user_role.scope
        
        # 检查角色是否有 (action, resource_type) 权限
        if role_has_permission(role, action, resource_type):
            # 检查 scope 是否匹配资源
            if scope_matches(scope, resource_obj, user):
                return True
    
    return False
```

**Scope 匹配逻辑**：
- `{}` (空) → 全租户访问
- `{"department_id": "<uuid>"}` → 限定部门（验证用户属于该部门）
- `{"dataset_ids": ["<uuid>", ...]}` → 限定数据集
- 两者可组合（取交集）

**系统预置角色**（由 Phase 1 种子数据创建）：
- `tenant_admin` - 全部权限
- `editor` - read/write record
- `viewer` - read record + read dataset
- `approver` - approve record
- `ai_user` - ai_query record

### 3. API 端点总览

| Method | Path | 权限 | 说明 |
|---|---|---|---|
| **认证** | | | |
| POST | `/api/v1/auth/login` | 公开 | 登录（返回 access + refresh token）|
| GET | `/api/v1/auth/me` | 已认证 | 当前用户信息 + 角色 + 部门 |
| POST | `/api/v1/auth/change-password` | 已认证 | 修改密码 |
| POST | `/api/v1/auth/refresh` | 公开 | 刷新 token（Phase 3+ 实现）|
| POST | `/api/v1/auth/logout` | 已认证 | 登出（Phase 3+ 实现）|
| **用户管理** | | | |
| GET | `/api/v1/users` | read:user | 列表（支持 department_id 过滤）|
| POST | `/api/v1/users` | write:user | 创建用户 |
| GET | `/api/v1/users/{id}` | read:user 或自己 | 用户详情 |
| PATCH | `/api/v1/users/{id}` | write:user | 更新用户 |
| DELETE | `/api/v1/users/{id}` | delete:user | 软删除（status=disabled）|
| POST | `/api/v1/users/{id}/roles` | write:role | 分配角色 |
| DELETE | `/api/v1/users/{id}/roles/{ur_id}` | write:role | 撤销角色 |
| **角色管理** | | | |
| GET | `/api/v1/roles` | read:role | 列表 |
| POST | `/api/v1/roles` | write:role | 创建角色 |
| PATCH | `/api/v1/roles/{id}` | write:role | 更新角色（系统角色禁止）|
| DELETE | `/api/v1/roles/{id}` | delete:role | 删除角色（系统角色禁止）|
| GET | `/api/v1/roles/permissions` | 已认证 | 全局权限列表 |
| **部门管理** | | | |
| GET | `/api/v1/departments` | read:department | 列表（支持 parent_id 过滤）|
| POST | `/api/v1/departments` | write:department | 创建部门 |
| GET | `/api/v1/departments/{id}` | read:department | 部门详情 |
| PATCH | `/api/v1/departments/{id}` | write:department | 更新部门 |
| DELETE | `/api/v1/departments/{id}` | delete:department | 删除部门 |

---

## 偏离文档的设计决策

| 决策 | 原因 |
|---|---|
| Refresh token 暂时无状态（不存数据库）| Phase 2 简化实现，Phase 3+ 添加 `refresh_tokens` 表实现旋转和撤销 |
| `/auth/refresh` 和 `/auth/logout` 返回 "not_implemented" | 依赖 refresh_tokens 表和 Redis 黑名单，Phase 3+ 实现 |
| `require_perm()` 不含 scope 过滤 | Phase 2 简化版，仅检查用户是否有该权限；完整 scope 匹配在 `PermissionService.check()` 中实现 |
| `user_roles.scope` 唯一约束包含 JSONB | PostgreSQL 支持 JSONB 唯一约束，防止重复分配相同 (user, role, scope) |
| 部门循环引用仅检查直接父子 | Phase 2 仅防止 `parent_id == self.id`；Phase 3+ 添加递归检查防止 A→B→C→A |
| 密码复杂度仅检查长度 ≥ 10 | Phase 3+ 添加字母数字混合、特殊字符等规则 |
| `TenantContextMiddleware` 创建独立 session | 与 `get_db()` 依赖注入分离，确保中间件在路由前设置 RLS；路由可通过 `request.state.db` 或 `Depends(get_db)` 访问 |

---

## 已知 TODO / 风险

### 高优先级（Phase 3 必须解决）

1. **Refresh token 持久化**：
   - 创建 `refresh_tokens` 表（user_id, token_hash, expires_at, device_fingerprint）
   - 实现 `/auth/refresh` 端点（验证 + 旋转）
   - 实现 `/auth/logout` 端点（撤销 refresh + access JTI 加 Redis 黑名单）

2. **密码策略增强**：
   - 复杂度规则：字母 + 数字 + 特殊字符
   - 首次登录强制改密（`users.must_change_password` 字段）
   - 密码历史（防止重用最近 5 个密码）

3. **部门循环引用检查**：
   - 递归查询检测 A→B→C→A 循环
   - 使用 PostgreSQL CTE 或应用层递归

4. **速率限制**：
   - 集成 slowapi 中间件
   - `/auth/login` 按 IP+email 限速（5 次/15 分钟）
   - 连续失败 5 次锁定账户 15 分钟

### 中优先级（Phase 4-5）

5. **审计日志**：
   - 创建 `audit_logs` 表
   - 记录所有写操作（login, user CRUD, role 分配, 密码修改）
   - 使用 SQLAlchemy event listener 自动记录

6. **用户邀请流程**：
   - 创建用户时发送邀请邮件（含一次性 token）
   - 用户首次登录设置密码
   - `users.status = 'invited'` 状态管理

7. **权限缓存**：
   - 用户登录后将 (role, scope, permissions) 缓存到 Redis
   - TTL 5 分钟，权限变更时主动清除
   - 减少每次请求的数据库查询

8. **Scope 验证增强**：
   - 分配角色时验证 scope 中的 department_id/dataset_ids 存在
   - 防止无效 scope 导致权限检查失败

### 低优先级（v2）

9. **SSO 集成**：
   - `users.password_hash` 改为 nullable
   - 添加 `users.identity_provider` 字段（local/oidc/saml）
   - 实现 OIDC/SAML 端点

10. **多设备管理**：
    - `refresh_tokens.device_fingerprint` 字段
    - 用户可查看/撤销所有设备的 session

11. **user_departments.is_primary 约束**：
    - 每个用户最多一个 `is_primary=true` 的部门
    - 使用 partial unique index 或触发器实现

---

## 测试建议

### 手动验收（Phase 2 完成后执行）

```bash
# 1. 启动服务
docker compose up -d
cd backend
uv run uvicorn app.main:app --reload

# 2. 登录（使用 Phase 1 种子数据）
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_slug": "demo",
    "email": "admin@demo.com",
    "password": "demo123456"
  }'
# 预期：返回 access_token + refresh_token + user info

# 3. 获取当前用户信息
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer <access_token>"
# 预期：返回用户详情 + 角色 + 部门

# 4. 列出用户
curl http://localhost:8000/api/v1/users \
  -H "Authorization: Bearer <access_token>"
# 预期：返回 3 个用户（admin, sales, finance）

# 5. 创建新用户
curl -X POST http://localhost:8000/api/v1/users \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@demo.com",
    "display_name": "Test User",
    "password": "testpass123",
    "department_ids": [],
    "role_ids": [],
    "is_tenant_admin": false
  }'
# 预期：返回新用户信息

# 6. 列出角色
curl http://localhost:8000/api/v1/roles \
  -H "Authorization: Bearer <access_token>"
# 预期：返回 5 个系统角色

# 7. 列出权限
curl http://localhost:8000/api/v1/roles/permissions \
  -H "Authorization: Bearer <access_token>"
# 预期：返回 19 条权限

# 8. 列出部门
curl http://localhost:8000/api/v1/departments \
  -H "Authorization: Bearer <access_token>"
# 预期：返回 2 个部门（Sales, Finance）

# 9. 测试权限拒绝（使用 viewer 角色登录）
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_slug": "demo",
    "email": "finance@demo.com",
    "password": "demo123456"
  }'
# 获取 finance 用户的 token

curl -X POST http://localhost:8000/api/v1/users \
  -H "Authorization: Bearer <finance_token>" \
  -H "Content-Type: application/json" \
  -d '{"email": "new@demo.com", ...}'
# 预期：403 Permission denied (finance 用户只有 viewer 角色，无 write:user 权限)

# 10. 测试 RLS 隔离（尝试跨租户访问）
# 创建第二个租户（需手动执行 SQL 或扩展 seed 脚本）
# 使用 tenant1 的 token 访问 tenant2 的用户
# 预期：返回空列表或 404（RLS 阻止）
```

### 自动化测试（Phase 3 添加）

```python
# tests/test_auth.py
async def test_login_success():
    response = await client.post("/api/v1/auth/login", json={
        "tenant_slug": "demo",
        "email": "admin@demo.com",
        "password": "demo123456"
    })
    assert response.status_code == 200
    assert "access_token" in response.json()

async def test_login_invalid_credentials():
    response = await client.post("/api/v1/auth/login", json={
        "tenant_slug": "demo",
        "email": "admin@demo.com",
        "password": "wrongpass"
    })
    assert response.status_code == 401
    assert response.json()["code"] == "auth.invalid_credentials"

# tests/test_permissions.py
async def test_permission_check_admin_bypass():
    service = PermissionService(db)
    admin_user = await get_user_by_email("admin@demo.com")
    assert await service.check(admin_user, "delete", "user") == True

async def test_permission_check_scope_department():
    service = PermissionService(db)
    sales_user = await get_user_by_email("sales@demo.com")
    sales_dept = await get_department_by_name("Sales")
    finance_dept = await get_department_by_name("Finance")
    
    # sales 用户有 Sales 部门的 editor 角色
    assert await service.check(sales_user, "write", "record", 
                               MockRecord(department_id=sales_dept.id)) == True
    assert await service.check(sales_user, "write", "record",
                               MockRecord(department_id=finance_dept.id)) == False
```

---

## 给 Phase 3 的上下文摘要（≤500字）

Phase 2 已完成认证、用户、角色、权限、部门的完整 CRUD API 和 RBAC 权限系统。

**认证系统**：
- 登录流程：验证 tenant + email + password（Argon2id）→ 生成 JWT access token (15min) + 不透明 refresh token (30d)。
- JWT claims 包含 user_id, tenant_id, department_ids, roles, is_admin。
- 中间件 `TenantContextMiddleware` 在每个请求前从 JWT 提取 tenant_id 并执行 `SET LOCAL app.tenant_id`，确保 RLS 生效。
- `/auth/refresh` 和 `/auth/logout` 暂时返回 "not_implemented"（Phase 3 实现）。

**RBAC 权限系统**：
- `PermissionService.check(user, action, resource_type, resource_obj)` 实现完整权限解析算法。
- 支持 scope 过滤：空 scope = 全租户，`department_id` = 限定部门，`dataset_ids` = 限定数据集。
- `require_perm(action, resource_type)` 依赖注入工厂，在路由层强制权限检查。
- tenant_admin 自动绕过所有权限检查。
- **`compute_ai_access(user)`** - 计算 AI 查询的访问约束（Phase 2 补充）：
  - 返回 `AIAccessBundle(dataset_ids, dept_ids, allowed_sensitivities)`
  - 敏感度级别规则：
    - tenant_admin / dataset_admin → 全部 4 个级别
    - editor / viewer / ai_user → public + internal
    - 其他角色 → 仅 public

**API 端点**：
- `/api/v1/auth/*` - 登录、获取当前用户、修改密码。
- `/api/v1/users/*` - 用户 CRUD + 角色分配/撤销（支持 department_id 过滤）。
- `/api/v1/roles/*` - 角色 CRUD（系统角色禁止修改/删除）+ 全局权限列表。
- `/api/v1/departments/*` - 部门 CRUD（支持树形结构，parent_id 过滤）。

**数据模型**：
- 所有模型使用 SQLAlchemy 2.0 风格（`Mapped[]` + `mapped_column`）。
- Mixin：TimestampMixin, TenantMixin, SoftDeleteMixin。
- 关系：User ↔ Department (多对多), User ↔ Role (多对多 + scope), Role ↔ Permission (多对多)。

**错误处理**：
- 统一 `APIError` 基类，12 个具体错误类（401/403/404/409/422/429/500）。
- 全局异常处理器返回 `{code, message, detail?}` JSON。
- structlog 记录完整错误上下文。

**Phase 3 关键任务**：
1. 实现 refresh token 持久化（`refresh_tokens` 表 + 旋转逻辑）。
2. 实现 `/auth/refresh` 和 `/auth/logout` 端点（含 Redis 黑名单）。
3. 添加速率限制（slowapi）和账户锁定。
4. 实现审计日志（`audit_logs` 表 + SQLAlchemy event listener）。
5. 添加自动化测试（pytest + httpx）。

**验收命令**：启动服务后用 curl 测试登录、权限检查、RLS 隔离（见上方测试建议）。
