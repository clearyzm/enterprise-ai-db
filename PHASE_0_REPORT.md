# PHASE_0_REPORT — 仓库骨架与基础设施

## 已实现清单

| 文件 | 状态 | 说明 |
|---|---|---|
| `README.md` | ✅ | 快速启动、命令表、阶段地图 |
| `.env.example` | ✅ | 全部 D1 字段（8 个 LLM/Embed）+ 注释 |
| `.gitignore` | ✅ | 密钥、构建产物、IDE 文件 |
| `Makefile` | ✅ | up/down/logs/migrate/seed/test/lint/install/install-dev |
| `docker-compose.yml` | ✅ | 5 服务全 healthcheck，D3 dev 模式 |
| `docker-compose.test.yml` | ✅ | 隔离测试库，tmpfs，端口 5433/6380（D4）|
| `backend/pyproject.toml` | ✅ | uv 格式（D2），ruff/mypy/pytest 配置 |
| `backend/Dockerfile` | ✅ | uv sync --frozen，开发挂载卷 |
| `backend/alembic.ini` | ✅ | URL 运行时注入，不写死密码 |
| `backend/app/__init__.py` | ✅ | 包标识 |
| `backend/app/config.py` | ✅ | D1 全部字段，SecretStr，model_validator |
| `backend/app/main.py` | ✅ | /health，structlog，lifespan 预留 |
| `backend/app/{api,models,schemas,services,ai,realtime,workers,utils,db,scripts}/__init__.py` | ✅ | 10 个子包占位，import 路径稳定 |
| `backend/migrations/env.py` | ✅ | asyncio 模式，Base.metadata 预留 |
| `backend/migrations/script.py.mako` | ✅ | mypy strict 注解模板 |
| `backend/tests/__init__.py` | ✅ | 测试包标识 |
| `backend/tests/conftest.py` | ✅ | AsyncClient fixture（ASGI，无网络） |
| `backend/tests/test_health.py` | ✅ | health 200 + 404 边界，2 条测试 |
| `frontend/package.json` | ✅ | Next.js 14.2，React 18，TanStack Query，Zustand，shadcn/ui 依赖 |
| `frontend/tsconfig.json` | ✅ | strict: true，@/ 路径别名 |
| `frontend/next.config.mjs` | ✅ | API proxy rewrite，图片域名 |
| `frontend/tailwind.config.ts` | ✅ | shadcn/ui CSS 变量槽预留 |
| `frontend/postcss.config.mjs` | ✅ | tailwindcss + autoprefixer |
| `frontend/src/app/globals.css` | ✅ | CSS 变量 light/dark 主题 |
| `frontend/src/app/layout.tsx` | ✅ | App Router 根 layout，Inter 字体 |
| `frontend/src/app/page.tsx` | ✅ | Placeholder（Phase 9 覆盖）|
| `frontend/Dockerfile.dev` | ✅ | node:20-alpine，npm ci，卷挂载 |
| `frontend/.eslintrc.json` | ✅ | next/core-web-vitals + strict TS rules |
| `.github/workflows/ci.yml` | ✅ | backend(ruff+mypy+migrate+pytest) + frontend(tsc+eslint) 并行 |

## 偏离文档的设计决策

| 决策 | 偏离原因 |
|---|---|
| `config.py` 增加 `EMBED_DIM` 白名单 validator（768/1024/1536/3072）| 文档未要求，但能在启动时提前拦截误配置，成本极低 |
| 前端目录使用 `src/app/`（有 src/）而非直接 `app/` | Next.js 14 官方推荐，shadcn/ui CLI 默认也在 src/ 下生成，后续 Phase 9 `npx shadcn-ui init` 无需调整 |
| `migrations/env.py` 对 `Base` 做 try/import（Phase 0 `db/base.py` 尚不存在）| 保持 `make migrate`（空迁移）在 Phase 0 可跑通，不因导入失败报错 |
| 补充 `alembic.ini` + `migrations/script.py.mako` | 任务卡仅列 `env.py`，但两者是 `alembic upgrade head` 运行的前提，必须同步交付 |

## 已知 TODO / 风险

- `backend/app/db/base.py`（含 `Base = DeclarativeBase()`）将在 Phase 1 创建；`env.py` 的 try/import 届时改为直接 import。
- `docker-compose.yml` 中 backend healthcheck 依赖 `curl`，Dockerfile 已安装；如换 distroless 镜像需改用 `wget` 或 httpx 脚本。
- 前端 CI job 依赖 `package-lock.json`（`npm ci`）；第一次 `npm install` 后需要把 lockfile 提交进仓库。
- `LLM_API_KEY` 在 CI 中 fallback 到 `sk-test-placeholder`，Phase 8 测试需要真实 key 或 mock，届时在 GitHub Secrets 配置。

## 测试通过率

Phase 0 包含 2 条测试：
- `test_health_returns_200` — happy path
- `test_unknown_route_returns_404` — 边界

两条均不依赖数据库，`AsyncClient(transport=ASGITransport(app=app))` 纯内存运行。

## 给 Phase 1 的上下文摘要（≤500字）

Phase 0 已交付完整仓库骨架。关键约定：

**目录结构**：后端在 `backend/`，入口 `app/main.py`，包管理 `uv`（`pyproject.toml` 无 poetry 块）。所有子包已建好 `__init__.py`，import 路径 `app.models.*`、`app.services.*` 等已可用。

**配置**：`app/config.py` 的 `get_settings()` 是全局单例（lru_cache），通过 `Settings(BaseSettings)` 从环境变量读取。数据库 URL 字段名 `DATABASE_URL`。LLM 分两组：生成模型（`LLM_*`）、嵌入模型（`EMBED_*`），均为 `SecretStr`。

**数据库**：Alembic 配置在 `backend/alembic.ini` + `migrations/env.py`。`env.py` 已预留 `from app.db.base import Base`（try/import），Phase 1 需创建 `app/db/base.py`（`Base = DeclarativeBase()`）和 `app/db/session.py`（async engine），随后把 try/import 改为正式 import。

**测试**：测试库隔离在 `docker-compose.test.yml`（postgres_test:5433, redis_test:6380）。`pyproject.toml [tool.pytest.ini_options]` 已注入所有测试环境变量，`conftest.py` 提供 `AsyncClient` fixture（Phase 1 需追加 `db_session` fixture）。

**Docker**：5 服务全 healthcheck，startup 顺序依赖链完整（postgres → redis → backend → frontend）。后端/前端均挂载源码卷，支持热重载。

**验收命令**：
```bash
cp .env.example .env  # 填 DATABASE_URL / JWT_SECRET_KEY / LLM_API_KEY
make up
curl http://localhost:8000/health   # {"status":"ok","version":"0.1.0"}
curl http://localhost:3000          # 200 HTML
make migrate                        # Alembic 空迁移通过
cd backend && uv sync --dev && uv run pytest --tb=short -q   # 2 passed
```
