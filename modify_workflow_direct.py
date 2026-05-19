import sys

file_path = r'D:\projects\enterprise-ai-db\backend\app\services\workflow_engine.py'

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line in apply method
target_idx = None
for i, line in enumerate(lines):
    if 'await self.db.flush()' in line and i > 140:
        target_idx = i
        break

if target_idx is None:
    print("ERROR: Could not find target line")
    sys.exit(1)

# Insert new lines after flush()
insert_lines = [
    '\n',
    '            # Enqueue indexing task after successful apply\n',
    '            # For delete operations, we still index to update chunks (mark as deleted)\n',
    '            if version.record_id:\n',
    '                from app.workers.tasks import index_record\n',
    '                index_record.delay(str(version.record_id))\n',
    '                logger.info(\n',
    '                    "workflow.apply.index_enqueued",\n',
    '                    version_id=str(version.id),\n',
    '                    record_id=str(version.record_id),\n',
    '                    op=version.op.value,\n',
    '                )\n',
    '\n',
]

# Insert after the flush line
new_lines = lines[:target_idx+1] + insert_lines + lines[target_idx+1:]

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"SUCCESS: Modified workflow_engine.py at line {target_idx+1}")
print(f"Added {len(insert_lines)} lines")
