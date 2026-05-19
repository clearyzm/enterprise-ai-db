"""Seed demo tenant with users, roles, and sample dataset.

Usage:
    docker compose exec backend uv run python -m app.scripts.seed_demo

Creates:
- Tenant: slug='demo', name='Demo Corporation'
- Users: admin@demo.com, sales@demo.com, finance@demo.com (password: demo123456)
- Departments: Sales, Finance
- System roles: tenant_admin, editor, viewer, approver, ai_user
- Dataset: sales_orders with JSON schema
"""
import asyncio
import sys
from uuid import UUID

from argon2 import PasswordHasher
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import async_session_maker

ph = PasswordHasher()


async def seed_demo() -> None:
    """Main seed function."""
    async with async_session_maker() as session:
        # Check if demo tenant already exists
        result = await session.execute(
            text("SELECT id FROM tenants WHERE slug = 'demo'")
        )
        existing = result.scalar_one_or_none()
        if existing:
            print("❌ Demo tenant already exists. Skipping seed.")
            return

        print("🌱 Seeding demo tenant...")

        # ============ CREATE TENANT ============
        tenant_result = await session.execute(
            text("""
                INSERT INTO tenants (slug, name, status, ai_profile, settings)
                VALUES ('demo', 'Demo Corporation', 'active', 
                        '{"company_persona": "A mid-sized enterprise", "domain_glossary": []}'::jsonb,
                        '{}'::jsonb)
                RETURNING id
            """)
        )
        tenant_id = tenant_result.scalar_one()
        print(f"✅ Created tenant: {tenant_id}")

        # Set tenant context for RLS
        await session.execute(
            text(f"SET LOCAL app.tenant_id = '{tenant_id}'")
        )

        # ============ CREATE DEPARTMENTS ============
        dept_sales_result = await session.execute(
            text("""
                INSERT INTO departments (tenant_id, name, code)
                VALUES (:tid, 'Sales', 'SALES')
                RETURNING id
            """).bindparams(tid=tenant_id)
        )
        dept_sales_id = dept_sales_result.scalar_one()

        dept_finance_result = await session.execute(
            text("""
                INSERT INTO departments (tenant_id, name, code)
                VALUES (:tid, 'Finance', 'FIN')
                RETURNING id
            """).bindparams(tid=tenant_id)
        )
        dept_finance_id = dept_finance_result.scalar_one()
        print(f"✅ Created departments: Sales ({dept_sales_id}), Finance ({dept_finance_id})")

        # ============ CREATE USERS ============
        password_hash = ph.hash("demo123456")

        users = [
            ("admin@demo.com", "Admin User", True, None),
            ("sales@demo.com", "Sales Manager", False, dept_sales_id),
            ("finance@demo.com", "Finance Analyst", False, dept_finance_id),
        ]

        user_ids = {}
        for email, display_name, is_admin, primary_dept in users:
            user_result = await session.execute(
                text("""
                    INSERT INTO users (tenant_id, email, password_hash, display_name, 
                                       status, is_tenant_admin)
                    VALUES (:tid, :email, :pwd, :name, 'active', :is_admin)
                    RETURNING id
                """).bindparams(
                    tid=tenant_id,
                    email=email,
                    pwd=password_hash,
                    name=display_name,
                    is_admin=is_admin,
                )
            )
            user_id = user_result.scalar_one()
            user_ids[email] = user_id

            # Assign to department
            if primary_dept:
                await session.execute(
                    text("""
                        INSERT INTO user_departments (user_id, department_id, is_primary)
                        VALUES (:uid, :did, true)
                    """).bindparams(uid=user_id, did=primary_dept)
                )

        print(f"✅ Created users: {', '.join(user_ids.keys())}")

        # ============ FETCH PERMISSIONS ============
        perm_result = await session.execute(
            text("SELECT id, action, resource_type FROM permissions")
        )
        permissions = {(row[1], row[2]): row[0] for row in perm_result.fetchall()}

        # ============ CREATE SYSTEM ROLES ============
        roles_config = {
            "tenant_admin": [
                ("read", "dataset"), ("write", "dataset"), ("manage", "dataset"),
                ("read", "record"), ("write", "record"), ("delete", "record"), ("approve", "record"),
                ("read", "user"), ("manage", "user"),
                ("read", "role"), ("manage", "role"),
                ("read", "department"), ("manage", "department"),
                ("read", "workflow"), ("manage", "workflow"),
                ("read", "tenant_settings"), ("manage", "tenant_settings"),
                ("read", "audit_log"),
                ("ai_query", "dataset"),
            ],
            "editor": [
                ("read", "dataset"), ("read", "record"), ("write", "record"),
            ],
            "viewer": [
                ("read", "dataset"), ("read", "record"),
            ],
            "approver": [
                ("read", "dataset"), ("read", "record"), ("approve", "record"),
            ],
            "ai_user": [
                ("read", "dataset"), ("read", "record"), ("ai_query", "dataset"),
            ],
        }

        role_ids = {}
        for role_name, perms in roles_config.items():
            role_result = await session.execute(
                text("""
                    INSERT INTO roles (tenant_id, name, description, is_system)
                    VALUES (:tid, :name, :desc, true)
                    RETURNING id
                """).bindparams(
                    tid=tenant_id,
                    name=role_name,
                    desc=f"System role: {role_name}",
                )
            )
            role_id = role_result.scalar_one()
            role_ids[role_name] = role_id

            # Assign permissions
            for action, resource_type in perms:
                perm_id = permissions.get((action, resource_type))
                if perm_id:
                    await session.execute(
                        text("""
                            INSERT INTO role_permissions (role_id, permission_id)
                            VALUES (:rid, :pid)
                        """).bindparams(rid=role_id, pid=perm_id)
                    )

        print(f"✅ Created roles: {', '.join(role_ids.keys())}")

        # ============ ASSIGN ROLES TO USERS ============
        # admin → tenant_admin (全租户)
        await session.execute(
            text("""
                INSERT INTO user_roles (user_id, role_id, scope)
                VALUES (:uid, :rid, '{}'::jsonb)
            """).bindparams(uid=user_ids["admin@demo.com"], rid=role_ids["tenant_admin"])
        )

        # sales → editor + ai_user (限 Sales 部门)
        for role_name in ["editor", "ai_user"]:
            scope_json = '{' + f'"department_id": "{dept_sales_id}"' + '}'
            await session.execute(
                text(f"""
                    INSERT INTO user_roles (user_id, role_id, scope)
                    VALUES ('{user_ids["sales@demo.com"]}', '{role_ids[role_name]}', '{scope_json}'::jsonb)
                """)
            )

        # finance → viewer (限 Finance 部门)
        scope_json = '{' + f'"department_id": "{dept_finance_id}"' + '}'
        await session.execute(
            text(f"""
                INSERT INTO user_roles (user_id, role_id, scope)
                VALUES ('{user_ids["finance@demo.com"]}', '{role_ids["viewer"]}', '{scope_json}'::jsonb)
            """)
        )

        print("✅ Assigned roles to users")

        # ============ CREATE SAMPLE DATASET ============
        schema_json = '{"type": "object", "required": ["order_no", "customer", "amount", "status"], "properties": {"order_no": {"type": "string"}, "customer": {"type": "string", "maxLength": 200}, "amount": {"type": "number", "minimum": 0}, "status": {"type": "string", "enum": ["draft", "paid", "cancelled"]}, "notes": {"type": "string"}}, "additionalProperties": false}'
        dataset_result = await session.execute(
            text(f"""
                INSERT INTO data_sets (tenant_id, owner_dept_id, name, description, schema,
                                       sensitivity, ai_indexed, created_by)
                VALUES ('{tenant_id}', '{dept_sales_id}', 'sales_orders', 'Sales order records',
                        $${schema_json}$$::jsonb, 'internal', true, '{user_ids["admin@demo.com"]}')
                RETURNING id
            """)
        )
        dataset_id = dataset_result.scalar_one()
        print(f"✅ Created dataset: sales_orders ({dataset_id})")
        await session.commit()
        print("🎉 Demo seed completed successfully!")


if __name__ == "__main__":
    asyncio.run(seed_demo())
