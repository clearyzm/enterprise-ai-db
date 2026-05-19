# 运维手册 (RUNBOOK)

**Enterprise AI Database - 运维故障排查与日常维护指南**

---

## 目录

1. [常见问题排查](#常见问题排查)
2. [数据库备份与恢复](#数据库备份与恢复)
3. [日志查看与分析](#日志查看与分析)
4. [向量索引管理](#向量索引管理)

---

## 常见问题排查

### 1. 后端服务启动失败

#### 问题：端口已被占用

**症状：** `Error: bind: address already in use`

**排查：**
```bash
# Windows
netstat -ano | findstr :8000

# Linux/Mac
lsof -i :8000
```

**解决：**
```bash
# 停止占用进程或修改端口
# 编辑 .env: APP_PORT=8001
docker-compose restart backend
```

#### 问题：环境变量缺失

**症状：** `ValidationError: LLM_API_KEY Field required`

**解决：**
```bash
# 确保 .env 文件存在并填入必填项
cp .env.example .env
# 编辑 .env，配置 LLM_API_KEY 和 JWT_SECRET_KEY
docker-compose down && docker-compose up -d
```

#### 问题：数据库连接失败

**症状：** `OperationalError: could not connect to server`

**排查：**
```bash
# 检查 PostgreSQL 容器
docker ps | grep postgres
docker logs enterprise-ai-db-postgres-1

# 测试连接
docker exec -it enterprise-ai-db-postgres-1 psql -U postgres -d enterprise_ai
```

**解决：**
```bash
# 确保 PostgreSQL 运行并等待就绪
docker-compose up -d postgres
sleep 10
docker-compose restart backend
```

---

### 2. 数据库迁移失败

#### 问题：迁移版本冲突

**症状：** `Target database is not up to date`

**排查：**
```bash
# 查看当前版本
docker-compose exec backend uv run alembic current
docker-compose exec backend uv run alembic history
```

**解决：**
```bash
# 升级到最新版本
docker-compose exec backend uv run alembic upgrade head

# 或重置数据库（开发环境）
docker-compose down -v
docker-compose up -d
make migrate && make seed
```

---

### 3. AI 不回答或返回 denied

#### 问题：AI 返回 "denied" 或空响应

**排查步骤：**

1. **检查用户权限：**
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/auth/me
```

2. **检查向量索引：**
```bash
docker exec -it enterprise-ai-db-postgres-1 psql -U postgres -d enterprise_ai

# 查询 chunks 数量
SELECT dataset_id, COUNT(*) FROM chunks GROUP BY dataset_id;

# 检查嵌入向量
SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL;
```

**解决方案：**

**情况 1: 用户无 ai_query 权限**
- 为用户分配 ai_user 角色

**情况 2: 数据集未索引**
```bash
# 重建向量索引（见下方"向量索引管理"）
docker-compose exec backend uv run python -c "
from app.workers.tasks import reembed_dataset
reembed_dataset.delay('<dataset_id>')
"
```

**情况 3: LLM API 配置错误**
```bash
# 测试 API Key
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $LLM_API_KEY"
```

---

### 4. WebSocket 连接失败

**症状：** `WebSocket connection failed`

**排查：**
```bash
# 检查后端健康状态
curl http://localhost:8000/api/v1/health

# 查看 WebSocket 日志
docker-compose logs backend | grep "websocket"

# 测试连接（需安装 wscat）
npm install -g wscat
wscat -c "ws://localhost:8000/api/v1/ws?token=<token>"
```

**解决：**
- 检查 CORS 配置（backend/app/main.py）
- 重新登录获取新 token
- 检查 Redis 连接：`docker-compose exec redis redis-cli ping`

---

## 数据库备份与恢复

### 备份数据库

#### 完整备份（推荐）

```bash
# 创建备份目录
mkdir -p backups

# 备份数据库
docker exec enterprise-ai-db-postgres-1 pg_dump \
  -U postgres \
  -d enterprise_ai \
  -F c \
  | gzip > backups/enterprise_ai_$(date +%Y%m%d_%H%M%S).dump.gz
```

#### SQL 格式备份

```bash
# 备份为 SQL 文件
docker exec enterprise-ai-db-postgres-1 pg_dump \
  -U postgres \
  -d enterprise_ai \
  --clean --if-exists \
  > backups/enterprise_ai_$(date +%Y%m%d_%H%M%S).sql
```

#### 仅备份数据

```bash
docker exec enterprise-ai-db-postgres-1 pg_dump \
  -U postgres \
  -d enterprise_ai \
  --data-only \
  -F c \
  > backups/enterprise_ai_data_$(date +%Y%m%d_%H%M%S).dump
```

### 恢复数据库

#### 从自定义格式恢复

```bash
# 恢复到现有数据库
docker exec -i enterprise-ai-db-postgres-1 pg_restore \
  -U postgres \
  -d enterprise_ai \
  --clean --if-exists \
  < backups/enterprise_ai_20260514_120000.dump
```

#### 从 SQL 文件恢复

```bash
docker exec -i enterprise-ai-db-postgres-1 psql \
  -U postgres \
  -d enterprise_ai \
  < backups/enterprise_ai_20260514_120000.sql
```

#### 从压缩备份恢复

```bash
gunzip -c backups/enterprise_ai_20260514_120000.dump.gz \
  | docker exec -i enterprise-ai-db-postgres-1 pg_restore \
    -U postgres \
    -d enterprise_ai \
    --clean --if-exists
```

### 自动化备份脚本

```bash
#!/bin/bash
# backup.sh - 自动备份脚本

BACKUP_DIR="backups"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/enterprise_ai_${TIMESTAMP}.dump.gz"

# 创建备份
docker exec enterprise-ai-db-postgres-1 pg_dump \
  -U postgres \
  -d enterprise_ai \
  -F c \
  | gzip > "${BACKUP_FILE}"

if [ $? -eq 0 ]; then
  echo "✅ Backup successful: ${BACKUP_FILE}"
  # 删除旧备份
  find "${BACKUP_DIR}" -name "*.dump.gz" -mtime +${RETENTION_DAYS} -delete
else
  echo "❌ Backup failed"
  exit 1
fi
```

**设置定时备份（cron）：**
```bash
# 每天凌晨 2 点备份
0 2 * * * /path/to/backup.sh >> /var/log/backup.log 2>&1
```

---

## 日志查看与分析

### Docker 日志查看

```bash
# 实时跟踪所有服务日志
docker-compose logs -f

# 查看最近 100 行
docker-compose logs --tail=100

# 查看特定服务
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f postgres

# 过滤日志
docker-compose logs backend | grep -i error
docker-compose logs backend | grep "user_id=<uuid>"
docker-compose logs backend | grep "ai\."
```

### Structlog 日志格式

后端使用 **structlog** 输出结构化 JSON 日志：

```json
{
  "event": "login.success",
  "level": "info",
  "timestamp": "2026-05-14T10:30:45.123456Z",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_id": "660e8400-e29b-41d4-a716-446655440000",
  "email": "admin@demo.com"
}
```

#### 常见日志事件

| 事件 | 说明 | 级别 |
|------|------|------|
| `login.success` | 登录成功 | info |
| `login.invalid_password` | 密码错误 | warning |
| `permission.check.denied` | 权限拒绝 | debug |
| `ai.agent.classify.complete` | AI 分类完成 | info |
| `guardrail.violations` | 安全检查失败 | warning |
| `workflow.approval.approved` | 审批通过 | info |
| `record.version_conflict` | 乐观锁冲突 | warning |

#### 日志分析示例

```bash
# 统计登录失败次数
docker-compose logs backend | grep "login.invalid_password" | wc -l

# 查看权限拒绝事件
docker-compose logs backend | grep "permission.check.denied" | tail -20

# 导出日志到文件
docker-compose logs backend > logs/backend_$(date +%Y%m%d).log
```

---

## 向量索引管理

### 重建单个数据集的向量索引

```bash
# 使用 Python 脚本
docker-compose exec backend uv run python -c "
from app.workers.tasks import reembed_dataset
task = reembed_dataset.delay('<dataset_id>')
print(f'Task ID: {task.id}')
"

# 使用 Celery CLI
docker-compose exec backend uv run celery -A app.workers.celery_app call \
  app.workers.tasks.reembed_dataset \
  --args='["<dataset_id>"]'
```

### 重建所有数据集的向量索引

```bash
docker-compose exec backend uv run python -c "
from sqlalchemy import select
from app.db.session import async_session_maker
from app.models.dataset import DataSet
from app.workers.tasks import reembed_dataset
import asyncio

async def reembed_all():
    async with async_session_maker() as session:
        result = await session.execute(
            select(DataSet.id).where(DataSet.status == 'active')
        )
        for row in result.all():
            task = reembed_dataset.delay(str(row[0]))
            print(f'Submitted: {task.id}')

asyncio.run(reembed_all())
"
```

### 查看 Celery 任务状态

```bash
# 查看活跃任务
docker-compose exec backend uv run celery -A app.workers.celery_app inspect active

# 查看已注册任务
docker-compose exec backend uv run celery -A app.workers.celery_app inspect registered

# 查看任务统计
docker-compose exec backend uv run celery -A app.workers.celery_app inspect stats
```

### 清理失败的任务

```bash
# 清除所有任务队列
docker-compose exec backend uv run celery -A app.workers.celery_app purge

# 重启 Celery Worker
docker-compose restart celery-worker
```

### 手动清理向量索引

```bash
# 删除特定数据集的 chunks
docker exec -it enterprise-ai-db-postgres-1 psql -U postgres -d enterprise_ai -c "
DELETE FROM chunks WHERE dataset_id = '<dataset_id>';
"

# 删除所有 chunks（谨慎使用）
docker exec -it enterprise-ai-db-postgres-1 psql -U postgres -d enterprise_ai -c "
TRUNCATE TABLE chunks;
"
```

---

## 快速命令参考

```bash
# 快速重启所有服务
docker-compose restart

# 查看服务健康状态
curl http://localhost:8000/api/v1/health

# 进入后端容器
docker-compose exec backend bash

# 进入数据库
docker exec -it enterprise-ai-db-postgres-1 psql -U postgres -d enterprise_ai

# 清理所有数据（开发环境）
docker-compose down -v && docker-compose up -d && make migrate && make seed

# 查看容器资源使用
docker stats
```

---

**最后更新：** 2026-05-14  
**版本：** 1.0.0
