"""Human-in-the-loop approval state (PRD §11.2) — generic, domain-agnostic."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    GRANTED = "granted"
    REJECTED = "rejected"


class HitlLifecycleStage(StrEnum):
    """Generic §11.2 stages surfaced on RP approval/commit events (POC subset)."""

    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    COMMIT = "COMMIT"
    VERIFY = "VERIFY"


@dataclass
class ApprovalRecord:
    approval_id: str
    tool_name: str
    arguments: dict[str, Any]
    status: ApprovalStatus = ApprovalStatus.PENDING
    lifecycle_stage: HitlLifecycleStage = HitlLifecycleStage.READY_FOR_REVIEW
    summary: str = ""
    idempotency_key: str = ""
    auth_proof: str | None = None

    def __post_init__(self) -> None:
        if not self.idempotency_key:
            self.idempotency_key = self.approval_id


@dataclass
class HITLManager:
    """Per-session pending approvals and grant/reject decisions."""

    _records: dict[str, ApprovalRecord] = field(default_factory=dict)

    def register_request(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        summary: str = "",
        approval_id: str | None = None,
    ) -> ApprovalRecord:
        aid = approval_id or str(uuid4())
        record = ApprovalRecord(
            approval_id=aid,
            tool_name=tool_name,
            arguments=dict(arguments),
            summary=summary,
            idempotency_key=aid,
        )
        self._records[aid] = record
        return record

    def get(self, approval_id: str) -> ApprovalRecord | None:
        return self._records.get(approval_id)

    def grant(self, approval_id: str, *, auth_proof: str) -> ApprovalRecord | None:
        record = self._records.get(approval_id)
        if record is None or record.status != ApprovalStatus.PENDING:
            return None
        record.status = ApprovalStatus.GRANTED
        record.auth_proof = auth_proof
        record.lifecycle_stage = HitlLifecycleStage.HUMAN_APPROVAL
        return record

    def reject(self, approval_id: str) -> ApprovalRecord | None:
        record = self._records.get(approval_id)
        if record is None or record.status != ApprovalStatus.PENDING:
            return None
        record.status = ApprovalStatus.REJECTED
        record.lifecycle_stage = HitlLifecycleStage.HUMAN_APPROVAL
        return record

    def mark_commit(self, approval_id: str) -> None:
        record = self._records.get(approval_id)
        if record is not None:
            record.lifecycle_stage = HitlLifecycleStage.COMMIT

    def mark_verified(self, approval_id: str) -> None:
        record = self._records.get(approval_id)
        if record is not None:
            record.lifecycle_stage = HitlLifecycleStage.VERIFY

    def can_execute_side_effect(self, approval_id: str | None, tool_name: str) -> bool:
        if not approval_id:
            return False
        record = self._records.get(approval_id)
        if record is None:
            return False
        if record.status != ApprovalStatus.GRANTED:
            return False
        return record.tool_name == tool_name

    def idempotency_key_for(self, approval_id: str | None) -> str | None:
        if not approval_id:
            return None
        record = self._records.get(approval_id)
        return record.idempotency_key if record is not None else None
