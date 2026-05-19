"""Permission service — RBAC permission checking with scope filtering.

Implements the permission resolution algorithm from 03-security.md §4.
Checks if a user has permission to perform an action on a resource,
considering role assignments and scope constraints.
"""
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

logger = structlog.get_logger(__name__)


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


class PermissionService:
    """Service for checking user permissions with scope filtering."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def check(
        self,
        user: User,
        action: str,
        resource_type: str,
        resource_obj: Any | None = None,
    ) -> bool:
        """Check if user has permission to perform action on resource.
        
        Algorithm (from 03-security.md §4):
        1. If user.is_tenant_admin → return True (bypass)
        2. For each (role, scope) assigned to user:
            a. Check if role has permission (action, resource_type)
            b. If yes, check if scope matches resource_obj
            c. If both match → return True
        3. If no match found → return False
        
        Args:
            user: User object (with loaded user_roles, roles, permissions)
            action: Permission action (read/write/delete/approve/manage/ai_query)
            resource_type: Resource type (user/role/department/dataset/record/workflow/audit_log)
            resource_obj: Optional resource object for scope matching
        
        Returns:
            True if user has permission, False otherwise
        
        Example:
            >>> service = PermissionService(db)
            >>> has_perm = await service.check(user, "read", "dataset", dataset_obj)
        """
        # Tenant admins bypass all permission checks
        if user.is_tenant_admin:
            logger.debug(
                "permission.check.admin_bypass",
                user_id=str(user.id),
                action=action,
                resource_type=resource_type,
            )
            return True
        
        # Iterate through user's roles
        for user_role in user.user_roles:
            role = user_role.role
            scope = user_role.scope
            
            # Check if role has the required permission
            has_permission = False
            for permission in role.permissions:
                if permission.action == action and permission.resource_type == resource_type:
                    has_permission = True
                    break
            
            if not has_permission:
                continue
            
            # Check if scope matches resource
            if self._scope_matches(scope, resource_obj, user):
                logger.debug(
                    "permission.check.granted",
                    user_id=str(user.id),
                    action=action,
                    resource_type=resource_type,
                    role_name=role.name,
                    scope=scope,
                )
                return True
        
        # No matching permission found
        logger.debug(
            "permission.check.denied",
            user_id=str(user.id),
            action=action,
            resource_type=resource_type,
        )
        return False

    def _scope_matches(
        self,
        scope: dict[str, Any],
        resource_obj: Any | None,
        user: User,
    ) -> bool:
        """Check if scope constraints match the resource object.
        
        Scope types (from 03-security.md §3.4):
        - {} (empty): Full tenant access → always match
        - {"department_id": "<uuid>"}: Limited to specific department
        - {"dataset_ids": ["<uuid>", ...]}: Limited to specific datasets
        - {"department_id": "...", "dataset_ids": [...]}: Intersection
        
        Args:
            scope: JSONB scope dict from user_roles.scope
            resource_obj: Resource object to check (e.g., Dataset, Record)
            user: User object (for department membership validation)
        
        Returns:
            True if scope matches, False otherwise
        """
        # Empty scope = full tenant access
        if not scope:
            return True
        
        # If no resource object provided, can't do scope matching
        # (used for list endpoints where filtering happens in query)
        if resource_obj is None:
            return True
        
        # Check department_id constraint
        if "department_id" in scope:
            scope_dept_id = UUID(scope["department_id"])
            
            # Verify user belongs to this department (prevent scope forgery)
            user_dept_ids = [ud.department_id for ud in user.user_departments]
            if scope_dept_id not in user_dept_ids:
                logger.warning(
                    "permission.scope_mismatch.user_not_in_dept",
                    user_id=str(user.id),
                    scope_dept_id=str(scope_dept_id),
                )
                return False
            
            # Check if resource belongs to this department
            resource_dept_id = getattr(resource_obj, "department_id", None) or getattr(
                resource_obj, "owner_dept_id", None
            )
            if resource_dept_id and UUID(resource_dept_id) != scope_dept_id:
                return False
        
        # Check dataset_ids constraint
        if "dataset_ids" in scope:
            scope_dataset_ids = [UUID(ds_id) for ds_id in scope["dataset_ids"]]
            
            # Get resource's dataset_id (could be direct or via FK)
            resource_dataset_id = getattr(resource_obj, "dataset_id", None) or getattr(
                resource_obj, "id", None
            )
            
            if resource_dataset_id:
                if UUID(resource_dataset_id) not in scope_dataset_ids:
                    return False
            else:
                # Resource has no dataset association, scope doesn't match
                return False
        
        # All scope constraints matched
        return True

    async def get_accessible_dataset_ids(self, user: User) -> list[UUID]:
        """Get list of dataset IDs user can access based on roles and scopes.
        
        Used for filtering queries (e.g., list datasets, AI retrieval).
        
        Args:
            user: User object (with loaded user_roles)
        
        Returns:
            List of dataset UUIDs user can access (empty = all datasets in tenant)
        
        Example:
            >>> dataset_ids = await service.get_accessible_dataset_ids(user)
            >>> stmt = select(Dataset).where(Dataset.id.in_(dataset_ids))
        """
        # Tenant admins can access all datasets
        if user.is_tenant_admin:
            return []  # Empty list = no filtering needed
        
        accessible_dataset_ids: set[UUID] = set()
        has_full_access = False
        
        for user_role in user.user_roles:
            scope = user_role.scope
            
            # Empty scope = full tenant access
            if not scope:
                has_full_access = True
                break
            
            # Collect dataset_ids from scope
            if "dataset_ids" in scope:
                for ds_id in scope["dataset_ids"]:
                    accessible_dataset_ids.add(UUID(ds_id))
        
        # If user has any role with full tenant access, return empty list
        if has_full_access:
            return []
        
        return list(accessible_dataset_ids)

    async def get_accessible_department_ids(self, user: User) -> list[UUID]:
        """Get list of department IDs user can access based on roles and scopes.
        
        Args:
            user: User object (with loaded user_roles, user_departments)
        
        Returns:
            List of department UUIDs user can access (empty = all departments in tenant)
        """
        # Tenant admins can access all departments
        if user.is_tenant_admin:
            return []
        
        accessible_dept_ids: set[UUID] = set()
        has_full_access = False
        
        for user_role in user.user_roles:
            scope = user_role.scope
            
            # Empty scope = full tenant access
            if not scope:
                has_full_access = True
                break
            
            # Collect department_id from scope
            if "department_id" in scope:
                accessible_dept_ids.add(UUID(scope["department_id"]))
        
        # If user has any role with full tenant access, return empty list
        if has_full_access:
            return []
        
        # If no department constraints in any role, user can access their own departments
        if not accessible_dept_ids:
            return [ud.department_id for ud in user.user_departments]
        
        return list(accessible_dept_ids)

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
