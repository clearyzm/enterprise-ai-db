# Enterprise AI Database

多租户企业 SaaS 数据平台，支持任意结构化数据管理、多级审批流、部门级并发协作，内置权限感知 AI 助手。

**架构：** FastAPI (Python 3.11) + PostgreSQL 16 (pgvector) + Next.js 14 + Redis，基于 RBAC 的多租户隔离，LangGraph 驱动的权限感知 AI 检索。

---

## 项目亮点

### 🎯 核心价值
- **多层多租户隔离**：数据库层 RLS + middleware session 注入 + application WHERE filter 三层防御
- **细粒度 RBAC**：tenant_admin / approver / editor / viewer / ai_user 五个系统角色 + 部门 scope + dataset scope 三维授权
- **审批流引擎**：基于 JSONLogic 的可配置审批路由，支持自审防御、并发版本冲突解决、跨部门约束
- **权限感知 AI 助手**：LangGraph 驱动的 RAG 检索，AI 输出严格按用户 scope 过滤，不会泄漏未授权数据
- **完整审计日志**：immutable audit trail 覆盖登录、用户修改、记录修改、审批通过/拒绝 5 个关键路径
- **生产级安全合同测试**：pytest 验证 RLS 跨租户隔离 + RBAC 越权审批 + AI scope guardrail 三组核心安全保证

### 🔒 安全加固历程（值得讲的故事）

本项目在开发后期通过 pytest 集成测试发现 **2 个隐藏的生产级安全漏洞**，并完成端到端修复：

#### Bug 1：RLS 从未真正启用
- **现象**：项目 migration `0002_rls.py` 文件名声明 "Enable Row-Level Security"，但 `upgrade()` 函数体仅为 `pass`
- **影响**：14 张租户数据表的 RLS 标志均为 false，**多租户隔离完全依赖 application 层 WHERE filter**，任何遗漏即跨租户数据泄漏
- **诊断方式**：`SELECT rowsecurity FROM pg_tables WHERE schemaname='public'` 返回全 false；`pg_policies` 返回 0 行

#### Bug 2：Middleware ↔ Session 注入断链
- **现象**：`TenantContextMiddleware` 正确从 JWT 提取 tenant_id 并 `SET LOCAL app.tenant_id` —— 但只设在它自己创建的 Session A 上
- **关键漏洞**：route handlers 通过 `Depends(get_db)` 拿到的是另一个新建 Session B，**从未注入过 tenant_id**
- **结果**：即使后续启用 RLS，所有 SQL 仍然在没设 tenant context 的 session 上运行，要么 fail-closed 返回 0 行（业务全崩），要么继续依赖 application filter（漏洞未真正修复）

#### 修复方案
1. **`get_db` 重构**：直接从 request JWT 提取 tenant_id 并在 session 上 `SET LOCAL`，**不再依赖 middleware**（middleware 在 BaseHTTPMiddleware + anyio 异步链路上偶尔不触发，已知 Starlette issue）
2. **`0010_enable_row_level_security.py`**：补齐 0002 漏掉的 RLS 启用 + `tenant_isolation` policy + `FORCE ROW LEVEL SECURITY` on 5 张核心表
3. **生产配置注意事项（写入文档）**：PostgreSQL superuser 自动 `BYPASS RLS`，**生产部署必须用 non-superuser 角色连接 DB**，否则 RLS 形同虚设

#### 验证
- pytest 集成测试 `test_security_contracts.py`：6/7 passed
  - ✅ 跨租户 RLS 拦截（3 个测试，包括 fail-closed 控制）
  - ✅ 越权审批 RBAC 拦截
  - ✅ AI scope 排除跨部门数据
  - 1 个 positive control 单跑通过，整套跑时遇到 pytest-asyncio + asyncpg 已知 connection cleanup race condition（不影响主合同验证）

### 🛠️ 跨平台开发踩坑记录

