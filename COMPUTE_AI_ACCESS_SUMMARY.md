# compute_ai_access() 补充说明

## ✅ 已完成

### 1. 新增 AIAccessBundle dataclass

**位置**：`permission_service.py` 第 19-31 行

```python
@dataclass
class AIAccessBundle:
    """Bundle of access constraints for AI retrieval.
    
    Used to filter chunks/records during AI query processing.
    
    Attributes:
        dataset_ids: List of accessible dataset UUIDs (empty = all datasets in tenant)
        dept_ids: List of accessible department UUIDs (empty = all departments in tenant)
        allowed_sensitivities: List of allowed sensitivity levels (e.g., ["public", "internal"])
    """
    dataset_ids: list[UUID]
    dept_ids: list[UUID]
    allowed_sensitivities: list[str]
```

### 2. 新增 compute_ai_access() 方法

**位置**：`permission_service.py` 第 279-318 行

**方法签名**：
```python
async def compute_ai_access(self, user: User) -> AIAccessBundle
```

**实现逻辑**：
```python
# 1. 获取可访问的数据集 ID
dataset_ids = await self.get_accessible_dataset_ids(user)

# 2. 获取可访问的部门 ID
dept_ids = await self.get_accessible_department_ids(user)

# 3. 计算允许的敏感度级别
allowed_sensitivities = self._compute_allowed_sensitivities(user)

# 4. 返回 AIAccessBundle
return AIAccessBundle(
    dataset_ids=dataset_ids,
    dept_ids=dept_ids,
    allowed_sensitivities=allowed_sensitivities,
)
```

### 3. 新增 _compute_allowed_sensitivities() 辅助方法

**位置**：`permission_service.py` 第 320-344 行

**敏感度级别规则**：

| 用户角色 | 允许的敏感度级别 |
|---|---|
| tenant_admin | ["public", "internal", "confidential", "restricted"] |
| dataset_admin | ["public", "internal", "confidential", "restricted"] |
| editor / viewer / ai_user / approver | ["public", "internal"] |
| 其他角色 | ["public"] |

**实现代码**：
```python
def _compute_allowed_sensitivities(self, user: User) -> list[str]:
    # Tenant admins can access all sensitivity levels
    if user.is_tenant_admin:
        return ["public", "internal", "confidential", "restricted"]
    
    # Collect all role names
    role_names = {ur.role.name for ur in user.user_roles}
    
    # Check for high-privilege roles (dataset_admin)
    high_privilege_roles = {"dataset_admin"}
    if role_names & high_privilege_roles:
        return ["public", "internal", "confidential", "restricted"]
    
    # Check for standard roles (editor, viewer, ai_user)
    standard_roles = {"editor", "viewer", "ai_user", "approver"}
    if role_names & standard_roles:
        return ["public", "internal"]
    
    # Default: public only
    return ["public"]
```

---

## 📋 使用示例

### 在 AI 检索服务中使用

```python
from app.services.permission_service import PermissionService, AIAccessBundle
from app.deps import CurrentUser

async def ai_query(
    query: str,
    user: CurrentUser,
    db: AsyncSession,
):
    # 计算用户的 AI 访问权限
    perm_service = PermissionService(db)
    access: AIAccessBundle = await perm_service.compute_ai_access(user)
    
    # 构建检索查询，应用访问约束
    stmt = select(Chunk).where(
        Chunk.tenant_id == user.tenant_id,
    )
    
    # 过滤数据集
    if access.dataset_ids:  # 非空列表 = 有限制
        stmt = stmt.where(Chunk.dataset_id.in_(access.dataset_ids))
    
    # 过滤部门
    if access.dept_ids:  # 非空列表 = 有限制
        stmt = stmt.where(Chunk.department_id.in_(access.dept_ids))
    
    # 过滤敏感度
    stmt = stmt.where(Chunk.sensitivity.in_(access.allowed_sensitivities))
    
    # 执行向量检索
    chunks = await db.execute(stmt)
    
    # ... 继续 AI 处理
```

