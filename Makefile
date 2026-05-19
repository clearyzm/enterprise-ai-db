.PHONY: up down logs migrate seed test lint install install-dev shell-backend shell-db

# -----------------------------------------------------------------------
# Docker Compose — 主环境
# -----------------------------------------------------------------------

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

restart:
	docker compose restart

ps:
	docker compose ps

# -----------------------------------------------------------------------
# 数据库迁移与种子（在 backend 容器内执行）
# -----------------------------------------------------------------------

migrate:
	docker compose exec backend uv run alembic upgrade head

migrate-down:
	docker compose exec backend uv run alembic downgrade -1

migrate-history:
	docker compose exec backend uv run alembic history --verbose

seed:
	docker compose exec backend uv run python -m app.scripts.seed_demo

# -----------------------------------------------------------------------
# 测试（使用隔离的 docker-compose.test.yml，D4）
# -----------------------------------------------------------------------

test:
	docker compose -f docker-compose.test.yml up -d
	sleep 3
	uv run pytest backend/ --tb=short -q
	docker compose -f docker-compose.test.yml down -v

test-fast:
	uv run pytest backend/ --tb=short -q

# -----------------------------------------------------------------------
# 静态检查
# -----------------------------------------------------------------------

lint:
	cd backend && uv run ruff check .
	cd backend && uv run mypy app/

lint-fix:
	cd backend && uv run ruff check . --fix

# -----------------------------------------------------------------------
# 依赖管理（D2 · uv）
# -----------------------------------------------------------------------

install:
	cd backend && uv sync

install-dev:
	cd backend && uv sync --dev

# -----------------------------------------------------------------------
# 调试工具
# -----------------------------------------------------------------------

shell-backend:
	docker compose exec backend bash

shell-db:
	docker compose exec postgres psql -U postgres -d enterprise_ai

build:
	docker compose build

build-no-cache:
	docker compose build --no-cache
