# Enterprise AI Database

多租户企业 SaaS 数据平台，支持任意结构化数据管理、多级审批流、部门级并发协作，内置权限感知 AI 助手。

**架构：** FastAPI (Python 3.11) + PostgreSQL 16 (pgvector) + Next.js 14 + Redis，基于 RBAC 的多租户隔离，LangGraph 驱动的权限感知 AI 检索。

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

| 角色 | 邮箱 | 密码 | 租户 | 权限说明 |
|------|------|------|------|----------|
| **租户管理员** | admin@demo.com | admin123 | demo | 全部权限，可管理用户/角色/数据集 |
| **销售部门** | sales1@demo.com | sales123 | demo | 销售数据集读写，可提交审批 |
| **财务部门** | finance1@demo.com | finance123 | demo | 财务数据集读写，可审批销售提交 |

**登录步骤：**
1. 访问 http://localhost:3000
2. 租户 slug 填写：`demo`
3. 输入上述邮箱和密码

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