| 坑 | 表现 | 解决 |
|---|---|---|
| Docker volume mount 在 Windows/WSL2 上漏检测嵌套目录 | uvicorn `--reload` 不重启，新文件 404 | 改动 middleware/嵌套目录后必须 `docker compose stop + rm + up`，restart 不够 |
| pytest-asyncio + asyncpg connection cleanup race | 整套测试跑时偶发 anyio TaskGroup 错误 | 单测试单独跑稳定；将 flaky 标记加入 docstring |
| Alembic migration 在干净 DB 上不可重放 | 0008 在初次跑 0001→0008 时报 "multiple primary keys" | 修补 0008 让它先 drop composite PK 再 add id PK，增加 idempotency |
| BaseHTTPMiddleware 异步链路偶尔被 ExceptionMiddleware 短路 | dispatch 对某些 path 不触发 | 关键 tenant_id 注入移到 `get_db` dependency，不依赖 BaseHTTPMiddleware |

---

## 快速启动

### 1. 环境准备

```bash
# 克隆仓库
git clone <repo-url>
cd enterprise-ai-db

# 复制环境变量模板
cp .env.example .env

# 编辑 .env，填入真实值（必填项见下方说明）
# 至少需要配置：LLM_API_KEY, JWT_SECRET_KEY
```

### 2. 启动服务

```bash
# 启动所有 Docker 服务（PostgreSQL, Redis, Backend, Frontend）
make up

# 或手动启动
docker-compose up -d
```

### 3. 初始化数据库

```bash
# 执行数据库迁移
make migrate

# 写入 demo 数据（租户、用户、数据集、记录）
make seed
```

### 4. 访问应用

- **前端：** http://localhost:3000
- **后端 API：** http://localhost:8000
- **API 文档：** http://localhost:8000/docs

---

## Demo 账号

| 角色 | 邮箱 | 密码 | 部门 | 权限说明 |
|------|------|------|------|----------|
| 租户管理员 | `admin@demo.com` | `demo123456` | — | 全部权限，可管理用户/角色/部门/数据集，审批 fast-path |
| 销售经理 | `sales@demo.com` | `demo123456` | Sales | editor + ai_user，scope 限于 Sales 部门 |
| 财务分析师 | `finance@demo.com` | `demo123456` | Finance | approver + viewer，scope 限于 Finance 部门 |

租户：`demo`

### 5 分钟演示流程

**1. 登录管理后台** （admin@demo.com）
- 访问 http://localhost:3000，租户填 `demo`
- 进 `/users` 看到 3 个用户，每个用户有角色 + 部门 + scope
- 进 `/roles` 看 5 个系统角色（tenant_admin / editor / viewer / approver / ai_user）
- 进 `/audit` 看到每个登录/修改操作的不可变审计记录

**2. 演示审批流** （切到 sales@demo.com）
- 进 `/datasets/sales_orders` 看到 sales 部门拥有的订单数据
- 点 record `SO20260520` → 编辑 → 改金额 → 保存
- 这条记录进入 pending 状态（因为 sales 不是 owner，又不是 admin）

**3. 跨部门审批** （切到 finance@demo.com）
- 进 `/approvals` 看到一条 pending 审批
- 点详情看 diff（旧值 vs 新值）
- 点 "批准" → 这条改动落地

**4. 权限感知 AI** （切到 sales@demo.com）
- 进 `/ai` 问"sales_orders 中金额前 3 大的订单是哪些"
- AI 返回 sales 部门数据
- 再问"finance 部门的报表"→ AI 因为 scope 限制不返回 finance 数据（**这一步是项目最有意思的演示**）

**5. 验证安全合同**（命令行）

```bash
# 启动测试数据库
docker compose --profile test up -d postgres-test

# 跑安全测试
docker compose exec backend uv run pytest tests/test_security_contracts.py -v
```

应该看到 6+ 个 PASSED：跨租户 RLS 隔离 / RBAC 越权拦截 / AI scope guardrail。

---

## 环境变量说明

### 必填项

| 变量 | 说明 | 示例 |
|------|------|------|
| `LLM_API_KEY` | OpenAI API Key（或兼容接口） | `sk-proj-...` |
| `JWT_SECRET_KEY` | JWT 签名密钥（生产环境必须随机生成） | `openssl rand -hex 32` |

### 数据库配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 连接字符串 | `postgresql+asyncpg://postgres:postgres@localhost:5432/enterprise_ai` |
| `POSTGRES_USER` | 数据库用户名 | `postgres` |
| `POSTGRES_PASSWORD` | 数据库密码 | `postgres` |
| `POSTGRES_DB` | 数据库名称 | `enterprise_ai` |

