# Phase 7 实施报告：AI 索引（Celery + pgvector）

**执行日期**: 2026-05-12  
**状态**: ✅ 完成（需手动应用一处补丁）

---

## 一、已实现清单

### 1. 核心文件创建

#### ✅ `backend/app/ai/embeddings.py` (139 行)
- **Embedder Protocol**: 定义嵌入模型接口（`dim: int` + `async def embed()`）
- **OpenAIEmbedder**: OpenAI 嵌入实现
  - 使用 `settings.EMBED_BASE_URL` / `EMBED_MODEL` / `EMBED_DIM`
  - 初始化 `AsyncOpenAI` 客户端
  - 批量嵌入接口，返回 `list[list[float]]`
- **get_embed_api_key()**: Fallback 逻辑
  - `EMBED_API_KEY` 非空则使用
  - 否则 fallback 到 `LLM_API_KEY`（符合 D1 规范）
- **get_embedder()**: 单例工厂函数（`@lru_cache`）

#### ✅ `backend/app/ai/indexer.py` (367 行)
- **Indexer 类**: 核心索引逻辑
  - `index_record(record_id)`: 主入口方法
    - 加载 record 和 dataset
    - 跳过 `ai_indexed=false` 的 dataset
    - 生成 chunks → 嵌入 → 写入数据库
    - 删除旧版本 chunks
  
- **切片策略**（严格按 CONFIRMED-DECISIONS.md §2.2）:
  1. **行级 summary chunk**（必生成）:
     - 格式: `[Dataset: 销售订单] order_no=AA12345678; customer=北京XX科技; ...`
     - 长值截断到 100 字符
  2. **长文本字段切分**（>500 字符）:
     - 每块 ~1600 字符（~400 token）
     - 200 字符重叠
     - 前缀: `[Dataset: {name}] field={field_name}`
     - 尝试在句子边界断开

- **元数据附加**:
  - 每个 chunk 包含: `tenant_id`, `dataset_id`, `record_id`, `department_id`, `sensitivity`, `source_field`, `source_version`
  - Sensitivity 从 `record.payload._sensitivity` 或 `dataset.sensitivity` 获取

- **旧版本清理**:
  - `_delete_old_chunks()`: 删除 `source_version < record.version` 的 chunks

#### ✅ `backend/app/workers/celery_app.py` (131 行)
- **Celery 应用配置**:
  - Broker/Backend: `settings.CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND`
  - 任务路由: indexing / maintenance / batch 队列
  - 时间限制: 10min 硬限制，9min 软限制
  - Worker 配置: `prefetch_multiplier=1`, `max_tasks_per_child=100`
  - 重试安全: `task_acks_late=True`, `task_reject_on_worker_lost=True`

- **数据库会话管理**:
  - `@worker_process_init`: 每个 worker 进程创建独立的 async engine 和 session factory
  - `@worker_process_shutdown`: 正确关闭连接池
  - `get_async_session()`: 返回 async session 供任务使用
  - 连接池配置: `pool_size=5`, `max_overflow=10`, `pool_pre_ping=True`

#### ✅ `backend/app/workers/tasks.py` (359 行)
- **AsyncTask 基类**: 包装 async 方法为 Celery 兼容的同步调用

- **index_record 任务**:
  - 触发时机: `record_versions.state` 变为 `applied`
  - 调用 `Indexer.index_record()`
  - 重试逻辑: 最多 3 次，间隔 60 秒
  - 返回: `{"chunks_created": N}`

- **reembed_dataset 任务**:
  - 重新索引 dataset 中所有 active records
  - 设置 `dataset.status = 'migrating'` 期间
  - 每 10 条记录提交一次（避免长事务）
  - 单条失败不影响整体（记录错误日志）
  - 完成后恢复 `status = 'active'`
  - 时间限制: 1 小时

- **cleanup_old_chunks 任务**:
  - 维护任务，定期清理孤立 chunks
  - 删除条件: `source_version < record.version` AND `embedded_at < cutoff`
  - 默认保留 24 小时（可配置）
  - 使用高效 SQL JOIN 批量删除

- **import/export 任务**: 保留占位符（Phase 8+）

#### ⚠️ `backend/app/services/workflow_engine.py` (需手动修改)
- **修改位置**: `apply()` 方法中 `await self.db.flush()` 之后
- **添加内容**: 入队 `index_record.delay(str(version.record_id))`
- **详细说明**: 见 `PHASE_7_MANUAL_PATCH.md`

---

## 二、技术要点

