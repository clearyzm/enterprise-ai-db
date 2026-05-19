# PHASE_6_REPORT — WebSocket 实时同步

## 已实现清单

| 文件 | 状态 | 说明 |
|---|---|---|
| `backend/app/realtime/redis_bus.py` | 新建 | In-process EventBus，预留 Redis 接口 (165 行) |
| `backend/app/realtime/ws_manager.py` | 新建 | WSManager + WSConnection，连接池与频道路由 (240 行) |
| `backend/app/api/ws.py` | 新建 | FastAPI WebSocket 端点，握手认证与消息循环 (220 行) |
| `backend/app/services/record_service.py` | 修改 | apply 后发布 record.upserted / record.deleted |
| `backend/app/services/workflow_engine.py` | 修改 | 审批流程中发布 approval.* 事件 |
| `backend/app/main.py` | 修改 | 注册 WebSocket 路由 + 启动心跳清理后台任务 |

**总计**：3 个新文件（约 625 行）+ 3 个更新文件，Linter 错误：0。

---

## 1. EventBus（redis_bus.py）

### 设计
- **In-process 实现**：`EventBus` 维护 `tenant_id → list[EventCallback]` 订阅表
- **租户隔离**：`publish()` 只向同一 `tenant_id` 的订阅者投递事件
- **并发安全**：`asyncio.Lock` 保护订阅表读写；`asyncio.gather()` 并发调用所有回调
- **错误隔离**：单个回调失败只记录日志，不影响其他回调
- **JSON 校验**：publish 前验证事件可序列化

### 预留 Redis 接口
- 函数签名 `publish(tenant_id, channel, event)` 与 Phase 11 Redis 方案完全兼容
- Phase 11 只需替换本地分发为 `redis.publish(f"events:{tenant_id}", json)`

---

## 2. WSManager（ws_manager.py）

### 连接池
- `_connections: dict[UUID, set[WSConnection]]` 按 tenant_id 分组
- 首个连接建立时向 EventBus 注册回调；最后一个连接断开时注销（避免空轮询）

### 频道权限检查

| 频道 | 权限逻辑 |
|---|---|
| `dataset:{id}` | 检查 DataSet 存在于当前 tenant（TODO: PermissionService 细化） |
| `record:{id}` | 检查 DataRecord 存在于当前 tenant（TODO: PermissionService 细化） |
| `approvals` | 始终允许（事件内容按用户身份过滤） |
| `ai:{conv_id}` | 始终允许（Phase 6 占位） |
| `notifications` | 始终允许（用户自己的通知） |
| 未知类型 | 拒绝 |

无权限订阅：**不断开连接**，返回 `"permission_denied"` 状态。

---

## 3. WebSocket 端点（ws.py）

### 握手认证
- Token 从 Query Param 读取：`/ws?token=<access_token>`
- Fallback：读 `authorization` 请求头
- 认证失败：`close(code=4001)`

### 消息协议

**客户端 → 服务端：**
```json
{ "type": "ping" }
{ "type": "subscribe",   "channels": ["dataset:abc", "approvals"] }
{ "type": "unsubscribe", "channels": ["dataset:abc"] }
```

**服务端 → 客户端：**
```json
{ "type": "pong" }
{ "type": "subscribed",   "results": {"dataset:abc": "ok", "approvals": "ok"} }
{ "type": "unsubscribed", "channels": ["dataset:abc"] }
{ "type": "error",        "message": "..." }
{ "channel": "dataset:abc", "type": "record.upserted", "record_id": "...", "version": 2, "by": "..." }
```

### 心跳与超时
- 客户端每 25s 发 `{"type":"ping"}`，服务端回 `{"type":"pong"}`
- `asyncio.wait_for(receive_json(), timeout=30)` 实现服务端超时检测
- 30s 无消息 → `close(1000, "Ping timeout")`

---

## 4. 事件发布一览（严格对应 §4.4）

| 事件 | 触发点 | 频道 |
|---|---|---|
| `record.upserted` | RecordService create/update apply 完成 | `dataset:{ds_id}` |
| `record.deleted` | RecordService delete apply 完成 | `dataset:{ds_id}` |
| `approval.new` | WorkflowEngine.submit 进入 pending | `approvals` |
| `approval.advanced` | WorkflowEngine.approve step 推进 | `approvals` |
| `approval.applied` | WorkflowEngine.apply 完成（有工作流时） | `approvals` + `dataset:{ds_id}` |
| `approval.rejected` | WorkflowEngine.reject 完成 | `approvals` |

**注意**：自动审批路径（record.upserted / record.deleted）由 RecordService 发布；工作流审批路径通过 approval.applied 覆盖，两条路径不重叠不重复。

---

## 5. 安全保证

| 安全点 | 实现 |
|---|---|
| 握手认证 | decode_access_token 验证 JWT，失败 close(4001) |
| 租户隔离 | EventBus 按 tenant_id 分组；WSManager 连接按 tenant_id 索引 |
| 频道权限 | 订阅时检查 dataset/record 存在于当前 tenant |
| 拒绝不断开 | 无权频道返回 permission_denied，连接保持 |
| ping 超时 | 30s 未收到消息服务端主动关闭 |

---

## 6. 偏离文档的决策

| 决策 | 原因 |
|---|---|
| EventBus 用 in-process 实现 | 任务要求 Phase 6 优先单实例正确性，Phase 11 再切 Redis pub/sub |
| dataset:{id} 权限检查简化 | 检查 dataset 存在于 tenant 即可，PermissionService 精细检查留 TODO |
| record.upserted/deleted 发布位置 | 在 RecordService 而非 WorkflowEngine，避免自动审批路径遗漏 |

---

## 7. 统计

- **新文件**：3（约 625 行）
- **更新文件**：3
- **新增端点**：1（WebSocket /ws）
- **Linter 错误**：0
- **mypy 注解**：全文件 strict 兼容