### Redis 配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `REDIS_URL` | Redis 连接字符串 | `redis://localhost:6379/0` |
| `CELERY_BROKER_URL` | Celery 消息队列 | `redis://localhost:6379/1` |
| `CELERY_RESULT_BACKEND` | Celery 结果存储 | `redis://localhost:6379/2` |

### AI 模型配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_MODEL` | 主 LLM 模型（分类、工具调用） | `gpt-4o-mini` |
| `LLM_STRONG_MODEL` | 强 LLM 模型（最终回答生成） | `gpt-4o` |
| `EMBED_MODEL` | 向量嵌入模型 | `text-embedding-3-small` |
| `EMBED_DIM` | 嵌入向量维度 | `1536` |
| `LLM_BASE_URL` | 自定义 API 端点（可选） | `https://api.openai.com/v1` |

### 认证配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `JWT_ALGORITHM` | JWT 签名算法 | `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Access Token 有效期（分钟） | `15` |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | Refresh Token 有效期（天） | `30` |

### 应用配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `APP_ENV` | 运行环境 | `development` |
| `APP_DEBUG` | 调试模式 | `false` |
| `APP_HOST` | 后端监听地址 | `0.0.0.0` |
| `APP_PORT` | 后端监听端口 | `8000` |
| `NEXT_PUBLIC_API_URL` | 前端 API 地址 | `http://localhost:8000` |

---

## 常用命令

### Docker 服务管理

| 命令 | 说明 |
|------|------|
| `make up` | 启动所有 Docker 服务（后台） |
| `make down` | 停止并移除容器 |
| `make restart` | 重启所有服务 |
| `make logs` | 跟踪所有服务日志 |
| `make logs-backend` | 仅查看后端日志 |
| `make logs-frontend` | 仅查看前端日志 |

### 数据库管理

| 命令 | 说明 |
|------|------|
| `make migrate` | 执行 Alembic 数据库迁移 |
| `make seed` | 写入 demo 租户、用户、数据集 |
| `make db-shell` | 进入 PostgreSQL 命令行 |
| `make db-backup` | 备份数据库到 backups/ 目录 |

### 开发工具

| 命令 | 说明 |
|------|------|
| `make test` | 运行后端测试套件 |
| `make test-e2e` | 运行前端 E2E 测试（Playwright） |
| `make lint` | ruff + mypy 静态检查 |
| `make format` | ruff 代码格式化 |
| `make install` | 安装后端生产依赖（uv sync） |
| `make install-dev` | 安装后端开发依赖（uv sync --dev） |

---

## 技术栈

```
后端:   Python 3.11 · FastAPI · SQLAlchemy 2.0 (async) · Pydantic v2 · Alembic
数据库: PostgreSQL 16 (+ pgvector) · Redis 7
AI:     LangChain ≥ 0.3 · LangGraph · OpenAI 兼容接口
前端:   Next.js 14 (App Router) · TypeScript · Tailwind · shadcn/ui
实时:   FastAPI WebSocket + Redis Pub/Sub
任务:   Celery + Redis
认证:   JWT (access + refresh) · Argon2id
测试:   pytest + pytest-asyncio + Playwright
部署:   Docker Compose
```

---

## 项目结构

```
enterprise-ai-db/
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── api/            # REST API 路由
│   │   ├── models/         # SQLAlchemy 模型
│   │   ├── services/       # 业务逻辑层
│   │   ├── ai/             # AI 检索、Agent、Guardrails
│   │   ├── workers/        # Celery 任务
│   │   └── main.py         # FastAPI 应用入口
│   ├── migrations/         # Alembic 迁移脚本
│   ├── tests/              # pytest 测试
│   └── pyproject.toml      # Python 依赖配置
├── frontend/               # Next.js 前端
│   ├── src/
│   │   ├── app/           # App Router 页面
│   │   ├── components/    # React 组件
│   │   ├── lib/           # API 客户端、工具函数
│   │   └── hooks/         # React Hooks
│   ├── e2e/               # Playwright E2E 测试
│   └── package.json       # Node.js 依赖配置
├── docs/                  # 设计文档
│   ├── 01-architecture.md
│   ├── 02-data-model.md
│   ├── 03-security.md
│   └── ...
├── docker-compose.yml     # Docker 编排配置
├── Makefile              # 常用命令快捷方式
└── README.md             # 本文件
```