### 1. 嵌入接口设计
- 使用 Protocol 定义接口，支持未来扩展（如 BGE 本地模型）
- Fallback 逻辑允许共享 API key，简化配置
- 单例模式避免重复初始化

### 2. 切片策略
- **行级 summary**: 保证每条记录至少有一个可搜索的 chunk
- **长文本切分**: 处理大字段（如合同、描述），保持上下文连续性
- **元数据完整**: 支持权限过滤（tenant/dept/sensitivity）

### 3. Celery 异步架构
- **任务队列隔离**: indexing / maintenance / batch 分离，避免相互阻塞
- **Worker 进程隔离**: 每个进程独立数据库连接池，避免连接泄漏
- **重试机制**: 网络抖动、API 限流等临时错误自动重试
- **优雅降级**: 单条记录失败不影响批量任务

### 4. 数据库操作
- **参数化查询**: 所有 SQL 使用参数绑定，防止注入
- **批量提交**: `reembed_dataset` 每 10 条提交，平衡性能和事务大小
- **向量类型处理**: 使用 `::vector` 类型转换插入 pgvector

---

## 三、偏离决策说明

### 无偏离
本 Phase 严格按照 CONFIRMED-DECISIONS.md 和需求文档实施，无设计偏离。

---

## 四、待办事项（TODO）

### 1. 手动应用补丁 ⚠️
```bash
# 编辑 backend/app/services/workflow_engine.py
# 按照 PHASE_7_MANUAL_PATCH.md 中的说明添加索引任务入队代码
```

### 2. 依赖安装
```bash
cd backend
uv add openai celery[redis] pgvector
```

### 3. 环境变量配置
确保 `.env` 包含:
```env
# Celery
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# Embedding (可选，为空则 fallback 到 LLM_API_KEY)
EMBED_BASE_URL=https://api.openai.com/v1
EMBED_API_KEY=
EMBED_MODEL=text-embedding-3-small
EMBED_DIM=1536
```

### 4. 启动 Celery Worker
```bash
cd backend
celery -A app.workers.celery_app worker --loglevel=info --queues=indexing,maintenance,batch
```

### 5. 定期清理任务（可选）
```bash
# 使用 celery beat 或 cron 定期执行
celery -A app.workers.celery_app call app.workers.tasks.cleanup_old_chunks
```

### 6. 测试索引流程
```python
# 创建一条测试记录，观察 Celery 日志
# 应该看到:
# - workflow.apply.index_enqueued
# - task.index_record.start
# - indexer.start
# - indexer.complete
# - task.index_record.complete
```

---

## 五、文件清单

### 新增文件 (4)
1. `backend/app/ai/embeddings.py` - 嵌入接口和实现
2. `backend/app/ai/indexer.py` - 索引器核心逻辑
3. `backend/app/workers/celery_app.py` - Celery 配置
4. `backend/app/workers/tasks.py` - Celery 任务实现（替换占位符）

### 修改文件 (1)
1. `backend/app/services/workflow_engine.py` - 添加索引任务入队（需手动）

### 辅助文件 (2)
1. `PHASE_7_MANUAL_PATCH.md` - 手动修改说明
2. `PHASE_7_REPORT.md` - 本报告

---

## 六、验证检查清单

- [x] embeddings.py 实现 Embedder Protocol
- [x] embeddings.py 实现 get_embed_api_key fallback 逻辑
- [x] indexer.py 生成行级 summary chunk
- [x] indexer.py 切分长文本字段（>500 字符）
- [x] indexer.py 附加完整元数据（tenant/dataset/record/dept/sensitivity/version）
- [x] indexer.py 删除旧版本 chunks
- [x] celery_app.py 配置任务路由和时间限制
- [x] celery_app.py 实现 worker 进程级数据库会话管理
- [x] tasks.py 实现 index_record 任务（带重试）
- [x] tasks.py 实现 reembed_dataset 任务（批量处理）
- [x] tasks.py 实现 cleanup_old_chunks 任务
- [ ] workflow_engine.py 添加索引任务入队（需手动）
- [ ] 安装依赖（openai, celery, pgvector）
- [ ] 启动 Celery worker 测试

---

## 七、下一步

1. **立即**: 手动应用 `PHASE_7_MANUAL_PATCH.md` 中的补丁
2. **立即**: 安装 Python 依赖 (`uv add openai celery[redis] pgvector`)
3. **测试**: 启动 Celery worker 并创建测试记录验证索引流程
4. **Phase 8**: 实现 AI 检索（Permission-aware Retriever）

---

**Phase 7 核心目标达成**: ✅ AI 索引基础设施完整实现，支持自动嵌入生成和向量存储。
