"""Workflow engine — approval workflow state machine."""
from datetime import datetime
from typing import Any
from uuid import UUID
import structlog
import sqlalchemy as sa
from sqlalchemy import select, and_, func, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession
from json_logic import jsonLogic
from app.models.workflow import Workflow, ApprovalAction, ApprovalActionType, AUTO_APPROVE_WORKFLOW_ID
from app.models.record import DataRecord, RecordVersion, RecordStatus, RecordVersionOp, RecordVersionState
from app.models.dataset import DataSet
from app.models.user import User
from app.models.role import Role, UserRole
from app.utils.errors import NotFoundError, ValidationError, PermissionDeniedError, ConflictError
from app.realtime.redis_bus import get_event_bus

logger = structlog.get_logger(__name__)


class WorkflowEngine:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def submit(self, version: RecordVersion, user: User) -> RecordVersion:
        dataset = await self._get_dataset(version.dataset_id)
        workflow_id = dataset.workflow_id
        if workflow_id == AUTO_APPROVE_WORKFLOW_ID or workflow_id is None:
            await self.apply(version, user)
            return version
        workflow = await self._get_workflow(workflow_id)
        version.workflow_id = workflow.id
        first_step = await self._find_first_applicable_step(workflow, version)
        if first_step is None:
            await self.apply(version, user)
        else:
            version.current_step = first_step
            version.state = RecordVersionState.pending
            step = workflow.steps[first_step]
            candidates = await self._resolve_approvers(step, version, version.tenant_id)
            # Snapshot candidate approvers for this step
            version.detail = {
                "step_candidates": {
                    str(first_step): [str(uid) for uid in candidates]
                }
            }
            await self.db.flush()
            # Notify candidate approvers
            await get_event_bus().publish(
                tenant_id=version.tenant_id,
                channel="approvals",
                event={
                    "type": "approval.new",
                    "version_id": str(version.id),
                    "dataset_id": str(version.dataset_id),
                    "step": first_step,
                    "candidates": [str(uid) for uid in candidates],
                },
            )
        return version

    async def approve(self, version_id: UUID, approver: User, comment: str | None = None) -> RecordVersion:
        version = await self._get_version(version_id, True)
        if version.state != RecordVersionState.pending:
            raise ValidationError(f"Not pending: {version.state.value}")
        if version.proposed_by == approver.id:
            raise PermissionDeniedError("Cannot approve own submission")
        workflow = await self._get_workflow(version.workflow_id)  # type: ignore
        step = workflow.steps[version.current_step]
        candidates = await self._resolve_approvers(step, version, version.tenant_id)
        if approver.id not in candidates:
            raise PermissionDeniedError("Not authorized")
        self.db.add(ApprovalAction(tenant_id=version.tenant_id, version_id=version.id, step_index=version.current_step, approver_id=approver.id, action=ApprovalActionType.approve, comment=comment))
        await self.db.flush()
        if await self._is_step_satisfied(version, step):
            next_step = await self._find_next_applicable_step(workflow, version, version.current_step + 1)
            if next_step is None:
                version.state = RecordVersionState.approved
                await self.db.flush()
                await self.apply(version, approver)
                # approval.applied is published inside apply() after record commit
            else:
                version.current_step = next_step
                # Snapshot candidate approvers for the new step
                next_step_config = workflow.steps[next_step]
                next_candidates = await self._resolve_approvers(next_step_config, version, version.tenant_id)
                if "step_candidates" not in version.detail:
                    version.detail["step_candidates"] = {}
                version.detail["step_candidates"][str(next_step)] = [str(uid) for uid in next_candidates]
                await self.db.flush()
                await get_event_bus().publish(
                    tenant_id=version.tenant_id,
                    channel="approvals",
                    event={
                        "type": "approval.advanced",
                        "version_id": str(version.id),
                        "dataset_id": str(version.dataset_id),
                        "step": next_step,
                        "candidates": [str(uid) for uid in next_candidates],
                    },
                )
        return version

    async def reject(self, version_id: UUID, approver: User, comment: str | None = None) -> RecordVersion:
        version = await self._get_version(version_id, True)
        if version.state != RecordVersionState.pending:
            raise ValidationError(f"Not pending: {version.state.value}")
        if version.proposed_by == approver.id:
            raise PermissionDeniedError("Cannot reject own submission")
        workflow = await self._get_workflow(version.workflow_id)  # type: ignore
        step = workflow.steps[version.current_step]
        if approver.id not in await self._resolve_approvers(step, version, version.tenant_id):
            raise PermissionDeniedError("Not authorized")
        self.db.add(ApprovalAction(tenant_id=version.tenant_id, version_id=version.id, step_index=version.current_step, approver_id=approver.id, action=ApprovalActionType.reject, comment=comment))
        version.state = RecordVersionState.rejected
        version.reject_reason = comment
        await self.db.flush()
        await get_event_bus().publish(
            tenant_id=version.tenant_id,
            channel="approvals",
            event={
                "type": "approval.rejected",
                "version_id": str(version.id),
                "dataset_id": str(version.dataset_id),
                "by": str(approver.id),
            },
        )
        return version

    async def cancel(self, version_id: UUID, user: User) -> RecordVersion:
        version = await self._get_version(version_id, True)
        if version.state != RecordVersionState.pending:
            raise ValidationError(f"Not pending: {version.state.value}")
        if version.proposed_by != user.id:
            raise PermissionDeniedError("Only proposer can cancel")
        version.state = RecordVersionState.cancelled
        await self.db.flush()
        return version

    async def apply(self, version: RecordVersion, user: User) -> DataRecord | None:
        await self.db.execute(sa.text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
        try:
            if version.op == RecordVersionOp.insert:
                record = await self._apply_insert(version, user)
            elif version.op == RecordVersionOp.update:
                record = await self._apply_update(version, user)
            elif version.op == RecordVersionOp.delete:
                record = await self._apply_delete(version, user)
            else:
                raise ValidationError(f"Unknown op: {version.op}")
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
                record_id_str = str(version.record_id) if version.record_id else ""
                event: dict[str, object] = {
                    "type": "approval.applied",
                    "version_id": str(version.id),
                    "record_id": record_id_str,
                    "dataset_id": str(version.dataset_id),
                    "by": str(user.id),
                }
                await get_event_bus().publish(
                    tenant_id=version.tenant_id,
                    channel="approvals",
                    event=event,
                )
                await get_event_bus().publish(
                    tenant_id=version.tenant_id,
                    channel=f"dataset:{version.dataset_id}",
                    event=event,
                )
            return record
        except ConflictError:
            version.state = RecordVersionState.superseded
            await self.db.flush()
            return None

    async def _get_dataset(self, dataset_id: UUID) -> DataSet:
        result = await self.db.execute(select(DataSet).where(DataSet.id == dataset_id))
        dataset = result.scalar_one_or_none()
        if not dataset:
            raise NotFoundError("Dataset")
        return dataset

    async def _get_workflow(self, workflow_id: UUID) -> Workflow:
        result = await self.db.execute(select(Workflow).where(Workflow.id == workflow_id))
        workflow = result.scalar_one_or_none()
        if not workflow:
            raise NotFoundError("Workflow")
        return workflow

    async def _get_version(self, version_id: UUID, lock: bool = False) -> RecordVersion:
        stmt = select(RecordVersion).where(RecordVersion.id == version_id)
        if lock:
            stmt = stmt.with_for_update()
        result = await self.db.execute(stmt)
        version = result.scalar_one_or_none()
        if not version:
            raise NotFoundError("RecordVersion")
        return version

    async def _find_first_applicable_step(self, wf: Workflow, ver: RecordVersion) -> int | None:
        return await self._find_next_applicable_step(wf, ver, 0)

    async def _find_next_applicable_step(self, wf: Workflow, ver: RecordVersion, start: int) -> int | None:
        for i in range(start, len(wf.steps)):
            cond = wf.steps[i].get("condition")
            if not cond:
                return i
            try:
                if jsonLogic(cond, {"payload": ver.after_payload or {}, "op": ver.op.value}):
                    return i
            except Exception:
                continue
        return None

    async def _resolve_approvers(self, step: dict[str, Any], ver: RecordVersion, tid: UUID) -> list[UUID]:
        cfg = step.get("approver", {})
        typ = cfg.get("type")
        val = cfg.get("value")
        if typ == "user_ids" and isinstance(val, list):
            return [UUID(u) if isinstance(u, str) else u for u in val]
        elif typ == "role":
            stmt = select(UserRole.user_id).join(User).join(Role).where(and_(User.tenant_id == tid, Role.name == val))
            if step.get("require_dept_match") and ver.record_id:
                dept_res = await self.db.execute(select(DataRecord.department_id).where(DataRecord.id == ver.record_id))
                dept_id = dept_res.scalar_one_or_none()
                if dept_id:
                    from app.models.department import UserDepartment
                    stmt = stmt.join(UserDepartment).where(UserDepartment.department_id == dept_id)
            result = await self.db.execute(stmt)
            return [r[0] for r in result.all()]
        elif typ == "role_in_dept" and ver.record_id:
            dept_res = await self.db.execute(select(DataRecord.department_id).where(DataRecord.id == ver.record_id))
            dept_id = dept_res.scalar_one_or_none()
            if dept_id:
                from app.models.department import UserDepartment
                stmt = select(UserRole.user_id).join(User).join(Role).join(UserDepartment).where(and_(User.tenant_id == tid, Role.name == val, UserDepartment.department_id == dept_id))
                result = await self.db.execute(stmt)
                return [r[0] for r in result.all()]
        return []

    async def _is_step_satisfied(self, ver: RecordVersion, step: dict[str, Any]) -> bool:
        mode = step.get("mode", "any")
        stmt = select(func.count(ApprovalAction.id.distinct())).where(and_(ApprovalAction.version_id == ver.id, ApprovalAction.step_index == ver.current_step, ApprovalAction.action == ApprovalActionType.approve))
        cnt = (await self.db.execute(stmt)).scalar_one()
        
        # Read candidate snapshot from version.detail
        snapshot = ver.detail.get("step_candidates", {}).get(str(ver.current_step), [])
        total_required = len(snapshot)
        
        if mode == "any":
            return cnt >= 1
        elif mode == "all":
            return cnt >= total_required
        else:
            return False

    async def _apply_insert(self, ver: RecordVersion, user: User) -> DataRecord:
        if not ver.after_payload:
            raise ValidationError("INSERT needs after_payload")
        rec = DataRecord(tenant_id=ver.tenant_id, dataset_id=ver.dataset_id, department_id=None, payload=ver.after_payload, status=RecordStatus.active, version=1, created_by=ver.proposed_by, updated_by=user.id)
        self.db.add(rec)
        await self.db.flush()
        ver.record_id = rec.id
        return rec

    async def _apply_update(self, ver: RecordVersion, user: User) -> DataRecord:
        if not ver.record_id or not ver.after_payload:
            raise ValidationError("UPDATE needs record_id and after_payload")
        exp_ver = ver.before_payload.get("__version", 1) if ver.before_payload else 1
        stmt = sql_update(DataRecord).where(and_(DataRecord.id == ver.record_id, DataRecord.version == exp_ver)).values(payload=ver.after_payload, version=DataRecord.version + 1, updated_by=user.id, updated_at=datetime.utcnow()).returning(DataRecord)
        rec = (await self.db.execute(stmt)).scalar_one_or_none()
        if not rec:
            raise ConflictError("Version conflict", code="record.version_conflict")
        return rec

    async def _apply_delete(self, ver: RecordVersion, user: User) -> DataRecord:
        if not ver.record_id:
            raise ValidationError("DELETE needs record_id")
        exp_ver = ver.before_payload.get("__version", 1) if ver.before_payload else 1
        stmt = sql_update(DataRecord).where(and_(DataRecord.id == ver.record_id, DataRecord.version == exp_ver)).values(status=RecordStatus.soft_deleted, version=DataRecord.version + 1, updated_by=user.id, updated_at=datetime.utcnow()).returning(DataRecord)
        rec = (await self.db.execute(stmt)).scalar_one_or_none()
        if not rec:
            raise ConflictError("Version conflict", code="record.version_conflict")
        return rec
