# 🚀 快速启动指南

## ✅ 已完成
- ✅ 项目已移动到 `D:\projects\enterprise-ai-db\`
- ✅ `.env` 文件已创建（开发环境默认配置）

## 📝 启动步骤

### 1. （可选）配置 OpenAI API Key

如果您有 OpenAI API Key，编辑 `.env` 文件：

```bash
# 打开 .env 文件
notepad .env

# 修改这一行：
LLM_API_KEY=sk-placeholder-replace-with-your-openai-api-key
# 改为：
LLM_API_KEY=sk-your-actual-api-key-here
```

**注意**：Phase 2 的认证和用户管理功能不需要 OpenAI API，可以跳过此步骤。

### 2. 启动服务

```bash
# 进入项目目录
cd D:\projects\enterprise-ai-db

# 启动所有服务（PostgreSQL + Redis + Backend + Frontend + Worker）
docker compose up -d

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f backend
```

### 3. 运行数据库迁移

```bash
# 执行迁移（创建表结构 + RLS + 权限种子）
make migrate

# 执行 demo 数据种子（创建 demo 租户 + 3 个用户 + 5 个角色 + 2 个部门）
make seed
```

### 4. 测试 API

#### 4.1 健康检查
```bash
curl http://localhost:8000/health
```

预期响应：
```json
{"status": "ok", "version": "0.1.0"}
```

#### 4.2 登录（使用 demo 数据）
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"tenant_slug\": \"demo\", \"email\": \"admin@demo.com\", \"password\": \"demo123456\"}"
```

预期响应：
```json
{
  "access_token": "eyJ...",
  "refresh_token": "...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": "...",
    "email": "admin@demo.com",
    "display_name": "Admin User",
    "is_tenant_admin": true,
    "tenant_id": "...",
    "tenant_slug": "demo"
  }
}
```

#### 4.3 获取当前用户信息
```bash
# 将上一步返回的 access_token 替换到下面的命令中
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer <access_token>"
```

#### 4.4 列出用户
```bash
curl http://localhost:8000/api/v1/users \
  -H "Authorization: Bearer <access_token>"
```

#### 4.5 列出角色
```bash
curl http://localhost:8000/api/v1/roles \
  -H "Authorization: Bearer <access_token>"
```

#### 4.6 列出部门
```bash
curl http://localhost:8000/api/v1/departments \
  -H "Authorization: Bearer <access_token>"
```

### 5. 访问 API 文档

打开浏览器访问：
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 6. 访问前端（开发模式）

打开浏览器访问：
- **Frontend**: http://localhost:3000

---

## 🛠️ 常用命令

```bash
# 查看所有服务状态
docker compose ps

# 查看日志
docker compose logs -f backend
docker compose logs -f postgres
docker compose logs -f redis

# 重启服务
docker compose restart backend

# 停止所有服务
docker compose down

# 停止并删除数据卷（清空数据库）
docker compose down -v

# 进入 backend 容器
docker compose exec backend bash

# 进入 PostgreSQL
docker compose exec postgres psql -U postgres -d enterprise_ai

# 运行测试
make test

# 代码检查
make lint
```

---

## 🐛 故障排除

### 问题 1：端口被占用
```
Error: bind: address already in use
```

**解决方案**：
```bash
# 检查端口占用
netstat -ano | findstr :5432
netstat -ano | findstr :6379
netstat -ano | findstr :8000
netstat -ano | findstr :3000

# 停止占用端口的进程或修改 docker-compose.yml 中的端口映射
```

### 问题 2：数据库连接失败
```
Error: could not connect to server
```

**解决方案**：
```bash
# 等待 PostgreSQL 启动完成（约 10-15 秒）
docker compose logs postgres

# 检查健康状态
docker compose ps
```

### 问题 3：迁移失败
```
Error: alembic.util.exc.CommandError
```

**解决方案**：
```bash
# 检查数据库是否已启动
docker compose ps postgres

# 重新运行迁移
make migrate

# 如果仍然失败，重置数据库
docker compose down -v
docker compose up -d
sleep 10
make migrate
make seed
```

---

## 📚 Demo 数据

### 租户
- **Slug**: `demo`
- **Name**: Demo Corporation

### 用户（密码统一为 `demo123456`）

| Email | 角色 | 部门 | 权限 |
|---|---|---|---|
| admin@demo.com | tenant_admin | - | 全部权限 |
| sales@demo.com | editor, ai_user | Sales | Sales 部门的读写权限 |
| finance@demo.com | viewer | Finance | Finance 部门的只读权限 |

### 角色
- `tenant_admin` - 租户管理员（全部权限）
- `editor` - 编辑者（read/write record）
- `viewer` - 查看者（read record + read dataset）
- `approver` - 审批者（approve record）
- `ai_user` - AI 用户（ai_query record）

### 部门
- Sales
- Finance

---

## ✅ 验收清单

- [ ] 服务启动成功（`docker compose ps` 显示所有服务 healthy）
- [ ] 数据库迁移成功（`make migrate` 无错误）
- [ ] 种子数据创建成功（`make seed` 无错误）
- [ ] 健康检查通过（`curl http://localhost:8000/health`）
- [ ] 登录成功（返回 access_token）
- [ ] 获取用户信息成功（返回用户详情 + 角色 + 部门）
- [ ] API 文档可访问（http://localhost:8000/docs）
- [ ] 前端可访问（http://localhost:3000）

---

**🎉 Phase 2 实施完成！认证 + 用户/角色/权限系统已就绪。**
