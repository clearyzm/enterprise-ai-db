#!/usr/bin/env python3
"""Temporary script to modify workflow_engine.py"""

import sys
from pathlib import Path

workflow_file = Path(__file__).parent / "app" / "services" / "workflow_engine.py"

with open(workflow_file, 'r', encoding='utf-8') as f:
    content = f.read()

old_text = """            await self.db.flush()
            # Publish approval.applied only when there is a workflow (not auto-approve)"""

new_text = """            await self.db.flush()
            
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
            
            # Publish approval.applied only when there is a workflow (not auto-approve)"""

if old_text in content:
    content = content.replace(old_text, new_text)
    with open(workflow_file, 'w', encoding='utf-8') as f:
        f.write(content)
    print("✓ Modified workflow_engine.py successfully")
    sys.exit(0)
else:
    print("✗ Could not find target text in workflow_engine.py")
    sys.exit(1)
