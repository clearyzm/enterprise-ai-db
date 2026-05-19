# workflow_engine.py 修改说明

## 需要修改的位置

文件：`backend/app/services/workflow_engine.py`

在 `async def apply(self, version: RecordVersion, user: User)` 方法中，找到这一行：

```python
            await self.db.flush()
```

在这一行**之后**，添加以下代码（注意保持缩进一致）：

```python
            
            # Enqueue indexing task after successful apply
            # For delete operations, we still index to update chunks (mark as deleted)
            if version.record_id:
                from app.workers.tasks import index_record
                index_record.delay(str(version.record_id))
                logger.info(
                    "workflow.apply.index_enqueued",
                    version_id=str(version.id),
                    record_id=str(version.record_id),
                    op=version.op.value,
                )
            
```

## 修改后的完整片段应该是：

```python
            version.state = RecordVersionState.applied
            version.applied_at = datetime.utcnow()
            await self.db.flush()
            
            # Enqueue indexing task after successful apply
            # For delete operations, we still index to update chunks (mark as deleted)
            if version.record_id:
                from app.workers.tasks import index_record
                index_record.delay(str(version.record_id))
                logger.info(
                    "workflow.apply.index_enqueued",
                    version_id=str(version.id),
                    record_id=str(version.record_id),
                    op=version.op.value,
                )
            
            # Publish approval.applied only when there is a workflow (not auto-approve)
            if version.workflow_id is not None and version.workflow_id != AUTO_APPROVE_WORKFLOW_ID:
```

## 验证

修改后，该方法应该：
1. 先执行 `await self.db.flush()` 提交数据库更改
2. 然后入队索引任务 `index_record.delay()`
3. 最后发布实时事件（如果有 workflow）

这样确保记录成功写入数据库后，才触发异步索引任务。
