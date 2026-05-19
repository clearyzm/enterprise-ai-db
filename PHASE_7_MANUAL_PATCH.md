# Phase 7: Manual Modification Required

## File: backend/app/services/workflow_engine.py

In the `apply` method, after line:
```python
            await self.db.flush()
```

And before line:
```python
            # Publish approval.applied only when there is a workflow (not auto-approve)
```

**Add the following code:**

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

This modification ensures that after a record version is successfully applied to the database, an indexing task is enqueued to Celery to generate embeddings and chunks for AI search.

## Location in File

The modification should be in the `async def apply(self, version: RecordVersion, user: User)` method, approximately at line 155-165.

The complete section should look like:

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