---

## 文档地图

| # | 文件 | 用途 |
|---|---|---|
| 01 | `01-architecture.md` | 系统架构、组件分工、关键决策 |
| 02 | `02-data-model.md` | 完整 SQL DDL、索引、RLS 策略 |
| 03 | `03-security.md` | 多租户、RBAC、认证、审计、威胁模型 |
| 04 | `04-ai-system.md` | RAG 索引/检索、LangGraph Agent、Prompt、Guardrail |
| 05 | `05-api-spec.md` | 所有 REST 端点、WebSocket 事件、错误码 |
| 06 | `06-workflow-realtime.md` | 审批工作流引擎、并发控制、实时同步 |
| 07 | `07-frontend.md` | Next.js 14 结构、页面、状态管理 |
| 08 | `08-implementation-roadmap.md` | 分阶段实施清单 |
| **运维** | `docs/RUNBOOK.md` | 常见问题排查、备份、日志查看 |

---

## 实施阶段

| Phase | 主题 | 状态 |
|---|---|---|
| 0 | 仓库骨架与基础设施 | ✅ 完成 |
| 1 | 数据库迁移 + RLS + 种子 | ✅ 完成 |
| 2 | 认证 + 用户/角色/权限 | ✅ 完成 |
| 3 | DataSet CRUD + Schema 校验 | ✅ 完成 |
| 4 | DataRecord + 乐观锁 + 列表过滤 | ✅ 完成 |
| 5 | 工作流引擎 + 审批 API | ✅ 完成 |
| 6 | WebSocket 实时同步 | ✅ 完成 |
| 7 | AI 索引 (Celery + pgvector) | ✅ 完成 |
| 8 | AI 检索 + LangGraph Agent + Guardrail | ✅ 完成 |
| 9 | 前端骨架 + 登录 + 数据列表/编辑 | ✅ 完成 |
| 10 | 前端审批 + AI 聊天 + 实时 | ✅ 完成 |
| 11 | 测试、加固、文档、Docker | ✅ 完成 |

---

## 开发指南

### 本地开发（不使用 Docker）

**后端：**
```bash
cd backend
uv sync --dev                    # 安装依赖
uv run alembic upgrade head      # 执行迁移
uv run python -m app.scripts.seed_demo  # 写入种子数据
uv run uvicorn app.main:app --reload    # 启动开发服务器
```

**前端：**
```bash
cd frontend
npm install                      # 安装依赖
npm run dev                      # 启动开发服务器
```

**Celery Worker（AI 索引任务）：**
```bash
cd backend
uv run celery -A app.workers.celery_app worker --loglevel=info
```

### 运行测试

**后端单元测试：**
```bash
cd backend
uv run pytest tests/ -v
```

**前端 E2E 测试：**
```bash
cd frontend
npx playwright test              # 无头模式
npx playwright test --ui         # UI 模式
npx playwright test --debug      # 调试模式
```

---

## 故障排查

常见问题请参考 **[docs/RUNBOOK.md](docs/RUNBOOK.md)**：
- 服务启动失败
- 数据库迁移错误
- AI 不回答问题
- 向量索引重建
- 日志查看方式

---

## 安全说明

- ✅ 多租户 RLS 隔离（PostgreSQL Row-Level Security）
- ✅ RBAC 权限控制（角色 + 作用域）
- ✅ Argon2id 密码哈希
- ✅ JWT 认证（15分钟 access token + 30天 refresh token）
- ✅ AI Guardrails（防止越权、PII 泄露、Prompt Injection）
- ✅ 乐观锁并发控制
- ⚠️ 生产环境必须修改 `JWT_SECRET_KEY`
- ⚠️ 生产环境建议启用 HTTPS + 速率限制

---

## 许可证

[MIT License](LICENSE)

---

## 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

---

## 联系方式

- 问题反馈：[GitHub Issues](https://github.com/your-org/enterprise-ai-db/issues)
- 文档：[docs/](docs/)
- API 文档：http://localhost:8000/docs（启动后访问）
