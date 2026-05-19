# Permission Service 补丁说明

## 需要添加的内容

### 1. 在文件开头添加 import 和 dataclass

在 `permission_service.py` 第 6 行后添加：

```python
from dataclasses import dataclass
```

在 `logger = structlog.get_logger(__name__)` 后添加：

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

### 2. 在 PermissionService 类末尾添加两个方法

在 `get_accessible_department_ids()` 方法后添加：

```python
    async def compute_ai_access(self, user: User) -> AIAccessBundle:
        """Compute AI access constraints for user.
        
        Determines which datasets, departments, and sensitivity levels
        the user can access during AI query processing.
        
        Args:
            user: User object (with loaded user_roles)
        
        Returns:
            AIAccessBundle with dataset_ids, dept_ids, and allowed_sensitivities
        
        Sensitivity level rules:
            - tenant_admin / dataset_admin → ["public", "internal", "confidential", "restricted"]
            - editor / viewer / ai_user    → ["public", "internal"]
            - other roles                  → ["public"]
        
        Example:
            >>> service = PermissionService(db)
            >>> access = await service.compute_ai_access(user)
            >>> # Use access.dataset_ids, access.dept_ids, access.allowed_sensitivities
            >>> # to filter chunks in AI retrieval query
        """
        # Get accessible datasets and departments
        dataset_ids = await self.get_accessible_dataset_ids(user)
        dept_ids = await self.get_accessible_department_ids(user)
        
        # Determine allowed sensitivity levels based on user's highest role
        allowed_sensitivities = self._compute_allowed_sensitivities(user)
        
        logger.debug(
            "permission.compute_ai_access",
            user_id=str(user.id),
            dataset_count=len(dataset_ids) if dataset_ids else "all",
            dept_count=len(dept_ids) if dept_ids else "all",
            sensitivities=allowed_sensitivities,
        )
        
        return AIAccessBundle(
            dataset_ids=dataset_ids,
            dept_ids=dept_ids,
            allowed_sensitivities=allowed_sensitivities,
        )

    def _compute_allowed_sensitivities(self, user: User) -> list[str]:
        """Compute allowed sensitivity levels based on user's roles.
        
        Args:
            user: User object (with loaded user_roles)
        
        Returns:
            List of allowed sensitivity levels
        
        Rules:
            - tenant_admin / dataset_admin → all levels (public, internal, confidential, restricted)
            - editor / viewer / ai_user    → public, internal
            - other roles                  → public only
        """
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

## 手动操作步骤

1. 打开文件：`D:\projects\enterprise-ai-db\backend\app\services\permission_service.py`

2. 在第 6 行（`from typing import Any`）后添加：
   ```python
   from dataclasses import dataclass
   ```

3. 在第 16 行（`logger = structlog.get_logger(__name__)`）后添加 `AIAccessBundle` dataclass

4. 在文件末尾（`get_accessible_department_ids()` 方法后）添加两个新方法：
   - `compute_ai_access()`
   - `_compute_allowed_sensitivities()`

5. 保存文件

## 验证

修改完成后，运行：
```bash
cd D:\projects\enterprise-ai-db\backend
uv run python -c "from app.services.permission_service import AIAccessBundle, PermissionService; print('✅ Import successful')"
```

如果没有错误，说明修改成功。