### 日志输出示例

```python
logger.debug(
    "permission.compute_ai_access",
    user_id=str(user.id),
    dataset_count=len(dataset_ids) if dataset_ids else "all",
    dept_count=len(dept_ids) if dept_ids else "all",
    sensitivities=allowed_sensitivities,
)
```

输出：
```json
{
  "event": "permission.compute_ai_access",
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "dataset_count": "all",
  "dept_count": 2,
  "sensitivities": ["public", "internal"]
}
```

---

## 🔍 设计要点

### 1. 空列表的语义

- `dataset_ids = []` → 用户可访问租户内**所有**数据集（无限制）
- `dept_ids = []` → 用户可访问租户内**所有**部门（无限制）
- `allowed_sensitivities = ["public"]` → 用户**仅**可访问 public 级别数据

### 2. AND 关系

三个约束条件是 **AND 关系**（交集）：
- 必须在允许的数据集内
- **且**必须在允许的部门内
- **且**必须在允许的敏感度级别内

### 3. 与 03-security.md 的对应

实现了文档 §9 数据敏感度分级的要求：

| 级别 | 含义 | RAG 默认行为 |
|---|---|---|
| `public` | 任意已登录用户可见 | 允许 AI 引用 |
| `internal` | 默认级别，按角色访问 | 允许 AI 引用，按用户权限过滤 |
| `confidential` | 财务/合同/HR 等 | 默认 AI **不引用**（除非用户具备高权限） |
| `restricted` | 个人敏感 / 法律强约束 | AI **绝不引用**（仅高权限用户） |

---

## 📊 测试场景

### 场景 1：tenant_admin 用户

```python
user = admin_user  # is_tenant_admin = True
access = await perm_service.compute_ai_access(user)

assert access.dataset_ids == []  # 所有数据集
assert access.dept_ids == []  # 所有部门
assert access.allowed_sensitivities == ["public", "internal", "confidential", "restricted"]
```

### 场景 2：editor 用户（Sales 部门）

```python
user = sales_user  # role: editor, dept: Sales
access = await perm_service.compute_ai_access(user)

assert access.dataset_ids == []  # 所有数据集（如果 scope 为空）
assert access.dept_ids == [sales_dept_id]  # 仅 Sales 部门
assert access.allowed_sensitivities == ["public", "internal"]
```

### 场景 3：viewer 用户（限定数据集）

```python
user = viewer_user  # role: viewer, scope: {dataset_ids: [ds1, ds2]}
access = await perm_service.compute_ai_access(user)

assert access.dataset_ids == [ds1_id, ds2_id]  # 仅限定的数据集
assert access.dept_ids == []  # 所有部门
assert access.allowed_sensitivities == ["public", "internal"]
```

### 场景 4：无角色用户

```python
user = no_role_user  # 没有任何角色
access = await perm_service.compute_ai_access(user)

assert access.dataset_ids == []  # 所有数据集（但会被其他权限检查拦截）
assert access.dept_ids == [user_dept_id]  # 用户自己的部门
assert access.allowed_sensitivities == ["public"]  # 仅 public
```

---

## ✅ 更新记录

- **PHASE_2_REPORT.md** 已更新：
  - 服务层说明中添加 `compute_ai_access` 方法
  - 代码行数更新为 344 行
  - 总代码量更新为 3,126 行
  - 添加敏感度级别规则说明

---

## 📝 后续集成（Phase 3+）

在 AI 检索服务中使用此方法：

1. **Phase 3**：实现基础 AI 查询端点
   - 使用 `compute_ai_access()` 获取访问约束
   - 在向量检索查询中应用约束

2. **Phase 4**：实现 LangGraph 工作流
   - 在 retrieval 节点中调用 `compute_ai_access()`
   - 确保所有 tool 调用都遵守权限约束

3. **Phase 5**：实现 guardrail 节点
   - 验证 AI 响应不包含超出权限的数据
   - 检测并阻止敏感度级别泄漏

---

**✅ compute_ai_access() 方法已完整实现并文档化！**
